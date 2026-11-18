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

"""Typed exception hierarchy and error mappers for cxidk."""

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional, Tuple, Type

from google.api_core import exceptions as api_exceptions


class CxidkError(Exception):
    """Base exception for all structured cxidk errors.

    Attributes:
        code: Stable machine-readable error code.
        message: Human- and model-readable error summary.
        hint: Optional remediation guidance for callers or AI agents.
        status_code: Optional HTTP status code associated with the failure.
        details: Optional structured diagnostic metadata (never secrets).
    """

    default_code: str = "CXIDK_ERROR"
    default_status_code: Optional[int] = None

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        hint: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initializes a typed cxidk error."""
        self.code = code or self.default_code
        self.message = message
        self.hint = hint
        self.status_code = (
            status_code if status_code is not None else self.default_status_code
        )
        self.details = details or {}
        super().__init__(message)

    def format_for_agent(self) -> str:
        """Formats the error with actionable remediation guidance for AI tools.

        Returns:
            Formatted error string prefixed with `[code]` and optional hint.
        """
        if self.hint:
            return f"[{self.code}] {self.message} Hint: {self.hint}"
        return f"[{self.code}] {self.message}"


class InvalidArgumentError(CxidkError, ValueError):
    """Raised when caller-supplied parameters or filters are invalid."""

    default_code = "INVALID_ARGUMENT"
    default_status_code = 400


class UnauthenticatedError(CxidkError):
    """Raised when credentials or authentication tokens are missing or invalid."""

    default_code = "UNAUTHENTICATED"
    default_status_code = 401


class PermissionDeniedError(CxidkError):
    """Raised when the caller lacks IAM permissions or violates project policy."""

    default_code = "PERMISSION_DENIED"
    default_status_code = 403


class PolicyViolationError(PermissionDeniedError):
    """Raised when a server-side guardrail blocks a tool invocation."""

    default_code = "POLICY_VIOLATION"
    default_status_code = 403


class NotFoundError(CxidkError):
    """Raised when a requested Google Cloud resource does not exist."""

    default_code = "NOT_FOUND"
    default_status_code = 404


class ConflictError(CxidkError):
    """Raised when creating or updating a resource conflicts with existing state."""

    default_code = "ALREADY_EXISTS"
    default_status_code = 409


class QuotaExceededError(CxidkError):
    """Raised when API rate limits or resource quotas are exhausted."""

    default_code = "RESOURCE_EXHAUSTED"
    default_status_code = 429


class OperationFailedError(CxidkError):
    """Raised when a remote API call or long-running operation fails."""

    default_code = "OPERATION_FAILED"
    default_status_code = 500


class UnsafeEndpointError(InvalidArgumentError):
    """Raised when a request targets an untrusted or non-HTTPS endpoint."""

    default_code = "UNSAFE_ENDPOINT"
    default_status_code = 400


_GOOGLE_EXCEPTION_RULES: Tuple[
    Tuple[Tuple[Type[BaseException], ...], Type[CxidkError], str], ...
] = (
    (
        (api_exceptions.InvalidArgument,),
        InvalidArgumentError,
        "Verify resource IDs, location, and CCAI Insights filter syntax.",
    ),
    (
        (api_exceptions.Unauthenticated,),
        UnauthenticatedError,
        "Run `gcloud auth application-default login` or check credentials.",
    ),
    (
        (api_exceptions.PermissionDenied,),
        PermissionDeniedError,
        "Grant `roles/contactcenterinsights.viewer` (reads) or `editor` "
        "(writes) on the target project.",
    ),
    (
        (api_exceptions.NotFound,),
        NotFoundError,
        "Confirm project_id, location, and resource ID match the resource.",
    ),
    (
        (api_exceptions.AlreadyExists,),
        ConflictError,
        "A resource with this ID already exists in the target location.",
    ),
    (
        (api_exceptions.TooManyRequests, api_exceptions.ResourceExhausted),
        QuotaExceededError,
        "Reduce page_size or concurrency and retry with exponential backoff.",
    ),
)

_HTTP_STATUS_RULES: Dict[int, Tuple[Type[CxidkError], str]] = {
    400: (InvalidArgumentError, "Check request parameters and filter syntax."),
    401: (
        UnauthenticatedError,
        "Refresh credentials or verify authentication headers.",
    ),
    403: (
        PermissionDeniedError,
        "Check IAM roles (`roles/contactcenterinsights.*`) on the project.",
    ),
    404: (NotFoundError, "Verify the resource path and regional endpoint."),
    409: (ConflictError, "Resource already exists or state conflict occurred."),
    429: (QuotaExceededError, "API quota exceeded; retry after backoff."),
}


def from_google_api(
    exc: BaseException,
    *,
    hint: Optional[str] = None,
) -> CxidkError:
    """Maps a `google.api_core.exceptions` error into a typed `CxidkError`.

    Args:
        exc: Upstream exception raised by a Google Cloud client library.
        hint: Optional custom remediation hint overriding the default.

    Returns:
        Corresponding `CxidkError` subclass instance.
    """
    if isinstance(exc, CxidkError):
        return exc

    msg = str(exc)
    for exc_types, err_cls, default_hint in _GOOGLE_EXCEPTION_RULES:
        if isinstance(exc, exc_types):
            return err_cls(msg, hint=hint or default_hint)

    if isinstance(exc, api_exceptions.GoogleAPICallError):
        status = getattr(exc, "code", None)
        code_int = status if isinstance(status, int) else 500
        return OperationFailedError(
            msg,
            status_code=code_int,
            hint=hint or "Inspect the upstream Google Cloud API status details.",
        )
    return OperationFailedError(
        msg,
        hint=hint or "Unexpected error while calling Google Cloud API.",
    )


def from_http(
    method: str,
    url: str,
    status_code: int,
    body: str,
    *,
    hint: Optional[str] = None,
) -> CxidkError:
    """Maps an HTTP error response into a typed `CxidkError`.

    Args:
        method: HTTP verb (`GET`, `POST`, `PATCH`, `DELETE`).
        url: Request URL that returned the error.
        status_code: Upstream HTTP status code.
        body: Sanitized HTTP response body text.
        hint: Optional custom remediation hint overriding the default.

    Returns:
        Corresponding `CxidkError` subclass instance.
    """
    summary = f"{method.upper()} {url} failed with HTTP {status_code}: {body}"
    details: Dict[str, Any] = {
        "method": method.upper(),
        "url": url,
        "status_code": status_code,
    }
    err_cls, default_hint = _HTTP_STATUS_RULES.get(
        status_code,
        (OperationFailedError, "Upstream Google Cloud service returned an error."),
    )
    return err_cls(
        summary,
        status_code=status_code,
        details=details,
        hint=hint or default_hint,
    )


@contextmanager
def translate_google_api_error(
    *,
    hint: Optional[str] = None,
) -> Iterator[None]:
    """Context manager mapping `GoogleAPICallError` into typed `CxidkError`.

    Args:
        hint: Optional remediation hint overriding default status guidance.

    Yields:
        None while executing the wrapped Google Cloud SDK call.

    Raises:
        CxidkError: Translated from any raised `GoogleAPICallError`.
    """
    try:
        yield
    except api_exceptions.GoogleAPICallError as exc:
        raise from_google_api(exc, hint=hint) from exc
