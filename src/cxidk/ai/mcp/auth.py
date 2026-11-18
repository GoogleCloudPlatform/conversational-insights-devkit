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

"""IAP and OAuth2/OIDC caller verification for remote HTTP MCP deployments.

Security invariant: Incoming client tokens authenticate the caller *to this MCP
server* only and are NEVER forwarded to downstream Google Cloud APIs (preventing
token passthrough / confused-deputy attacks). Downstream calls execute under the
server's least-privilege IAM service account subject to `Policy` allowlists.

TODO(security): Add optional Workforce Identity Federation / OAuth 2.0 Token
Exchange (RFC 8693) when per-end-user IAM delegation is required beyond IAP.
"""

from contextvars import ContextVar
from contextvars import Token
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token

from cxidk.core import errors
from cxidk.ai import policy as ai_policy

IAP_HEADER = "x-goog-iap-jwt-assertion"
IAP_CERTS_URL = "https://www.gstatic.com/iap/verify/public_key"
IAP_ISSUER = "https://cloud.google.com/iap"


@dataclass(frozen=True)
class Principal:
    """Verified identity of the caller invoking an MCP request.

    Attributes:
        subject: Unique caller subject identifier (`sub` or email).
        email: Optional verified email address.
        auth_type: Authentication mechanism (`stdio`, `iap`, `oidc`, `local-dev`).
    """

    subject: str
    email: str = ""
    auth_type: str = "stdio"


_CURRENT_PRINCIPAL: ContextVar[Principal] = ContextVar(
    "cxidk_mcp_principal",
    default=Principal(subject="local-stdio", auth_type="stdio"),
)


def current_principal() -> Principal:
    """Returns the `Principal` bound to the current async/request context.

    Returns:
        Active `Principal` instance for the current task.
    """
    return _CURRENT_PRINCIPAL.get()


def bind_principal(principal: Principal) -> Token[Principal]:
    """Binds `principal` to the current contextvar and returns its reset token.

    Args:
        principal: Verified caller `Principal` to bind.

    Returns:
        `contextvars.Token` used to restore prior state via `reset_principal`.
    """
    return _CURRENT_PRINCIPAL.set(principal)


def reset_principal(token: Token[Principal]) -> None:
    """Restores the previous `Principal` contextvar state.

    Args:
        token: Reset token returned by `bind_principal`.
    """
    _CURRENT_PRINCIPAL.reset(token)


def _principal_from_claims(
    claims: Mapping[str, Any], auth_type: str, token_label: str
) -> Principal:
    """Extracts a verified `Principal` from decoded JWT claims."""
    sub = str(claims.get("sub") or claims.get("email") or "")
    if not sub:
        raise errors.UnauthenticatedError(
            f"{token_label} did not contain a subject claim."
        )
    return Principal(
        subject=sub,
        email=str(claims.get("email") or ""),
        auth_type=auth_type,
    )


def verify_iap_assertion(
    assertion: str,
    *,
    audience: str,
    transport_request: Optional[Any] = None,
) -> Principal:
    """Verifies a Google Cloud IAP signed JWT (`x-goog-iap-jwt-assertion`).

    Args:
        assertion: Compact JWT string from `x-goog-iap-jwt-assertion`.
        audience: Expected IAP JWT audience string.
        transport_request: Optional `google.auth.transport.Request` for JWKS fetch.

    Returns:
        Verified `Principal` with `auth_type='iap'`.

    Raises:
        errors.UnauthenticatedError: If signature, expiry, issuer, or audience check fails.
    """
    req = transport_request or google_auth_requests.Request()
    try:
        claims = id_token.verify_token(
            assertion,
            req,
            audience=audience,
            certs_url=IAP_CERTS_URL,
        )
    except Exception as exc:
        raise errors.UnauthenticatedError(
            "Invalid or expired IAP JWT assertion.",
            hint="Verify Cloud Run IAP audience configuration (`CXIDK_IAP_AUDIENCE`).",
        ) from exc

    if claims.get("iss") != IAP_ISSUER:
        raise errors.UnauthenticatedError(
            "IAP JWT assertion has an unexpected issuer claim.",
            hint=f"Expected `iss` equal to `{IAP_ISSUER}`.",
        )

    return _principal_from_claims(claims, "iap", "IAP JWT assertion")


def verify_bearer_oidc(
    authorization_header: str,
    *,
    audience: str,
    transport_request: Optional[Any] = None,
) -> Principal:
    """Verifies an OIDC `Authorization: Bearer <id_token>` header.

    Args:
        authorization_header: Raw HTTP `Authorization` header value.
        audience: Expected OIDC audience string (`CXIDK_OAUTH_AUDIENCE`).
        transport_request: Optional `google.auth.transport.Request` for JWKS fetch.

    Returns:
        Verified `Principal` with `auth_type='oidc'`.

    Raises:
        errors.UnauthenticatedError: If header format or token verification fails.
    """
    parts = authorization_header.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise errors.UnauthenticatedError(
            "Malformed Authorization header.",
            hint="Expected `Authorization: Bearer <oidc-id-token>`.",
        )
    raw_token = parts[1].strip()
    req = transport_request or google_auth_requests.Request()
    try:
        claims = id_token.verify_oauth2_token(
            raw_token,
            req,
            audience=audience,
        )
    except Exception as exc:
        raise errors.UnauthenticatedError(
            "Invalid or expired OAuth2/OIDC bearer token.",
            hint="Verify the token audience matches `CXIDK_OAUTH_AUDIENCE`.",
        ) from exc

    return _principal_from_claims(claims, "oidc", "Bearer ID token")


def authenticate_headers(
    headers: Mapping[str, str],
    policy: ai_policy.Policy,
    *,
    transport_request: Optional[Any] = None,
) -> Principal:
    """Authenticates incoming HTTP headers according to `policy`.

    Args:
        headers: Case-insensitive mapping of incoming HTTP request headers.
        policy: Server `Policy` specifying audience and auth requirements.
        transport_request: Optional `google.auth.transport.Request` override.

    Returns:
        Verified `Principal` for the HTTP request.

    Raises:
        errors.UnauthenticatedError: If credentials are missing or invalid.
    """
    lowered = {k.lower(): v for k, v in headers.items()}

    if not policy.require_auth:
        return Principal(subject="local-dev-http", auth_type="local-dev")

    iap_jwt = lowered.get(IAP_HEADER)
    if iap_jwt and policy.iap_audience:
        return verify_iap_assertion(
            iap_jwt,
            audience=policy.iap_audience,
            transport_request=transport_request,
        )

    auth_hdr = lowered.get("authorization")
    if auth_hdr and policy.oauth_audience:
        return verify_bearer_oidc(
            auth_hdr,
            audience=policy.oauth_audience,
            transport_request=transport_request,
        )

    if not policy.iap_audience and not policy.oauth_audience:
        raise errors.UnauthenticatedError(
            "Remote HTTP authentication is enabled, but neither "
            "`CXIDK_IAP_AUDIENCE` nor `CXIDK_OAUTH_AUDIENCE` is configured.",
            hint="Configure `CXIDK_IAP_AUDIENCE` (for IAP) or `CXIDK_OAUTH_AUDIENCE`.",
        )

    raise errors.UnauthenticatedError(
        "Missing valid authentication credentials.",
        hint="Provide an IAP assertion header or an OIDC Bearer token.",
    )
