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

"""Non-blocking long-running operation polling tool."""

from typing import Optional

from cxidk.core import context
from cxidk.core import errors
from cxidk.core import serialize
from cxidk.ai.tools import models
from cxidk.ai.tools import registry
from cxidk.ai.tools import validation
from cxidk.wrapper import insights


@registry.cx_tool(
    name="insights_get_operation",
    title="Get CCAI Insights Long-Running Operation",
    description=(
        "Polls the current status of a CCAI Insights long-running operation "
        "(`projects/{project}/locations/{location}/operations/{id}`) without "
        "blocking. Returns `done`, `metadata`, and either `response` or `error`."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=True,
    toolset="core",
    confirm=False,
    output_model=models.OperationStatusOutput,
)
def insights_get_operation(
    operation_name: str,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.OperationStatusOutput:
    """Returns a non-blocking status snapshot of a long-running operation.

    Args:
        operation_name: Full `projects/{project}/locations/{location}/operations/{id}` path.
        cx: Optional execution `CxContext`.

    Returns:
        `OperationStatusOutput` with `done`, `metadata`, `response`, and `error`.

    Raises:
        errors.InvalidArgumentError: If `operation_name` is malformed.
        errors.CxidkError: If polling the upstream operation fails.
    """
    proj, loc, op_id = validation.validate_operation_name(operation_name)
    target = context.CxContext.resolve(cx, project_id=proj, location=loc)

    with errors.translate_google_api_error():
        lro = insights.LongRunningOperation(
            project_id=target.project_id,
            location=target.location,
            operation_id=op_id,
            auth=target.auth,
            config=target.config,
        )
        raw = serialize.to_jsonable(lro.poll())

    return models.OperationStatusOutput(
        operation_name=str(raw.get("name") or operation_name.strip()),
        done=bool(raw.get("done", False)),
        metadata=raw.get("metadata"),
        response=raw.get("response"),
        error=raw.get("error"),
    )
