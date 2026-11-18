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

"""Flask backend for the demo-artifacts configuration UI.

Serves the single-page frontend and exposes an authenticated JSON API used to
read and write the demo project configuration files (``projects.json``,
``display_names.json``, and ``numbers.json``) in GCS, plus an allowlist-guarded
endpoint that refreshes per-project Contact Center Insights conversation counts.
"""

from collections import defaultdict, deque
import copy
from datetime import datetime, timezone
import functools
import hmac
import json
import os
import re
import time
from typing import Any, Callable, Deque, Dict, FrozenSet, List, Optional, Set, Tuple, TypeVar

from flask import Flask, Response, abort, jsonify, render_template, request
from google.api_core import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.cloud import contact_center_insights_v1
from google.cloud import storage
from google.oauth2 import id_token
from werkzeug.exceptions import HTTPException

F = TypeVar("F", bound=Callable[..., Any])

app = Flask(__name__, template_folder="frontend", static_folder="frontend")
app.config["JSON_SORT_KEYS"] = False
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MiB request cap

PROJECTS_FILENAME = "projects.json"
DISPLAY_NAMES_FILENAME = "display_names.json"
NUMBERS_FILENAME = "numbers.json"

_IAP_CERTS_URL = "https://www.gstatic.com/iap/verify/public_key-jwk"
_IAP_ISSUER = "https://cloud.google.com/iap"
_GOOGLE_AUTH_REQUEST = google_requests.Request()

_SUPPORTED_LOCATIONS: FrozenSet[str] = frozenset({
    "global",
    "us",
    "us-central1",
    "us-east1",
    "us-west1",
    "northamerica-northeast1",
    "europe-west1",
    "europe-west2",
    "europe-west3",
    "europe-west4",
    "europe-west6",
    "asia-northeast1",
    "asia-northeast3",
    "asia-south1",
    "asia-southeast1",
    "asia-southeast2",
    "australia-southeast1",
})
_SUPPORTED_ENVIRONMENTS: FrozenSet[str] = frozenset({"prod", "stg"})
_SUPPORTED_VA_TYPES: FrozenSet[str] = frozenset({
    "deterministic",
    "generative",
    "next-gen",
    "agent-studio",
    "cxas",
})
_OPTIONAL_PROFILE_VA_TYPES: FrozenSet[str] = frozenset({
    "next-gen",
    "agent-studio",
    "cxas",
})

_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_PROJECT_NUMBER_RE = re.compile(r"^[0-9]{5,20}$")
_BUCKET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")
_SAFE_RESOURCE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
_UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_CSP_HEADER = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)
_API_PREFIXES: Tuple[str, ...] = ("/configurations", "/conversation-counts")

# Optional module-level overrides for tests; resolved lazily via `_get_bucket()`
# so importing this module never triggers network/ADC calls.
storage_client: Optional[storage.Client] = None  # pylint: disable=invalid-name
bucket: Optional[storage.Bucket] = None  # pylint: disable=invalid-name

# TODO(security): Enforce distributed rate limiting via Cloud Armor / IAP in
# multi-instance Cloud Run deployments.
_RATE_BUCKETS: Dict[str, Deque[float]] = defaultdict(deque)


