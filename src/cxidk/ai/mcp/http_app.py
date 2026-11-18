# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Hardened Streamable HTTP ASGI application for Cloud Run and loopback dev."""

from contextlib import asynccontextmanager
import json
from typing import Any, AsyncIterator, Dict, List, MutableMapping, Optional, Tuple
from urllib.parse import urlparse

from mcp.server import MCPServer

from cxidk.core import context
from cxidk.core import errors
from cxidk.ai.mcp import audit
from cxidk.ai.mcp import auth
from cxidk.ai import policy as ai_policy
from cxidk.ai.mcp import server as mcp_server

SECURITY_HEADERS: Tuple[Tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"cache-control", b"no-store"),
    (
        b"content-security-policy",
        b"default-src 'none'; frame-ancestors 'none'",
    ),
)


def _is_allowed_local_origin(origin: Optional[str]) -> bool:
    """Validates `Origin` header on loopback HTTP servers against DNS rebinding."""
    if not origin:
        return True
    parsed = urlparse(origin)
    return parsed.scheme in ("http", "https") and (
        parsed.hostname in ai_policy.LOOPBACK_HOSTS
    )


def _decode_headers(raw_headers: List[Tuple[bytes, bytes]]) -> Dict[str, str]:
    """Converts ASGI byte headers into a lowercase string dictionary."""
    decoded: Dict[str, str] = {}
    for raw_k, raw_v in raw_headers:
        decoded[raw_k.decode("latin-1").lower()] = raw_v.decode("latin-1")
    return decoded


def _merge_security_headers(
    existing: List[Tuple[bytes, bytes]],
) -> List[Tuple[bytes, bytes]]:
    """Appends mandatory security headers without duplicating existing keys."""
    present = {k.lower() for k, _ in existing}
    merged = list(existing)
    for sec_k, sec_v in SECURITY_HEADERS:
        if sec_k not in present:
            merged.append((sec_k, sec_v))
    return merged


async def _send_json(
    send: Any,
    status: int,
    payload: Dict[str, Any],
    extra_headers: Optional[List[Tuple[bytes, bytes]]] = None,
) -> None:
    """Sends a JSON HTTP response with security headers."""
    body = json.dumps(payload).encode("utf-8")
    base_headers: List[Tuple[bytes, bytes]] = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if extra_headers:
        base_headers.extend(extra_headers)
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": _merge_security_headers(base_headers),
        }
    )
    await send({"type": "http.response.body", "body": body})


