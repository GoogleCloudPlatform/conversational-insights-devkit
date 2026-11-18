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

"""JSON-safe serialization helpers for protobuf, proto-plus, LRO, and Pydantic objects."""

import dataclasses
import datetime
from enum import Enum
from typing import Any, Dict, Mapping

from google.api_core import operation as ga_operation
from google.protobuf import json_format
from google.protobuf.message import Message as ProtobufMessage
import proto  # type: ignore[import-untyped]
from pydantic import BaseModel


def _serialize_operation(
    value: ga_operation.Operation,
    *,
    preserving_proto_field_name: bool,
) -> Dict[str, Any]:
    """Serializes a `google.api_core.operation.Operation` handle without blocking."""
    op_pb = getattr(value, "operation", None)
    op_name = getattr(op_pb, "name", "") if op_pb is not None else ""
    try:
        done = bool(value.done())
    except Exception:  # pylint: disable=broad-exception-caught
        done = bool(getattr(op_pb, "done", False))
    metadata_obj = getattr(value, "metadata", None)
    return {
        "operation_name": op_name,
        "done": done,
        "metadata": (
            to_jsonable(
                metadata_obj,
                preserving_proto_field_name=preserving_proto_field_name,
            )
            if metadata_obj is not None
            else None
        ),
    }


def _serialize_protobuf_or_model(
    value: Any,
    *,
    preserving_proto_field_name: bool,
) -> Any:
    """Serializes Pydantic, LRO Operation, proto-plus, or raw protobuf objects."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, ga_operation.Operation):
        return _serialize_operation(
            value, preserving_proto_field_name=preserving_proto_field_name
        )
    if isinstance(value, proto.Message):
        pb_msg = type(value).pb(value)
        return json_format.MessageToDict(
            pb_msg, preserving_proto_field_name=preserving_proto_field_name
        )
    if isinstance(value, ProtobufMessage):
        return json_format.MessageToDict(
            value, preserving_proto_field_name=preserving_proto_field_name
        )
    return None


def _serialize_container(
    value: Any,
    *,
    preserving_proto_field_name: bool,
) -> Any:
    """Serializes dataclasses, mappings, bytes, or sequence containers."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(
                getattr(value, field.name),
                preserving_proto_field_name=preserving_proto_field_name,
            )
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(k): to_jsonable(
                v, preserving_proto_field_name=preserving_proto_field_name
            )
            for k, v in value.items()
        }
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (list, tuple, set, frozenset)):
        return [
            to_jsonable(
                item, preserving_proto_field_name=preserving_proto_field_name
            )
            for item in value
        ]
    return str(value)


def to_jsonable(
    value: Any,
    *,
    preserving_proto_field_name: bool = True,
) -> Any:
    """Converts SDK responses into plain JSON-serializable Python structures.

    Args:
        value: Arbitrary SDK object (Protobuf, `proto-plus`, `Operation`,
            Pydantic model, dataclass, `datetime`, or nested container).
        preserving_proto_field_name: When True, keeps snake_case Protobuf field
            names rather than lowerCamelCase JSON names.

    Returns:
        JSON-serializable primitive, `dict`, or `list` representation.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return to_jsonable(
            value.value, preserving_proto_field_name=preserving_proto_field_name
        )
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return value.total_seconds()

    model_result = _serialize_protobuf_or_model(
        value, preserving_proto_field_name=preserving_proto_field_name
    )
    if model_result is not None:
        return model_result

    return _serialize_container(
        value, preserving_proto_field_name=preserving_proto_field_name
    )