def _parse_csv_env(var_name: str) -> Set[str]:
    """Parses a comma-separated environment variable into a stripped set."""
    raw = os.environ.get(var_name, "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _is_valid_bucket_name(name: str) -> bool:
    """Checks that `name` is a safe GCS bucket identifier."""
    return (
        bool(name)
        and ".." not in name
        and "/" not in name
        and "\\" not in name
        and bool(_BUCKET_NAME_RE.match(name))
    )


def _get_storage_client() -> storage.Client:
    """Returns the configured or lazily initialized GCS client."""
    global storage_client  # pylint: disable=global-statement
    if storage_client is None:
        storage_client = storage.Client()
    return storage_client


def _get_bucket() -> storage.Bucket:
    """Returns the configured GCS configuration bucket handle."""
    if bucket is not None:
        return bucket
    bucket_name = os.environ.get("GCS_BUCKET_NAME", "").strip()
    if not bucket_name:
        raise ValueError("GCS_BUCKET_NAME environment variable not set.")
    if not _is_valid_bucket_name(bucket_name):
        raise ValueError("GCS_BUCKET_NAME has an invalid format.")
    return _get_storage_client().bucket(bucket_name)


def _get_allowed_cors_origins() -> Set[str]:
    """Reads explicit allowed CORS origins dynamically, rejecting wildcards."""
    raw = os.environ.get("ALLOWED_CORS_ORIGINS") or os.environ.get(
        "ALLOWED_ORIGINS", ""
    )
    origins: Set[str] = set()
    for candidate in raw.split(","):
        origin = candidate.strip()
        if not origin or origin == "*":
            continue
        if origin.startswith("https://") or origin.startswith(
            ("http://127.0.0.1", "http://localhost")
        ):
            origins.add(origin)
    return origins


def _is_api_path(path: str) -> bool:
    """Returns True when `path` targets a JSON API endpoint."""
    return any(path == prefix or path.startswith(prefix + "/") for prefix in _API_PREFIXES)


def _check_rate_limit() -> None:
    """Applies a per-IP sliding-window rate limit on API requests."""
    raw_limit = os.environ.get("RATE_LIMIT_PER_MINUTE", "120").strip()
    try:
        limit = int(raw_limit)
    except ValueError:
        limit = 120
    if limit <= 0:
        return

    client_key = request.remote_addr or "local"
    now = time.monotonic()
    window = _RATE_BUCKETS[client_key]
    while window and now - window[0] > 60.0:
        window.popleft()
    if len(window) >= limit:
        abort(429, description="Rate limit exceeded. Please retry shortly.")
    window.append(now)


def _verify_iap_jwt(iap_jwt: str, audience: str) -> bool:
    """Verifies a Cloud Run IAP JWT signature, audience, expiry, and issuer."""
    if not iap_jwt or not audience:
        return False
    try:
        claims = id_token.verify_token(
            iap_jwt,
            _GOOGLE_AUTH_REQUEST,
            audience=audience,
            certs_url=_IAP_CERTS_URL,
        )
        return isinstance(claims, dict) and claims.get("iss") == _IAP_ISSUER
    except Exception:  # pylint: disable=broad-exception-caught
        return False


def _authenticate_request(allow_standalone_shell: bool = False) -> None:
    """Authenticates the active request via IAP JWT or X-API-Key (fail-closed)."""
    iap_aud = os.environ.get("IAP_EXPECTED_AUDIENCE", "").strip()
    api_key = os.environ.get("CONFIG_API_KEY", "").strip()
    if not iap_aud and not api_key:
        abort(503, description="Authentication is not configured on this server.")

    if iap_aud:
        iap_jwt = request.headers.get("X-Goog-IAP-JWT-Assertion", "")
        if _verify_iap_jwt(iap_jwt, iap_aud):
            return

    if api_key:
        if allow_standalone_shell and not iap_aud:
            return
        supplied = request.headers.get("X-API-Key", "")
        if supplied and hmac.compare_digest(
            supplied.encode("utf-8"), api_key.encode("utf-8")
        ):
            return

    abort(401, description="Authentication required.")


def require_auth(fn: F) -> F:
    """Decorator enforcing fail-closed authentication and rate limiting."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        _check_rate_limit()
        _authenticate_request(allow_standalone_shell=False)
        return fn(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


@app.before_request
def _handle_cors_preflight() -> Optional[Response]:
    """Handles CORS preflight requests only for explicitly allowlisted origins."""
    if request.method != "OPTIONS":
        return None
    origin = request.headers.get("Origin", "")
    if origin and origin in _get_allowed_cors_origins():
        resp = app.make_default_options_response()
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
        resp.headers["Vary"] = "Origin"
        return resp
    return Response(status=204)


@app.after_request
def _apply_security_headers(response: Response) -> Response:
    """Attaches strict CSP, framing, MIME, cache, and allowlisted CORS headers."""
    response.headers["Content-Security-Policy"] = _CSP_HEADER
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )
    if _is_api_path(request.path):
        response.headers["Cache-Control"] = "no-store"

    origin = request.headers.get("Origin", "")
    if origin and origin in _get_allowed_cors_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    else:
        response.headers.pop("Access-Control-Allow-Origin", None)
    response.headers.pop("Access-Control-Allow-Credentials", None)
    return response


@app.errorhandler(HTTPException)
def _handle_http_exception(exc: HTTPException) -> Tuple[Response, int]:
    """Returns structured JSON errors without reflecting unsanitized HTML."""
    code = exc.code or 500
    return jsonify({"error": exc.name, "description": exc.description}), code


def _default_content_for(filename: str) -> Dict[str, Any]:
    """Returns the fallback payload used when `filename` is missing or unreadable."""
    if filename == PROJECTS_FILENAME:
        return {"projects": []}
    if filename == NUMBERS_FILENAME:
        return {"projects": {}, "last_run_utc": None}
    return {}


def _get_json_from_gcs(filename: str) -> Dict[str, Any]:
    """Downloads `filename` from the config bucket and parses it as JSON."""
    blob = _get_bucket().blob(filename)
    try:
        content = blob.download_as_string()
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
        return _default_content_for(filename)
    except google_exceptions.NotFound:
        return _default_content_for(filename)
    except (json.JSONDecodeError, ValueError):
        app.logger.warning("Failed to parse JSON from '%s'; using default.", filename)
        return _default_content_for(filename)


def _write_json_to_gcs(filename: str, data: Dict[str, Any]) -> None:
    """Serializes `data` as indented JSON and uploads it to `filename`."""
    blob = _get_bucket().blob(filename)
    blob.upload_from_string(
        json.dumps(data, indent=2), content_type="application/json"
    )


def _to_list(value: Any) -> List[str]:
    """Normalizes `value` into a list of stripped strings."""
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _to_float(value: Any) -> Optional[float]:
    """Converts `value` to a float, or returns None when empty/None-like."""
    if value is not None and not isinstance(value, bool):
        text = str(value).strip()
        if text not in ("", "None"):
            return float(text)
    return None


def _parse_bounded_int(value: Any, field_name: str) -> int:
    """Parses an integer (or whole float) in `[0, 15]` or aborts with HTTP 400."""
    if value is None or (isinstance(value, str) and value.strip() in ("", "None")):
        return 0
    if isinstance(value, bool):
        abort(400, description=f"Invalid integer value for {field_name}.")
    try:
        numeric = float(str(value).strip())
    except ValueError:
        abort(400, description=f"Invalid integer value for {field_name}.")
    if not numeric.is_integer():
        abort(400, description=f"{field_name} must be a whole number.")
    parsed = int(numeric)
    if parsed < 0 or parsed > 15:
        abort(400, description=f"{field_name} must be between 0 and 15.")
    return parsed


def _to_list_of_floats(value: Any) -> List[float]:
    """Normalizes `value` into a list of floats, dropping empty entries."""
    if isinstance(value, str) and value.strip():
        parsed_items: List[float] = []
        for item in value.split(","):
            try:
                converted = _to_float(item.strip())
            except ValueError:
                abort(400, description="Invalid numeric range parameter.")
            if converted is not None:
                parsed_items.append(converted)
        return parsed_items
    if isinstance(value, list):
        result: List[float] = []
        for item in value:
            try:
                converted = _to_float(item)
            except ValueError:
                abort(400, description="Invalid numeric range parameter.")
            if converted is not None:
                result.append(converted)
        return result
    return []


def _structure_and_order_project(data: Dict[str, Any]) -> Dict[str, Any]:
    """Builds the canonical project configuration object from raw form `data`."""
    project_id = str(data.get("project_id", "")).strip()
    raw_display_name = str(data.get("display_name", "")).strip()
    theme = data.get("gen_theme", [])
    language = data.get("gen_language", [])

    return {
        "display_name": raw_display_name or project_id,
        "project_id": project_id,
        "project_number": str(data.get("project_number", "")).strip(),
        "location": str(data.get("location", "")).strip(),
        "environments": _to_list(data.get("environments", [])),
        "buckets": {
            "audios": str(data.get("buckets_audios", "")).strip(),
            "transcripts": str(data.get("buckets_transcripts", "")).strip(),
            "metadata": str(data.get("buckets_metadata", "")).strip(),
        },
        "virtual_agents": data.get("virtual_agents", []),
        "generation_profile": {
            "theme": (
                [theme.strip()]
                if isinstance(theme, str) and theme.strip()
                else _to_list(theme)
            ),
            "company_name": str(data.get("gen_company_name", "")).strip(),
            "language": (
                [language.strip()]
                if isinstance(language, str) and language.strip()
                else _to_list(language)
            ),
            "topics": _to_list(data.get("gen_topics", [])),
            "model": str(data.get("gen_model", "")).strip(),
            "temperature": _to_list_of_floats(data.get("gen_temperature", [])),
            "topk": _to_list_of_floats(data.get("gen_topk", [])),
            "topp": _to_list_of_floats(data.get("gen_topp", [])),
            "sentiment_journeys": _to_list(data.get("gen_sentiment_journeys", [])),
            "max_conversations_per_run": {
                "audio": _parse_bounded_int(
                    data.get("max_conversations_per_run_audio"),
                    "max_conversations_per_run.audio",
                ),
                "chat": _parse_bounded_int(
                    data.get("max_conversations_per_run_chat"),
                    "max_conversations_per_run.chat",
                ),
                "agentic": _parse_bounded_int(
                    data.get("max_conversations_per_run_agentic"),
                    "max_conversations_per_run.agentic",
                ),
            },
            "probabilities": {
                "bad_sentiment": _to_list_of_floats(
                    data.get("probabilities_bad_sentiment", [])
                ),
                "long_conversation": _to_list_of_floats(
                    data.get("probabilities_long_conversation", [])
                ),
                "bad_performance": _to_list_of_floats(
                    data.get("probabilities_bad_performance", [])
                ),
            },
            "prompt_hint": _to_list(data.get("gen_prompt_hint", [])),
        },
    }


def _validate_virtual_agents(virtual_agents: Any) -> List[Dict[str, Any]]:
    """Validates and normalizes the `virtual_agents` list or aborts HTTP 400."""
    if not isinstance(virtual_agents, list):
        abort(400, description="virtual_agents must be a list.")

    sanitized: List[Dict[str, Any]] = []
    for idx, va in enumerate(virtual_agents):
        if not isinstance(va, dict):
            abort(400, description=f"virtual_agents[{idx}] must be an object.")
        agent_id = str(va.get("agent", "")).strip()
        va_type = str(va.get("type", "")).strip()
        conv_profile = str(va.get("conversation_profile", "")).strip()
        va_location = str(va.get("location", "")).strip()
        va_env = str(va.get("environment", "")).strip()

        if not _SAFE_RESOURCE_ID_RE.match(agent_id):
            abort(400, description=f"Invalid virtual_agents[{idx}].agent identifier.")
        if va_type not in _SUPPORTED_VA_TYPES:
            abort(400, description=f"Unsupported virtual_agents[{idx}].type.")
        if conv_profile:
            if not _SAFE_RESOURCE_ID_RE.match(conv_profile):
                abort(
                    400,
                    description=(
                        f"Invalid virtual_agents[{idx}].conversation_profile."
                    ),
                )
        elif va_type not in _OPTIONAL_PROFILE_VA_TYPES:
            abort(
                400,
                description=(
                    f"virtual_agents[{idx}].conversation_profile is required "
                    f"for type '{va_type}'."
                ),
            )
        if va_location not in _SUPPORTED_LOCATIONS:
            abort(400, description=f"Unsupported virtual_agents[{idx}].location.")
        if va_env not in _SUPPORTED_ENVIRONMENTS:
            abort(400, description=f"Unsupported virtual_agents[{idx}].environment.")

        topics_raw = va.get("topics", [])
        topics = _to_list(topics_raw)
        sanitized.append({
            "agent": agent_id,
            "conversation_profile": conv_profile,
            "location": va_location,
            "type": va_type,
            "environment": va_env,
            "topics": topics,
        })
    return sanitized


def _validate_buckets_and_allowlists(
    project_id: str, project_number: str, buckets: Any
) -> None:
    """Validates bucket names and configured project/bucket/number allowlists."""
    if not isinstance(buckets, dict):
        abort(400, description="Invalid buckets configuration.")
    for bucket_key in ("audios", "transcripts", "metadata"):
        b_name = buckets.get(bucket_key, "")
        if not isinstance(b_name, str) or not _is_valid_bucket_name(b_name):
            abort(400, description=f"Invalid GCS bucket name for '{bucket_key}'.")

    allowed_projects = _parse_csv_env("ALLOWED_PROJECT_IDS")
    if allowed_projects and project_id not in allowed_projects:
        abort(400, description="project_id is not in ALLOWED_PROJECT_IDS.")

    allowed_buckets = _parse_csv_env("ALLOWED_BUCKETS")
    if allowed_buckets:
        for bucket_key in ("audios", "transcripts", "metadata"):
            if buckets[bucket_key] not in allowed_buckets:
                abort(
                    400,
                    description=f"Bucket '{buckets[bucket_key]}' is not allowlisted.",
                )

    allowed_numbers = _parse_csv_env("ALLOWED_PROJECT_NUMBERS")
    if allowed_numbers:
        _verify_bucket_project_numbers(project_number, buckets, allowed_numbers)


def _verify_bucket_project_numbers(
    project_number: str, buckets: Dict[str, Any], allowed_numbers: Set[str]
) -> None:
    """Verifies project_number and GCS bucket metadata match allowed_numbers."""
    if project_number not in allowed_numbers:
        abort(400, description="project_number is not allowlisted.")
    for bucket_key in ("audios", "transcripts", "metadata"):
        try:
            meta = _get_storage_client().get_bucket(buckets[bucket_key])
        except Exception:  # pylint: disable=broad-exception-caught
            abort(
                400,
                description=f"Could not verify ownership of '{buckets[bucket_key]}'.",
            )
        if str(meta.project_number) not in allowed_numbers:
            abort(
                400,
                description=(
                    f"Bucket '{buckets[bucket_key]}' does not belong to an "
                    "allowlisted project."
                ),
            )


def _validate_configuration_payload(structured_config: Dict[str, Any]) -> None:
    """Validates schema, path safety, and configured resource allowlists."""
    project_id = structured_config.get("project_id", "")
    if not isinstance(project_id, str) or not _PROJECT_ID_RE.match(project_id):
        abort(400, description="Invalid GCP project_id.")

    project_number = structured_config.get("project_number", "")
    if not isinstance(project_number, str) or not _PROJECT_NUMBER_RE.match(
        project_number
    ):
        abort(400, description="Invalid GCP project_number.")

    display_name = structured_config.get("display_name", "")
    if (
        not isinstance(display_name, str)
        or not 1 <= len(display_name) <= 128
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in display_name)
    ):
        abort(400, description="Invalid display_name.")

    if structured_config.get("location", "") not in _SUPPORTED_LOCATIONS:
        abort(400, description="Unsupported GCP location.")

    environments = structured_config.get("environments", [])
    if (
        not isinstance(environments, list)
        or not environments
        or any(env not in _SUPPORTED_ENVIRONMENTS for env in environments)
    ):
        abort(400, description="environments must be a non-empty subset of prod, stg.")

    structured_config["virtual_agents"] = _validate_virtual_agents(
        structured_config.get("virtual_agents", [])
    )
    _validate_buckets_and_allowlists(
        project_id, project_number, structured_config.get("buckets")
    )


def _validate_stats_project(project: Dict[str, Any]) -> Tuple[str, str]:
    """Validates a stored project entry before querying CCAI Insights (fail-closed)."""
    allowed_projects = _parse_csv_env("ALLOWED_PROJECT_IDS")
    if not allowed_projects:
        raise ValueError("ALLOWED_PROJECT_IDS is not configured; refusing stats scan.")

    project_id = str(project.get("project_id", "")).strip()
    if not _PROJECT_ID_RE.match(project_id):
        raise ValueError(f"Invalid project_id format: {project_id!r}")
    if project_id not in allowed_projects:
        raise ValueError(f"Project '{project_id}' is not in ALLOWED_PROJECT_IDS.")

    location = str(project.get("location", "us-central1")).strip() or "us-central1"
    if location not in _SUPPORTED_LOCATIONS:
        raise ValueError(f"Unsupported location '{location}' for '{project_id}'.")

    return project_id, location


def _upsert_project(
    current_projects: List[Dict[str, Any]],
    config_for_storage: Dict[str, Any],
    lookup_project_id: str,
) -> None:
    """Replaces the entry matching `lookup_project_id`, appending it when absent."""
    existing_idx = next(
        (
            i
            for i, p in enumerate(current_projects)
            if isinstance(p, dict) and p.get("project_id") == lookup_project_id
        ),
        -1,
    )
    if existing_idx == -1:
        current_projects.append(config_for_storage)
    else:
        current_projects[existing_idx] = config_for_storage


def _register_display_name(
    display_names_map: Dict[str, List[str]], project_id: str, display_name: str
) -> None:
    """Ensures `display_name` is listed under `project_id` in the display map."""
    if project_id not in display_names_map or not isinstance(
        display_names_map[project_id], list
    ):
        display_names_map[project_id] = []
    if display_name not in display_names_map[project_id]:
        display_names_map[project_id].append(display_name)


def _apply_edit_display_names(
    display_names_map: Dict[str, List[str]],
    original_project_id: str,
    new_project_id: str,
    original_display_name: Any,
    new_display_name: str,
) -> None:
    """Migrates and updates `display_names_map` during an edit operation."""
    if original_project_id != new_project_id and original_project_id in display_names_map:
        display_names_map[new_project_id] = display_names_map.pop(original_project_id)
    if new_project_id not in display_names_map or not isinstance(
        display_names_map[new_project_id], list
    ):
        display_names_map[new_project_id] = []
    if (
        isinstance(original_display_name, str)
        and original_display_name in display_names_map[new_project_id]
    ):
        display_names_map[new_project_id].remove(original_display_name)
    _register_display_name(display_names_map, new_project_id, new_display_name)


@app.route("/", methods=["GET"])
def index() -> str:
    """Serves the single-page configuration UI."""
    _check_rate_limit()
    _authenticate_request(allow_standalone_shell=True)
    return render_template("index.html")


@app.route("/configurations", methods=["GET"])
@require_auth
def get_configurations() -> Tuple[Response, int]:
    """Returns the stored projects, expanded to one entry per display name."""
    try:
        projects_data = _get_json_from_gcs(PROJECTS_FILENAME)
        projects_list = projects_data.get("projects", [])
        display_names_map = _get_json_from_gcs(DISPLAY_NAMES_FILENAME)
        final_configurations: List[Dict[str, Any]] = []

        for project in projects_list:
            if isinstance(project, dict) and "project_id" in project:
                project_id = str(project["project_id"])
                display_names = display_names_map.get(project_id, [])
                if isinstance(display_names, list) and display_names:
                    for name in display_names:
                        project_copy = copy.deepcopy(project)
                        project_copy["display_name"] = str(name)
                        final_configurations.append(project_copy)
                else:
                    project_copy = copy.deepcopy(project)
                    project_copy["display_name"] = project_id
                    final_configurations.append(project_copy)

        final_configurations.sort(
            key=lambda item: str(item.get("display_name", "")).lower()
        )
        return (
            jsonify({
                "configurations": final_configurations,
                "project_count": len(final_configurations),
            }),
            200,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        app.logger.exception("Failed to retrieve configurations.")
        return jsonify({"error": "Could not retrieve configuration."}), 500


@app.route("/configurations/raw", methods=["GET"])
@require_auth
def get_projects_config_raw() -> Response:
    """Returns the raw, pretty-printed contents of the projects file."""
    try:
        content = _get_bucket().blob(PROJECTS_FILENAME).download_as_string()
        return Response(
            json.dumps(json.loads(content), indent=4),
            mimetype="application/json",
            status=200,
        )
    except google_exceptions.NotFound:
        return Response(
            '{\n  "projects": []\n}',
            mimetype="application/json",
            status=200,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        app.logger.exception("Failed to retrieve raw configuration from GCS.")
        return Response(
            json.dumps({"error": "Could not retrieve configuration."}),
            mimetype="application/json",
            status=500,
        )


def _validate_edit_project_id(original_project_id: Any) -> str:
    """Validates `original_project_id` on edit requests."""
    if not isinstance(original_project_id, str) or not _PROJECT_ID_RE.match(
        original_project_id.strip()
    ):
        abort(400, description="Invalid original_project_id for edit.")
    cleaned = original_project_id.strip()
    allowed_projects = _parse_csv_env("ALLOWED_PROJECT_IDS")
    if allowed_projects and cleaned not in allowed_projects:
        abort(400, description="original_project_id is not in ALLOWED_PROJECT_IDS.")
    return cleaned


@app.route("/configurations/single", methods=["POST"])
@require_auth
def update_single_configuration() -> Tuple[Response, int]:
    """Handles validated Add or Edit configuration writes to GCS."""
    request_data = request.get_json(silent=True)
    if not isinstance(request_data, dict):
        abort(400, description="Request body must be a JSON object.")

    action = request_data.get("action")
    payload = request_data.get("configuration")
    if action not in {"add", "edit"} or not isinstance(payload, dict):
        abort(400, description="Invalid action or configuration payload.")

    structured_config = _structure_and_order_project(payload)
    _validate_configuration_payload(structured_config)
    validated_orig_id = (
        _validate_edit_project_id(request_data.get("original_project_id"))
        if action == "edit"
        else ""
    )

    try:
        projects_data = _get_json_from_gcs(PROJECTS_FILENAME)
        current_projects = projects_data.get("projects", [])
        if not isinstance(current_projects, list):
            current_projects = []
        display_names_map = _get_json_from_gcs(DISPLAY_NAMES_FILENAME)
    except Exception:  # pylint: disable=broad-exception-caught
        app.logger.exception("Failed to read current configuration state from GCS.")
        return (
            jsonify({
                "error": "Internal Server Error",
                "description": "Could not save configuration.",
            }),
            500,
        )

    new_project_id = structured_config["project_id"]
    new_display_name = structured_config["display_name"]
    config_for_storage = copy.deepcopy(structured_config)
    del config_for_storage["display_name"]

    if action == "add":
        _upsert_project(current_projects, config_for_storage, new_project_id)
        _register_display_name(display_names_map, new_project_id, new_display_name)
    else:
        _upsert_project(current_projects, config_for_storage, validated_orig_id)
        _apply_edit_display_names(
            display_names_map,
            validated_orig_id,
            new_project_id,
            request_data.get("original_display_name"),
            new_display_name,
        )

    try:
        _write_json_to_gcs(PROJECTS_FILENAME, {"projects": current_projects})
        _write_json_to_gcs(DISPLAY_NAMES_FILENAME, display_names_map)
        return jsonify({"message": "Configuration saved successfully!"}), 200
    except Exception:  # pylint: disable=broad-exception-caught
        app.logger.exception("Failed to write updated configuration to GCS.")
        return (
            jsonify({
                "error": "Internal Server Error",
                "description": "Could not save configuration.",
            }),
            500,
        )


@app.route("/conversation-counts", methods=["POST"])
@require_auth
def update_conversation_counts() -> Tuple[Response, int]:
    """Refreshes stored per-project conversation counts from CCAI Insights."""
    if not _parse_csv_env("ALLOWED_PROJECT_IDS"):
        return (
            jsonify({"error": "ALLOWED_PROJECT_IDS is not configured on this server."}),
            503,
        )

    try:
        current_counts_data = _get_json_from_gcs(NUMBERS_FILENAME)
        projects_data = _get_json_from_gcs(PROJECTS_FILENAME).get("projects", [])

        last_run_str = current_counts_data.get("last_run_utc")
        if isinstance(last_run_str, str) and _UTC_TIMESTAMP_RE.match(last_run_str):
            time_filter = f'create_time > "{last_run_str}"'
            new_counts_data: Dict[str, Any] = copy.deepcopy(current_counts_data)
            if not isinstance(new_counts_data.get("projects"), dict):
                new_counts_data["projects"] = {}
        else:
            time_filter = 'create_time > "2025-01-01T00:00:00Z"'
            new_counts_data = {"projects": {}, "last_run_utc": None}

        current_run_time = datetime.now(timezone.utc)
        app.logger.info(
            "Starting conversation count refresh at %s",
            current_run_time.isoformat(),
        )

        unique_projects = {
            p["project_id"]: p
            for p in projects_data
            if isinstance(p, dict) and p.get("project_id")
        }.values()

        for project in unique_projects:
            try:
                project_id, location = _validate_stats_project(project)
            except ValueError as exc:
                app.logger.error("Skipping invalid project in stats job: %s", exc)
                continue

            endpoint = (
                "contactcenterinsights.googleapis.com"
                if location == "global"
                else f"{location}-contactcenterinsights.googleapis.com"
            )
            client_options = {"api_endpoint": endpoint}
            client = contact_center_insights_v1.ContactCenterInsightsClient(
                client_options=client_options
            )
            parent = f"projects/{project_id}/locations/{location}"
            project_counts = new_counts_data["projects"].get(
                project_id, {"total": 0}
            )

            try:
                list_request = contact_center_insights_v1.ListConversationsRequest(
                    parent=parent,
                    filter=time_filter,
                    page_size=1000,
                    view=contact_center_insights_v1.ConversationView.BASIC,
                )
                iterator = client.list_conversations(request=list_request)
                total_delta = 0
                for page in iterator.pages:
                    page_count = len(list(page.conversations))
                    if page_count > 0:
                        total_delta += page_count

                project_counts["total"] = int(project_counts.get("total", 0)) + total_delta
                new_counts_data["projects"][project_id] = project_counts
                app.logger.info(
                    "[%s] Updated conversation count to %s",
                    project_id,
                    project_counts["total"],
                )
            except Exception:  # pylint: disable=broad-exception-caught
                app.logger.exception(
                    "[%s] Failed to query conversation counts.", project_id
                )

        new_counts_data["last_run_utc"] = current_run_time.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        _write_json_to_gcs(NUMBERS_FILENAME, new_counts_data)
        return (
            jsonify({
                "message": "Conversation counts updated successfully.",
                "data": new_counts_data,
            }),
            200,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        app.logger.exception("Fatal error in update_conversation_counts.")
        return jsonify({"error": "Failed to refresh conversation counts."}), 500


@app.route("/conversation-counts", methods=["GET"])
@require_auth
def get_conversation_counts() -> Tuple[Response, int]:
    """Returns the last computed per-project conversation counts."""
    try:
        counts = _get_json_from_gcs(NUMBERS_FILENAME)
        return jsonify(counts), 200
    except Exception:  # pylint: disable=broad-exception-caught
        app.logger.exception("Failed to read conversation counts.")
        return jsonify({"error": "Could not retrieve configuration."}), 500


if __name__ == "__main__":
    app.run(
        debug=False,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8080")),
    )
