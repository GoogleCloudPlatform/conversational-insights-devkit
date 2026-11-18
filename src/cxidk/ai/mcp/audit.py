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

"""Structured Cloud Logging audit records, OpenTelemetry spans, and rate limiting."""

from contextlib import contextmanager
import json
import logging
import threading
import time
from typing import Any, Dict, Iterator, Tuple

from opentelemetry import trace

audit_logger = logging.getLogger("cxidk.ai.mcp.audit")
_tracer = trace.get_tracer("cxidk.ai.mcp")

_REDACTED_ARG_KEYS = frozenset(
    {
        "authorization",
        "token",
        "access_token",
        "id_token",
        "plan_token",
        "signing_key",
        "transcript",
        "speech_v2_transcript",
    }
)


def sanitize_args_for_audit(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Produces a metadata-only copy of tool arguments safe for audit logging.

    Never logs raw conversation transcripts, tokens, or signing keys.

    Args:
        kwargs: Raw tool invocation keyword arguments.

    Returns:
        Sanitized dictionary with sensitive keys redacted and long strings truncated.
    """
    sanitized: Dict[str, Any] = {}
    for key, value in kwargs.items():
        if key in ("ctx", "cx"):
            continue
        if key.lower() in _REDACTED_ARG_KEYS:
            sanitized[key] = "<redacted>"
        elif isinstance(value, str) and len(value) > 256:
            sanitized[key] = f"{value[:64]}...<truncated:{len(value)}>"
        else:
            sanitized[key] = value
    return sanitized


def emit_audit_event(
    *,
    tool_name: str,
    principal: str,
    safety: str,
    project_id: str,
    location: str,
    status: str,
    duration_ms: float,
    args: Dict[str, Any],
    error_code: str = "",
) -> Dict[str, Any]:
    """Emits a structured JSON audit record compatible with Google Cloud Logging.

    Args:
        tool_name: Registered tool name.
        principal: Authenticated caller subject.
        safety: Tool safety classification (`read`, `write`, `destructive`).
        project_id: Target GCP project ID (or `<none>`).
        location: Target GCP location (or `<none>`).
        status: Execution outcome (`ok` or `error`).
        duration_ms: Execution latency in milliseconds.
        args: Tool arguments prior to sanitization.
        error_code: Optional structured error code when `status != 'ok'`.

    Returns:
        Emitted structured audit dictionary.
    """
    record: Dict[str, Any] = {
        "severity": "INFO" if status == "ok" else "WARNING",
        "event": "cxidk.ai.mcp.tool_call",
        "tool": tool_name,
        "principal": principal,
        "safety": safety,
        "project_id": project_id,
        "location": location,
        "status": status,
        "duration_ms": round(duration_ms, 2),
        "args": sanitize_args_for_audit(args),
    }
    if error_code:
        record["error_code"] = error_code
    audit_logger.info(json.dumps(record, sort_keys=True, default=str))
    return record


@contextmanager
def trace_tool_call(
    tool_name: str,
    principal: str,
    safety: str,
) -> Iterator[Any]:
    """Wraps a tool invocation in an OpenTelemetry span without PII attributes.

    Args:
        tool_name: Registered tool name.
        principal: Authenticated caller subject.
        safety: Tool safety classification.

    Yields:
        Active OpenTelemetry `Span` instance.
    """
    with _tracer.start_as_current_span(f"mcp.tool.{tool_name}") as span:
        span.set_attribute("mcp.tool.name", tool_name)
        span.set_attribute("mcp.principal", principal)
        span.set_attribute("mcp.tool.safety", safety)
        yield span


class RateLimiter:
    """Thread-safe token-bucket rate limiter keyed by authenticated principal."""

    def __init__(self, requests_per_minute: int = 60) -> None:
        """Initializes the rate limiter.

        Args:
            requests_per_minute: Allowed burst and sustained calls per minute.
        """
        self.capacity = float(max(1, requests_per_minute))
        self.refill_per_sec = self.capacity / 60.0
        self._buckets: Dict[str, Tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, principal: str) -> bool:
        """Consumes one token for `principal`, returning False when rate-limited.

        Args:
            principal: Caller key for the token bucket.

        Returns:
            True when allowed; False when the bucket is exhausted.
        """
        now = time.monotonic()
        with self._lock:
            tokens, last_ts = self._buckets.get(principal, (self.capacity, now))
            elapsed = max(0.0, now - last_ts)
            replenished = min(
                self.capacity, tokens + elapsed * self.refill_per_sec
            )
            if replenished < 1.0:
                self._buckets[principal] = (replenished, now)
                return False
            self._buckets[principal] = (replenished - 1.0, now)
            return True