class SecuredMcpHttpApp:
    """ASGI wrapper adding auth, Origin protection, rate limiting, and headers.

    Attributes:
        inner_app: Underlying Starlette/MCP Streamable HTTP ASGI application.
        policy: Server security policy configuration.
        rate_limiter: Per-principal token-bucket rate limiter.
        transport_request: Optional Google Auth transport for OIDC verification.
    """

    def __init__(
        self,
        inner_app: Any,
        policy: ai_policy.Policy,
        *,
        rate_limiter: Optional[audit.RateLimiter] = None,
        transport_request: Optional[Any] = None,
    ) -> None:
        """Initializes `SecuredMcpHttpApp`.

        Args:
            inner_app: Underlying MCP Streamable HTTP ASGI application.
            policy: Server security policy configuration.
            rate_limiter: Optional rate limiter override.
            transport_request: Optional Google Auth transport for tests or custom TLS.
        """
        self.inner_app = inner_app
        self.policy = policy
        self.rate_limiter = rate_limiter or audit.RateLimiter(
            policy.rate_limit_per_minute
        )
        self.transport_request = transport_request

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        """Starts and stops the underlying MCP Streamable HTTP session manager.

        Yields:
            None while the inner ASGI lifespan context is active.
        """
        async with self.inner_app.router.lifespan_context(self.inner_app):
            yield

    async def _handle_mcp(
        self, scope: MutableMapping[str, Any], receive: Any, send: Any
    ) -> None:
        """Handles `/mcp` requests with method, Origin, auth, and rate guards."""
        method = str(scope.get("method", "")).upper()
        if method != "POST":
            await _send_json(
                send,
                405,
                {"error": "Method not allowed. Use POST /mcp."},
                extra_headers=[(b"allow", b"POST")],
            )
            return

        headers = _decode_headers(list(scope.get("headers") or []))
        if not self.policy.require_auth and not _is_allowed_local_origin(
            headers.get("origin")
        ):
            await _send_json(
                send,
                403,
                {"error": "Forbidden Origin header for loopback MCP server."},
            )
            return

        try:
            principal = auth.authenticate_headers(
                headers,
                self.policy,
                transport_request=self.transport_request,
            )
        except errors.UnauthenticatedError as exc:
            await _send_json(
                send,
                401,
                {"error": exc.message, "code": exc.code},
                extra_headers=[(b"www-authenticate", b"Bearer")],
            )
            return

        if not self.rate_limiter.allow(principal.subject):
            await _send_json(
                send,
                429,
                {
                    "error": "Rate limit exceeded.",
                    "code": "QUOTA_EXCEEDED",
                },
            )
            return

        async def _wrapped_send(message: MutableMapping[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                raw_hdrs = list(message.get("headers") or [])
                message = {
                    **message,
                    "headers": _merge_security_headers(raw_hdrs),
                }
            await send(message)

        token = auth.bind_principal(principal)
        try:
            await self.inner_app(scope, receive, _wrapped_send)
        finally:
            auth.reset_principal(token)

    async def __call__(
        self, scope: MutableMapping[str, Any], receive: Any, send: Any
    ) -> None:
        """Routes ASGI `lifespan`, `/healthz`, and `/mcp` requests.

        Args:
            scope: ASGI connection scope mapping.
            receive: ASGI receive awaitable.
            send: ASGI send awaitable.
        """
        scope_type = scope.get("type")
        if scope_type == "lifespan":
            await self.inner_app(scope, receive, send)
            return
        if scope_type != "http":
            return

        path = str(scope.get("path", ""))
        method = str(scope.get("method", "")).upper()

        if path == "/healthz":
            if method != "GET":
                await _send_json(
                    send,
                    405,
                    {"error": "Method not allowed. Use GET /healthz."},
                    extra_headers=[(b"allow", b"GET")],
                )
                return
            await _send_json(
                send, 200, {"status": "ok", "service": "cxidk-mcp"}
            )
            return

        if path == "/mcp":
            await self._handle_mcp(scope, receive, send)
            return

        await _send_json(send, 404, {"error": "Not found."})


def build_http_app(
    *,
    server: Optional[MCPServer] = None,
    policy: Optional[ai_policy.Policy] = None,
    cx: Optional[context.CxContext] = None,
    host: str = "127.0.0.1",
    transport_request: Optional[Any] = None,
) -> SecuredMcpHttpApp:
    """Constructs a hardened Streamable HTTP ASGI application.

    Args:
        server: Optional pre-built `MCPServer` instance.
        policy: Optional `Policy`; defaults to `Policy.from_env(transport='http')`.
        cx: Optional base `CxContext` injected into tool calls.
        host: Bind address checked against unauthenticated non-loopback binds.
        transport_request: Optional Google Auth transport for JWT verification.

    Returns:
        Configured `SecuredMcpHttpApp` ASGI callable.

    Raises:
        PolicyViolationError: If unauthenticated HTTP is bound to a non-loopback host.
    """
    eff_policy = policy or ai_policy.Policy.from_env(transport="http")
    if not eff_policy.require_auth and host not in ai_policy.LOOPBACK_HOSTS:
        raise errors.PolicyViolationError(
            f"Refusing to bind unauthenticated HTTP MCP server to {host!r}.",
            hint=(
                "Bind to `127.0.0.1` for local development or enable IAP/OIDC "
                "authentication (`CXIDK_IAP_AUDIENCE` / `CXIDK_OAUTH_AUDIENCE`)."
            ),
        )
    eff_server = server or mcp_server.build_server(policy=eff_policy, cx=cx)
    inner = eff_server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        host=host,
    )
    return SecuredMcpHttpApp(
        inner_app=inner,
        policy=eff_policy,
        transport_request=transport_request,
    )
