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

"""Unit tests for typed errors, serialization, and CxContext."""

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from enum import Enum

from google.api_core import exceptions as api_exceptions
from google.cloud.contact_center_insights_v1 import types as cci_types
from google.protobuf import timestamp_pb2
from pydantic import BaseModel
import pytest

from cxidk.core import context
from cxidk.core import errors
from cxidk.core import serialize


class SampleEnum(Enum):
    """Sample enum for serialization tests."""

    ALPHA = "alpha"


@dataclass
class SampleData:
    """Sample dataclass for serialization tests."""

    label: str
    mode: SampleEnum


class SampleModel(BaseModel):
    """Sample Pydantic model for serialization tests."""

    count: int


def test_from_google_api_maps_known_exceptions() -> None:
    """Verifies GAPIC error classes map to distinct CxidkError subclasses."""
    assert isinstance(
        errors.from_google_api(api_exceptions.InvalidArgument("bad filter")),
        errors.InvalidArgumentError,
    )
    assert isinstance(
        errors.from_google_api(api_exceptions.NotFound("missing")),
        errors.NotFoundError,
    )
    assert isinstance(
        errors.from_google_api(api_exceptions.PermissionDenied("denied")),
        errors.PermissionDeniedError,
    )
    assert isinstance(
        errors.from_google_api(api_exceptions.Unauthenticated("no creds")),
        errors.UnauthenticatedError,
    )
    assert isinstance(
        errors.from_google_api(api_exceptions.AlreadyExists("dup")),
        errors.ConflictError,
    )
    assert isinstance(
        errors.from_google_api(api_exceptions.TooManyRequests("slow down")),
        errors.QuotaExceededError,
    )


def test_from_http_maps_status_codes_and_formats_hint() -> None:
    """Verifies HTTP status codes map to typed CxidkError with hints."""
    url = "https://contactcenterinsights.googleapis.com/v1/x"
    err_404 = errors.from_http("get", url, 404, "not found")
    assert isinstance(err_404, errors.NotFoundError)
    assert err_404.status_code == 404
    assert "Hint:" in err_404.format_for_agent()

    err_429 = errors.from_http("post", url, 429, "quota")
    assert isinstance(err_429, errors.QuotaExceededError)


def test_to_jsonable_handles_proto_plus_protobuf_pydantic_and_dataclass() -> None:
    """Verifies JSON-safe conversion across SDK message types."""
    conv = cci_types.Conversation(
        name="projects/my-proj/locations/us-central1/conversations/c1",
        language_code="en-US",
    )
    ts = timestamp_pb2.Timestamp()  # pylint: disable=no-member
    ts.FromDatetime(datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc))

    payload = {
        "conversation": conv,
        "timestamp": ts,
        "dataclass": SampleData(label="ok", mode=SampleEnum.ALPHA),
        "model": SampleModel(count=3),
    }
    serialized = serialize.to_jsonable(payload)
    assert serialized["conversation"]["name"].endswith("/conversations/c1")
    assert serialized["conversation"]["language_code"] == "en-US"
    assert serialized["dataclass"] == {"label": "ok", "mode": "alpha"}
    assert serialized["model"] == {"count": 3}


def test_cx_context_validates_project_and_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensures CxContext fails fast when project or location is missing or invalid."""
    monkeypatch.delenv("CXIDK_PROJECT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("CXIDK_LOCATION", raising=False)

    with pytest.raises(errors.InvalidArgumentError):
        context.CxContext.from_env()

    monkeypatch.setenv("CXIDK_PROJECT_ID", "valid-project-123")
    with pytest.raises(errors.InvalidArgumentError):
        context.CxContext.from_env()

    with pytest.raises(errors.InvalidArgumentError):
        context.validate_project_id("BAD_UPPERCASE_PROJECT!")
