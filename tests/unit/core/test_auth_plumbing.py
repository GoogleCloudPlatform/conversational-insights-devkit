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

"""Auth scope hygiene, token refresh, and wrapper credential plumbing tests."""

from unittest.mock import MagicMock
from unittest.mock import patch

from cxidk.core import base
from cxidk.wrapper import agents
from cxidk.wrapper import iam
from cxidk.wrapper import insights
from cxidk.wrapper import sensitive_data_protection
from cxidk.wrapper import storage
from cxidk.wrapper import vertex


@patch("google.auth.transport.requests.Request")
def test_auth_does_not_mutate_global_scopes(_mock_req: MagicMock) -> None:
    """Regression test: passing `scope=` must never mutate GLOBAL_SCOPES."""
    before = list(base.GLOBAL_SCOPES)
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.expired = False
    mock_creds.token = "tok-1"

    auth_instance = base.Auth(
        creds=mock_creds,
        scope=["https://www.googleapis.com/auth/spreadsheets"],
    )
    assert base.GLOBAL_SCOPES == before
    assert "https://www.googleapis.com/auth/spreadsheets" in auth_instance.scopes


@patch("cxidk.core.base.requests")
@patch("cxidk.core.base.auth_request")
def test_request_refreshes_expired_token_before_sending(
    mock_auth_req: MagicMock,
    mock_requests: MagicMock,
) -> None:
    """Ensures expired credentials refresh automatically before HTTP calls."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.expired = False
    mock_creds.token = "initial-token"

    auth_obj = base.Auth(creds=mock_creds)
    mock_creds.refresh.assert_not_called()

    # Now expire the token and verify Request.make refreshes it
    mock_creds.expired = True

    def _do_refresh(_req: object) -> None:
        mock_creds.expired = False
        mock_creds.valid = True
        mock_creds.token = "refreshed-token"

    mock_creds.refresh.side_effect = _do_refresh
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"ok": true}'
    mock_resp.json.return_value = {"ok": True}
    mock_requests.get.return_value = mock_resp

    req = base.Request(
        project_id="my-project",
        location="us-central1",
        base_url="https://us-central1-contactcenterinsights.googleapis.com/v1/",
        auth=auth_obj,
    )
    res = req.make("projects/my-project/locations/us-central1/settings", base.Methods.GET, None)
    assert res == {"ok": True}
    mock_creds.refresh.assert_called_once_with(mock_auth_req.return_value)
    sent_headers = mock_requests.get.call_args.kwargs["headers"]
    assert sent_headers["Authorization"] == "Bearer refreshed-token"


def _make_explicit_auth() -> base.Auth:
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.expired = False
    mock_creds.token = "injected-token"
    return base.Auth(creds=mock_creds)


@patch("cxidk.wrapper.insights.contact_center_insights_v1.ContactCenterInsightsClient")
def test_all_insights_wrappers_forward_credentials(
    mock_cci_client: MagicMock,
) -> None:
    """Verifies every GAPIC Insights wrapper forwards `credentials=auth.creds`."""
    explicit_auth = _make_explicit_auth()
    cfg = base.Config(region="us-central1")
    parent = "projects/my-project/locations/us-central1"

    insights.Settings("my-project", parent, auth=explicit_auth, config=cfg)
    insights.Ingestion(parent, auth=explicit_auth, config=cfg)
    insights.Analysis(parent, auth=explicit_auth, config=cfg)
    insights.Export(parent, auth=explicit_auth, config=cfg)
    insights.LongRunningOperation(
        "my-project", "us-central1", operation_id="op-1", auth=explicit_auth, config=cfg
    )
    insights.LegacyScorecards("my-project", "us-central1", auth=explicit_auth, config=cfg)
    insights.ScorecardQuestions(
        "my-project",
        "us-central1",
        "sc-1",
        revision_id="rev-1",
        auth=explicit_auth,
        config=cfg,
    )

    assert mock_cci_client.call_count == 7
    for call in mock_cci_client.call_args_list:
        assert call.kwargs["credentials"] is explicit_auth.creds

    # The REST-composed facade must thread the same auth/config into every
    # collection it builds instead of falling back to ADC.
    facade = insights.Scorecards("my-project", "us-central1", auth=explicit_auth, config=cfg)
    assert facade.auth is explicit_auth
    assert facade.collection.auth is explicit_auth
    assert facade.collection.request.auth is explicit_auth
    assert facade.collection.config is cfg
    # pylint: disable-next=protected-access
    assert facade._questions("sc-1", "rev-1").request.auth is explicit_auth


@patch("cxidk.wrapper.storage.Client")
@patch("cxidk.wrapper.sensitive_data_protection.dlp_v2.DlpServiceClient")
@patch("cxidk.wrapper.iam.resourcemanager_v3.ProjectsClient")
@patch("cxidk.wrapper.iam.iam_admin_v1.IAMClient")
@patch("cxidk.wrapper.vertex.genai.Client")
@patch("cxidk.wrapper.agents.ConversationsClient")
@patch("cxidk.wrapper.agents.ParticipantsClient")
def test_other_wrappers_forward_credentials(
    mock_part: MagicMock,
    mock_conv: MagicMock,
    mock_genai: MagicMock,
    mock_iam: MagicMock,
    mock_rm: MagicMock,
    mock_dlp: MagicMock,
    mock_storage: MagicMock,
) -> None:
    """Verifies Storage, DLP, IAM, Vertex, and Dialogflow wrappers forward credentials."""
    explicit_auth = _make_explicit_auth()
    cfg = base.Config(region="us-central1")

    storage.Gcs("bkt", "my-project", auth=explicit_auth, config=cfg)
    sensitive_data_protection.DLP("my-project", "us-central1", auth=explicit_auth, config=cfg)
    iam.Policy("my-project", auth=explicit_auth, config=cfg)
    vertex.Generator("my-project", "us-central1", auth=explicit_auth, config=cfg)
    agents.Dialogflow("my-project", "us-central1", "prof-1", auth=explicit_auth, config=cfg)

    assert mock_storage.call_args.kwargs["credentials"] is explicit_auth.creds
    assert mock_dlp.call_args.kwargs["credentials"] is explicit_auth.creds
    assert mock_rm.call_args.kwargs["credentials"] is explicit_auth.creds
    assert mock_iam.call_args.kwargs["credentials"] is explicit_auth.creds
    assert mock_genai.call_args.kwargs["credentials"] is explicit_auth.creds
    assert mock_conv.call_args.kwargs["credentials"] is explicit_auth.creds
    assert mock_part.call_args.kwargs["credentials"] is explicit_auth.creds
