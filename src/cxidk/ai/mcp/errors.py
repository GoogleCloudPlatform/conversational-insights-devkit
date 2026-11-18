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

"""Safe, remediation-oriented MCP ToolError translation without stack-trace leaks."""

import re

from google.api_core import exceptions as google_exceptions
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from cxidk.core import errors

_BEARER_SCRUB_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")


def scrub_sensitive_text(message: str) -> str:
    """Removes bearer tokens from error messages prior to surfacing to clients.

    Args:
        message: Raw error message string.

    Returns:
        Sanitized message with bearer credentials replaced by `[REDACTED]`.
    """
    return _BEARER_SCRUB_RE.sub("Bearer [REDACTED]", message)


def to_tool_error(exc: Exception) -> ToolError:
    """Maps domain, validation, and Google API exceptions to a sanitized `ToolError`.

    Args:
        exc: Exception raised during tool validation or execution.

    Returns:
        Sanitized MCP `ToolError` containing `[CODE]` and remediation hint.
    """
    if isinstance(exc, ToolError):
        return exc

    if isinstance(exc, errors.CxidkError):
        return ToolError(scrub_sensitive_text(exc.format_for_agent()))

    if isinstance(exc, ValidationError):
        details = "; ".join(
            f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        return ToolError(
            f"[INVALID_ARGUMENT] Schema validation failed: {details}"
        )

    if isinstance(exc, google_exceptions.GoogleAPICallError):
        mapped = errors.from_google_api(exc)
        return to_tool_error(mapped)

    if isinstance(exc, ValueError):
        return ToolError(
            f"[INVALID_ARGUMENT] {scrub_sensitive_text(str(exc))}"
        )

    return ToolError(
        "[INTERNAL_ERROR] The requested operation failed unexpectedly. "
        "(Hint: Verify input parameters, credentials, and regional configuration.)"
    )
