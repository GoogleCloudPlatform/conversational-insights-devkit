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

"""Security tests for CES Demo Studio UI backend, frontend, and deployment."""

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Dict, Generator, List, Optional, Tuple
from unittest.mock import MagicMock, patch

from google.api_core import exceptions as google_exceptions
import pytest

from cxidk.workflow.demo_artifacts.ui import main as ui_main

_UI_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "cxidk"
    / "workflow"
    / "demo_artifacts"
    / "ui"
)
_SCRIPT_JS_PATH = _UI_DIR / "frontend" / "script.js"
_INDEX_HTML_PATH = _UI_DIR / "frontend" / "index.html"
_DEPLOYMENT_SH_PATH = _UI_DIR / "deployment.sh"


class _FakeBlob:
    """In-memory GCS blob test double."""

    def __init__(self, store: Dict[str, str], name: str) -> None:
        self._store = store
        self._name = name

    def download_as_string(self) -> bytes:
        """Returns stored bytes or raises NotFound."""
        if self._name not in self._store:
            raise google_exceptions.NotFound(self._name)
        return self._store[self._name].encode("utf-8")

    def upload_from_string(
        self, data: str, content_type: str = "application/json"  # pylint: disable=unused-argument
    ) -> None:
        """Stores serialized JSON string in memory."""
        self._store[self._name] = data


class _FakeBucket:
    """In-memory GCS bucket test double."""

    def __init__(self) -> None:
        self.store: Dict[str, str] = {}

    def blob(self, name: str) -> _FakeBlob:
        """Returns a fake blob handle."""
        return _FakeBlob(self.store, name)


def _valid_flat_payload() -> Dict[str, Any]:
    """Returns a valid flat configuration payload matching frontend submissions."""
    return {
        "display_name": "Safe Demo Project",
        "project_id": "safe-demo-project",
        "project_number": "123456789012",
        "location": "us-central1",
        "environments": "prod,stg",
        "buckets_audios": "safe-demo-audios",
        "buckets_transcripts": "safe-demo-transcripts",
        "buckets_metadata": "safe-demo-metadata",
        "gen_theme": "Telecommunications",
        "gen_company_name": "Cymbal",
        "gen_language": "en-US",
        "gen_topics": "Billing,Outage",
        "gen_model": "gemini-2.5-pro",
        "gen_temperature": "0.5,0.8",
        "gen_topk": "30,40",
        "gen_topp": "0.9,1.0",
        "gen_sentiment_journeys": "Low to High",
        "max_conversations_per_run_audio": "5",
        "max_conversations_per_run_chat": "5",
        "max_conversations_per_run_agentic": "5",
        "probabilities_bad_sentiment": "0.1,0.2",
        "probabilities_long_conversation": "0.1,0.2",
        "probabilities_bad_performance": "0.1,0.2",
        "gen_prompt_hint": "",
        "virtual_agents": [
            {
                "agent": "90435a01-f8a0-42e9-a1e8-4a6417e9bfb4",
                "conversation_profile": "",
                "location": "us",
                "type": "next-gen",
                "environment": "prod",
                "topics": ["Billing"],
            }
        ],
    }


@pytest.fixture(name="fake_bucket")
def fixture_fake_bucket(monkeypatch: pytest.MonkeyPatch) -> Generator[_FakeBucket, None, None]:
    """Configures an in-memory GCS bucket and clears rate-limit state per test."""
    mem_bucket = _FakeBucket()
    monkeypatch.setattr(ui_main, "bucket", mem_bucket)
    monkeypatch.delenv("IAP_EXPECTED_AUDIENCE", raising=False)
    monkeypatch.delenv("CONFIG_API_KEY", raising=False)
    monkeypatch.delenv("ALLOWED_PROJECT_IDS", raising=False)
    monkeypatch.delenv("ALLOWED_BUCKETS", raising=False)
    monkeypatch.delenv("ALLOWED_PROJECT_NUMBERS", raising=False)
    monkeypatch.delenv("ALLOWED_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    ui_main._RATE_BUCKETS.clear()  # pylint: disable=protected-access
    yield mem_bucket
    ui_main._RATE_BUCKETS.clear()  # pylint: disable=protected-access


def test_all_routes_fail_closed_503_when_auth_unconfigured(
    fake_bucket: _FakeBucket,  # pylint: disable=unused-argument
) -> None:
    """Every route fails closed with 503 when neither IAP nor API key is set."""
    client = ui_main.app.test_client()
    assert client.get("/").status_code == 503
    assert client.get("/configurations").status_code == 503
    assert client.get("/configurations/raw").status_code == 503
    assert client.post("/configurations/single", json={}).status_code == 503
    assert client.get("/conversation-counts").status_code == 503
    assert client.post("/conversation-counts").status_code == 503


def test_api_key_authentication_protects_reads_and_writes(
    fake_bucket: _FakeBucket,  # pylint: disable=unused-argument
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Standalone CONFIG_API_KEY allows UI shell load and guards all API routes."""
    monkeypatch.setenv("CONFIG_API_KEY", "super-secret-test-key")
    client = ui_main.app.test_client()

    # Static shell loads in standalone mode so modal can prompt for key.
    assert client.get("/").status_code == 200

    # All API endpoints reject missing or wrong X-API-Key with 401.
    for method, path in [
        ("GET", "/configurations"),
        ("GET", "/configurations/raw"),
        ("POST", "/configurations/single"),
        ("GET", "/conversation-counts"),
        ("POST", "/conversation-counts"),
    ]:
        resp_missing = client.open(path, method=method, json={})
        assert resp_missing.status_code == 401
        resp_wrong = client.open(
            path, method=method, headers={"X-API-Key": "wrong-key"}, json={}
        )
        assert resp_wrong.status_code == 401

    headers = {"X-API-Key": "super-secret-test-key"}
    assert client.get("/configurations", headers=headers).status_code == 200
    assert client.get("/configurations/raw", headers=headers).status_code == 200
    assert client.get("/conversation-counts", headers=headers).status_code == 200


@patch("cxidk.workflow.demo_artifacts.ui.main.id_token.verify_token")
def test_iap_jwt_authentication_verifies_audience_and_issuer(
    mock_verify_token: MagicMock,
    fake_bucket: _FakeBucket,  # pylint: disable=unused-argument
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IAP JWT mode enforces signature/audience/issuer on UI shell and APIs."""
    expected_aud = "/projects/987339129652/locations/us-central1/services/ces-demo-studio"
    monkeypatch.setenv("IAP_EXPECTED_AUDIENCE", expected_aud)
    client = ui_main.app.test_client()

    # Without IAP JWT, even GET / is denied when IAP_EXPECTED_AUDIENCE is active.
    assert client.get("/").status_code == 401
    assert client.get("/configurations").status_code == 401

    # Wrong issuer is rejected.
    mock_verify_token.return_value = {"iss": "https://accounts.google.com"}
    assert (
        client.get(
            "/configurations",
            headers={"X-Goog-IAP-JWT-Assertion": "forged.jwt.token"},
        ).status_code
        == 401
    )

    # Verification exception is rejected.
    mock_verify_token.side_effect = ValueError("Invalid signature")
    assert (
        client.get(
            "/configurations",
            headers={"X-Goog-IAP-JWT-Assertion": "bad.jwt.token"},
        ).status_code
        == 401
    )

    # Valid IAP JWT succeeds.
    mock_verify_token.side_effect = None
    mock_verify_token.return_value = {
        "iss": "https://cloud.google.com/iap",
        "sub": "accounts.google.com:12345",
        "email": "operator@google.com",
    }
    ok_resp = client.get(
        "/configurations",
        headers={"X-Goog-IAP-JWT-Assertion": "valid.iap.jwt"},
    )
    assert ok_resp.status_code == 200
    assert (
        client.get(
            "/", headers={"X-Goog-IAP-JWT-Assertion": "valid.iap.jwt"}
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "override_field,override_value",
    [
        ("project_id", "../evil-project"),
        ("project_id", "UPPERCASE_BAD"),
        ("project_number", "not-digits"),
        ("display_name", "Bad\x00ControlChar"),
        ("location", "us-central1?ssrf=1"),
        ("location", "unsupported-region-9"),
        ("environments", "dev"),
        ("environments", ""),
        ("buckets_audios", "../outside-bucket"),
        ("buckets_transcripts", "bucket/with/slash"),
        ("max_conversations_per_run_chat", "99"),
        ("max_conversations_per_run_audio", "-1"),
        (
            "virtual_agents",
            [
                {
                    "agent": "agent/../../hack",
                    "conversation_profile": "prof1",
                    "location": "us-central1",
                    "type": "deterministic",
                    "environment": "prod",
                }
            ],
        ),
        (
            "virtual_agents",
            [
                {
                    "agent": "agent1",
                    "conversation_profile": "prof?inject=1",
                    "location": "us-central1",
                    "type": "deterministic",
                    "environment": "prod",
                }
            ],
        ),
        (
            "virtual_agents",
            [
                {
                    "agent": "agent1",
                    "conversation_profile": "prof1",
                    "location": "../bad-loc",
                    "type": "deterministic",
                    "environment": "prod",
                }
            ],
        ),
    ],
)
def test_single_configuration_rejects_malformed_or_traversal_inputs(
    override_field: str,
    override_value: Any,
    fake_bucket: _FakeBucket,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid project_id, location, buckets, counts, or VAs return HTTP 400."""
    monkeypatch.setenv("CONFIG_API_KEY", "test-key")
    client = ui_main.app.test_client()

    bad_cfg = _valid_flat_payload()
    bad_cfg[override_field] = override_value

    resp = client.post(
        "/configurations/single",
        headers={"X-API-Key": "test-key"},
        json={"action": "add", "configuration": bad_cfg},
    )
    assert resp.status_code == 400
    assert ui_main.PROJECTS_FILENAME not in fake_bucket.store


def test_single_configuration_enforces_ingress_allowlists_and_persists_valid(
    fake_bucket: _FakeBucket,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write endpoint enforces ALLOWED_PROJECT_IDS and ALLOWED_BUCKETS."""
    monkeypatch.setenv("CONFIG_API_KEY", "test-key")
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "safe-demo-project")
    monkeypatch.setenv(
        "ALLOWED_BUCKETS",
        "safe-demo-audios,safe-demo-transcripts,safe-demo-metadata",
    )
    client = ui_main.app.test_client()
    headers = {"X-API-Key": "test-key"}

    unallowlisted_proj = _valid_flat_payload()
    unallowlisted_proj["project_id"] = "attacker-gcp-project"
    assert (
        client.post(
            "/configurations/single",
            headers=headers,
            json={"action": "add", "configuration": unallowlisted_proj},
        ).status_code
        == 400
    )

    squatted_bkt = _valid_flat_payload()
    squatted_bkt["buckets_audios"] = "safe-demo-project-squatted"
    assert (
        client.post(
            "/configurations/single",
            headers=headers,
            json={"action": "add", "configuration": squatted_bkt},
        ).status_code
        == 400
    )

    ok_resp = client.post(
        "/configurations/single",
        headers=headers,
        json={"action": "add", "configuration": _valid_flat_payload()},
    )
    assert ok_resp.status_code == 200
    stored = json.loads(fake_bucket.store[ui_main.PROJECTS_FILENAME])
    assert len(stored["projects"]) == 1
    assert stored["projects"][0]["project_id"] == "safe-demo-project"


@patch(
    "cxidk.workflow.demo_artifacts.ui.main.contact_center_insights_v1.ContactCenterInsightsClient"
)
def test_conversation_counts_enforces_allowlist_and_hides_internal_errors(
    mock_insights_client: MagicMock,
    fake_bucket: _FakeBucket,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /conversation-counts fails closed and skips unallowlisted entries."""
    monkeypatch.setenv("CONFIG_API_KEY", "test-key")
    headers = {"X-API-Key": "test-key"}
    client = ui_main.app.test_client()

    # Fails closed with 503 when ALLOWED_PROJECT_IDS is unset.
    assert client.post("/conversation-counts", headers=headers).status_code == 503
    mock_insights_client.assert_not_called()

    fake_bucket.store[ui_main.PROJECTS_FILENAME] = json.dumps({
        "projects": [
            {"project_id": "attacker-project", "location": "us-central1"},
            {"project_id": "safe-demo-project", "location": "us-central1"},
        ]
    })
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "safe-demo-project")

    fake_page = MagicMock()
    fake_page.conversations = [object(), object(), object()]
    mock_insights_client.return_value.list_conversations.return_value.pages = [
        fake_page
    ]

    resp = client.post("/conversation-counts", headers=headers)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["data"]["projects"] == {"safe-demo-project": {"total": 3}}
    mock_insights_client.assert_called_once()

    # Verify generic error message when GCS raises an internal error.
    with patch.object(
        fake_bucket,
        "blob",
        side_effect=RuntimeError("sensitive-internal-gcs-bucket-detail"),
    ):
        err_resp = client.get("/configurations", headers=headers)
        assert err_resp.status_code == 500
        assert "sensitive-internal" not in err_resp.get_data(as_text=True)


def test_security_headers_cors_methods_and_rate_limit(
    fake_bucket: _FakeBucket,  # pylint: disable=unused-argument
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CSP, X-Frame-Options, nosniff, no-store, strict CORS, and rate limit hold."""
    monkeypatch.setenv("CONFIG_API_KEY", "test-key")
    monkeypatch.setenv("ALLOWED_CORS_ORIGINS", "*,https://trusted.corp.example.com")
    headers = {"X-API-Key": "test-key"}
    client = ui_main.app.test_client()

    api_resp = client.get(
        "/configurations",
        headers={**headers, "Origin": "https://evil.example.com"},
    )
    assert api_resp.status_code == 200
    csp = api_resp.headers["Content-Security-Policy"]
    directives = {
        part.strip().split()[0]: part.strip()
        for part in csp.split(";")
        if part.strip()
    }
    assert directives["script-src"] == "script-src 'self'"
    assert directives["style-src"] == "style-src 'self'"
    assert "'unsafe-inline'" not in csp
    assert "'unsafe-eval'" not in csp
    assert "cdnjs.cloudflare.com" not in csp
    assert "unpkg.com" not in csp
    assert api_resp.headers["X-Content-Type-Options"] == "nosniff"
    assert api_resp.headers["X-Frame-Options"] == "DENY"
    assert api_resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert api_resp.headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in api_resp.headers

    trusted_resp = client.get(
        "/configurations",
        headers={**headers, "Origin": "https://trusted.corp.example.com"},
    )
    assert (
        trusted_resp.headers["Access-Control-Allow-Origin"]
        == "https://trusted.corp.example.com"
    )
    assert "Access-Control-Allow-Credentials" not in trusted_resp.headers

    # Disallowed HTTP verb is rejected.
    assert client.delete("/configurations", headers=headers).status_code == 405

    # Rate limit enforces 429 when exceeded.
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    ui_main._RATE_BUCKETS.clear()  # pylint: disable=protected-access
    assert client.get("/configurations", headers=headers).status_code == 200
    assert client.get("/configurations", headers=headers).status_code == 200
    assert client.get("/configurations", headers=headers).status_code == 429


def test_frontend_and_deployment_static_security_invariants() -> None:
    """Asserts zero innerHTML/onclick/style sinks, zero CDNs, and IAP deploy flags."""
    js_source = _SCRIPT_JS_PATH.read_text(encoding="utf-8")
    js_code_lines = "\n".join(
        line for line in js_source.splitlines() if not line.strip().startswith("//")
    )
    assert ".innerHTML" not in js_source
    assert ".outerHTML" not in js_source
    assert "insertAdjacentHTML" not in js_source
    assert "document.write" not in js_source
    assert ".style." not in js_code_lines
    assert "sessionStorage" not in js_code_lines
    assert not re.search(r"\b(?:alert|confirm|prompt)\s*\(", js_code_lines)

    class _HtmlInspector(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.inline_events: List[Tuple[str, str]] = []
            self.inline_styles: List[str] = []
            self.external_assets: List[Dict[str, str]] = []

        def handle_starttag(
            self, tag: str, attrs: List[Tuple[str, Optional[str]]]
        ) -> None:
            attr_map: Dict[str, str] = {
                k.lower(): (v or "") for k, v in attrs
            }
            for attr_name in attr_map:
                if attr_name.startswith("on"):
                    self.inline_events.append((tag, attr_name))
                if attr_name == "style":
                    self.inline_styles.append(tag)
            if tag in ("script", "link"):
                url = attr_map.get("src") or attr_map.get("href") or ""
                if url.startswith("https://"):
                    self.external_assets.append({
                        "url": url,
                        "integrity": attr_map.get("integrity", ""),
                        "crossorigin": attr_map.get("crossorigin", ""),
                    })

    html_source = _INDEX_HTML_PATH.read_text(encoding="utf-8")
    inspector = _HtmlInspector()
    inspector.feed(html_source)
    assert not inspector.inline_events, (
        f"Inline handlers found: {inspector.inline_events}"
    )
    assert not inspector.inline_styles, (
        f"Inline style attributes found on tags: {inspector.inline_styles}"
    )
    assert not inspector.external_assets, (
        f"Unexpected third-party CDN assets: {inspector.external_assets}"
    )

    deploy_sh = _DEPLOYMENT_SH_PATH.read_text(encoding="utf-8")
    assert "--no-allow-unauthenticated" in deploy_sh
    assert "--iap" in deploy_sh
    assert "--allow-unauthenticated" not in deploy_sh
    assert "allUsers" not in deploy_sh
    assert "roles/storage.objectUser" in deploy_sh


@pytest.mark.skipif(shutil.which("node") is None, reason="node runtime not installed")
def test_frontend_stored_dom_xss_payloads_render_as_inert_text() -> None:
    """Executes script.js against XSS payloads in Node VM and verifies inert DOM."""
    node_harness = r"""
const fs = require('fs');
const vm = require('vm');

class FakeElement {
  constructor(tagName) {
    this.tagName = String(tagName).toUpperCase();
    this.children = [];
    this.childNodes = [];
    this.attributes = {};
    this.dataset = {};
    this.style = {};
    this.listeners = {};
    this.parentElement = null;
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.id = '';
    this.className = '';
    this.type = '';
    this._text = '';
    this.classList = {
      _set: new Set(),
      add: (...cls) => cls.forEach((c) => this.classList._set.add(c)),
      remove: (...cls) => cls.forEach((c) => this.classList._set.delete(c)),
      contains: (c) => this.classList._set.has(c),
    };
  }
  set innerHTML(_v) {
    throw new Error('Forbidden innerHTML assignment detected!');
  }
  set outerHTML(_v) {
    throw new Error('Forbidden outerHTML assignment detected!');
  }
  insertAdjacentHTML() {
    throw new Error('Forbidden insertAdjacentHTML call detected!');
  }
  set textContent(val) {
    this.children = [];
    this.childNodes = [];
    this._text = String(val ?? '');
  }
  get textContent() {
    if (this.childNodes.length === 0) return this._text;
    return this.childNodes
      .map((n) => (typeof n === 'string' ? n : n.textContent))
      .join('');
  }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  appendChild(node) {
    if (node && node._isFragment) {
      node.childNodes.forEach((c) => this.appendChild(c));
      return node;
    }
    if (node && typeof node === 'object') node.parentElement = this;
    this.childNodes.push(node);
    if (node && node.tagName) this.children.push(node);
    return node;
  }
  append(...nodes) { nodes.forEach((n) => this.appendChild(n)); }
  replaceChildren(...nodes) {
    this.children = [];
    this.childNodes = [];
    this._text = '';
    this.append(...nodes);
  }
  insertBefore(newNode, _refNode) { return this.appendChild(newNode); }
  remove() {}
  cloneNode() {
    const copy = new FakeElement(this.tagName);
    copy._text = this._text;
    return copy;
  }
  addEventListener(ev, fn) {
    if (!this.listeners[ev]) this.listeners[ev] = [];
    this.listeners[ev].push(fn);
  }
  removeEventListener() {}
  dispatchEvent() {}
  closest() { return null; }
  querySelector(sel) {
    if (sel === '.modal-background' || sel === '.modal-close' || sel === 'svg') {
      return new FakeElement('div');
    }
    return new FakeElement('input');
  }
  querySelectorAll() { return []; }
}

const elementsById = {};
const ensureId = (id) => {
  if (!elementsById[id]) {
    const el = new FakeElement('div');
    el.id = id;
    if (id === 'gcp-regions-template') {
      el.content = {
        cloneNode: () => ({ _isFragment: true, childNodes: [new FakeElement('option')] }),
      };
    }
    elementsById[id] = el;
  }
  return elementsById[id];
};

const docListeners = {};
const windowObj = { __xss: undefined };
const documentObj = {
  body: new FakeElement('body'),
  createElement: (tag) => new FakeElement(tag),
  createTextNode: (txt) => String(txt),
  getElementById: (id) => ensureId(id),
  querySelectorAll: () => [],
  addEventListener: (ev, fn) => { docListeners[ev] = fn; },
};

const xssDisplay = '<img src=x onerror="window.__xss=1">';
const xssProject = '"><svg onload="window.__xss=1">';
const xssCompany = '<script>window.__xss=1</script>';

const sandbox = {
  window: windowObj,
  document: documentObj,
  Headers: class { set() {} },
  Event: class {},
  Blob: class {},
  URL: { createObjectURL: () => '', revokeObjectURL: () => {} },
  navigator: { clipboard: { writeText: async () => {} } },
  localStorage: { getItem: () => 'disabled', setItem: () => {} },
  setTimeout: () => 0,
  console,
  fetch: async (url) => {
    if (url.endsWith('/configurations')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          configurations: [{
            display_name: xssDisplay,
            project_id: xssProject,
            generation_profile: { company_name: xssCompany },
          }],
        }),
      };
    }
    if (url.endsWith('/conversation-counts')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          message: 'ok',
          projects: { [xssProject]: { total: 7 } },
          data: {
            last_run_utc: '2026-11-16T00:00:00Z',
            projects: { [xssProject]: { total: 12 } },
          },
        }),
      };
    }
    throw new Error('Unexpected fetch: ' + url);
  },
};

const code = fs.readFileSync(process.argv[1], 'utf8');
vm.runInNewContext(code, sandbox);

(async () => {
  await docListeners.DOMContentLoaded();
  if (windowObj.__xss !== undefined) {
    throw new Error('XSS executed!');
  }
  const renderedListText = ensureId('projectListContainer').textContent;
  const renderedStatsText = ensureId('conversation-details-container').textContent;
  if (!renderedListText.includes(xssDisplay) || !renderedListText.includes(xssCompany)) {
    throw new Error('Escaped text missing from config list: ' + renderedListText);
  }
  if (!renderedStatsText.includes(xssProject)) {
    throw new Error('Escaped project ID missing from stats: ' + renderedStatsText);
  }
  process.stdout.write('DOM_XSS_SAFE_OK\n');
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
"""
    proc = subprocess.run(
        ["node", "-e", node_harness, str(_SCRIPT_JS_PATH)],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert proc.returncode == 0, f"Node DOM XSS check failed: {proc.stderr}"
    assert "DOM_XSS_SAFE_OK" in proc.stdout
