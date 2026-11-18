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

"""Cryptographically signed plan tokens binding `config_plan_import` to `config_apply_import`."""

import hashlib
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import jwt

from cxidk.core import errors

logger = logging.getLogger(__name__)

_ISSUER = "cxidk-plan-v1"
_JWT_ALG = "HS256"
_MIN_KEY_BYTES = 32
DEFAULT_PLAN_TTL_SECONDS = 900
_REQUIRED_CLAIMS: Tuple[str, ...] = (
    "iss",
    "sub",
    "iat",
    "exp",
    "jti",
    "dst_project",
    "dst_location",
    "bundle_uri",
    "bundle_sha256",
    "assets",
    "activate_imported",
)

# Lazily generated per-process ephemeral key used ONLY when `allow_ephemeral=True`
# (local single-process stdio mode). Never hardcoded, never logged.
_PROCESS_EPHEMERAL_KEY: Optional[bytes] = None


def compute_bundle_digest(bundle_document: Any) -> str:
    """Computes a canonical SHA-256 hex digest of a configuration bundle.

    Args:
        bundle_document: Parsed JSON configuration bundle structure.

    Returns:
        64-character lowercase hexadecimal SHA-256 digest.
    """
    canonical = json.dumps(
        bundle_document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def resolve_signing_key(
    *,
    explicit_key: Optional[bytes] = None,
    allow_ephemeral: bool = True,
) -> bytes:
    """Resolves the HMAC signing key without any hardcoded fallback secret.

    Resolution priority:
    1. `explicit_key` argument (used in isolated tests or custom embeds)
    2. `CXIDK_PLAN_SIGNING_KEY` environment variable (Secret Manager on Cloud Run)
    3. Random per-process key via `secrets.token_bytes(32)` ONLY when
       `allow_ephemeral=True` (default for local `stdio`, disabled in production HTTP).

    Args:
        explicit_key: Optional caller-provided HMAC secret (>= 32 bytes).
        allow_ephemeral: Whether a per-process ephemeral key is permitted when
            `CXIDK_PLAN_SIGNING_KEY` is unset.

    Returns:
        Validated HMAC signing key bytes (at least 32 bytes).

    Raises:
        errors.PolicyViolationError: If no valid >=32-byte key is available.
    """
    global _PROCESS_EPHEMERAL_KEY  # pylint: disable=global-statement

    if explicit_key is not None:
        if len(explicit_key) < _MIN_KEY_BYTES:
            raise errors.PolicyViolationError(
                f"Plan signing key must be at least {_MIN_KEY_BYTES} bytes.",
                hint="Provide at least 32 random bytes for HS256 signing.",
            )
        return explicit_key

    env_val = os.environ.get("CXIDK_PLAN_SIGNING_KEY")
    if env_val:
        raw = env_val.encode("utf-8")
        if len(raw) < _MIN_KEY_BYTES:
            raise errors.PolicyViolationError(
                f"CXIDK_PLAN_SIGNING_KEY must be at least {_MIN_KEY_BYTES} bytes.",
                hint="Generate a 32+ byte secret in Secret Manager (`openssl rand -hex 32`).",
            )
        return raw

    if not allow_ephemeral:
        raise errors.PolicyViolationError(
            "CXIDK_PLAN_SIGNING_KEY is required for multi-instance HTTP deployments.",
            hint="Mount `CXIDK_PLAN_SIGNING_KEY` from Google Cloud Secret Manager.",
        )

    if _PROCESS_EPHEMERAL_KEY is None:
        _PROCESS_EPHEMERAL_KEY = secrets.token_bytes(32)
        logger.warning(
            "CXIDK_PLAN_SIGNING_KEY not set; generated an ephemeral per-process "
            "plan signing key (suitable for local stdio only)."
        )
    return _PROCESS_EPHEMERAL_KEY


def issue_plan_token(
    *,
    destination_project_id: str,
    destination_location: str,
    bundle_uri: str,
    bundle_sha256: str,
    assets: Iterable[str],
    activate_imported: bool = False,
    principal: str = "local-stdio",
    ttl_seconds: int = DEFAULT_PLAN_TTL_SECONDS,
    signing_key: Optional[bytes] = None,
    allow_ephemeral: bool = True,
) -> str:
    """Issues a short-lived HS256 JWT binding an approved import plan.

    Args:
        destination_project_id: Target GCP project ID.
        destination_location: Target CCAI Insights location.
        bundle_uri: `gs://` URI of the configuration bundle.
        bundle_sha256: Canonical SHA-256 digest of the bundle contents.
        assets: Asset category names covered by the dry-run plan.
        activate_imported: Planned `activate_imported` setting.
        principal: Authenticated caller identity (`sub` claim).
        ttl_seconds: Token lifetime in seconds.
        signing_key: Optional explicit signing secret (>= 32 bytes).
        allow_ephemeral: Whether ephemeral signing keys are permitted.

    Returns:
        Compact HS256-signed JWT `plan_token` string.
    """
    key = resolve_signing_key(
        explicit_key=signing_key, allow_ephemeral=allow_ephemeral
    )
    now = int(time.time())
    payload: Dict[str, Any] = {
        "iss": _ISSUER,
        "sub": principal,
        "iat": now,
        "exp": now + max(1, ttl_seconds),
        "jti": secrets.token_hex(16),
        "dst_project": destination_project_id,
        "dst_location": destination_location,
        "bundle_uri": bundle_uri,
        "bundle_sha256": bundle_sha256,
        "assets": sorted(str(a) for a in assets),
        "activate_imported": bool(activate_imported),
    }
    return jwt.encode(payload, key, algorithm=_JWT_ALG)


def _collect_claim_mismatches(
    claims: Dict[str, Any],
    *,
    principal: str,
    destination_project_id: str,
    destination_location: str,
    bundle_uri: str,
    bundle_sha256: str,
    expected_assets: List[str],
    activate_imported: bool,
) -> List[str]:
    """Compares decoded `plan_token` claims against target apply arguments."""
    checks = [
        (claims.get("sub") != principal, "caller principal"),
        (claims.get("dst_project") != destination_project_id, "destination project_id"),
        (claims.get("dst_location") != destination_location, "destination location"),
        (claims.get("bundle_uri") != bundle_uri, "bundle_uri"),
        (
            claims.get("bundle_sha256") != bundle_sha256,
            "bundle SHA-256 digest (bundle changed since plan)",
        ),
        (claims.get("assets") != expected_assets, "selected assets"),
        (
            bool(claims.get("activate_imported")) != bool(activate_imported),
            "activate_imported flag",
        ),
    ]
    return [label for failed, label in checks if failed]


def verify_plan_token(
    token: str,
    *,
    destination_project_id: str,
    destination_location: str,
    bundle_uri: str,
    bundle_sha256: str,
    assets: Iterable[str],
    activate_imported: bool = False,
    principal: str = "local-stdio",
    signing_key: Optional[bytes] = None,
    allow_ephemeral: bool = True,
) -> Dict[str, Any]:
    """Verifies a plan token's signature, expiry, algorithm, and exact target claims.

    Explicitly rejects `alg != HS256` (including `"none"`) prior to decoding.

    Args:
        token: Signed `plan_token` returned by `config_plan_import`.
        destination_project_id: Target GCP project ID for import.
        destination_location: Target CCAI Insights location for import.
        bundle_uri: `gs://` URI of the bundle being imported.
        bundle_sha256: Freshly computed SHA-256 digest of the bundle.
        assets: Asset category names requested for import.
        activate_imported: Requested `activate_imported` setting.
        principal: Authenticated caller identity.
        signing_key: Optional explicit verification secret.
        allow_ephemeral: Whether ephemeral signing keys are permitted.

    Returns:
        Verified JWT claims dictionary.

    Raises:
        errors.PolicyViolationError: If the token is missing, malformed,
            expired, forged, or mismatched against any target parameter.
    """
    if not isinstance(token, str) or not token.strip():
        raise errors.PolicyViolationError(
            "Missing plan_token for config_apply_import.",
            hint="Call `config_plan_import` first and pass its `plan_token`.",
        )

    key = resolve_signing_key(
        explicit_key=signing_key, allow_ephemeral=allow_ephemeral
    )

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise errors.PolicyViolationError(
            "Malformed plan_token header.",
            hint="Call `config_plan_import` to generate a valid plan_token.",
        ) from exc

    if header.get("alg") != _JWT_ALG:
        raise errors.PolicyViolationError(
            f"Rejected plan_token with disallowed JWT algorithm: {header.get('alg')!r}",
            hint="Only server-issued HS256 plan tokens are accepted.",
        )

    try:
        claims: Dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=[_JWT_ALG],
            issuer=_ISSUER,
            options={"require": list(_REQUIRED_CLAIMS)},
        )
    except jwt.ExpiredSignatureError as exc:
        raise errors.PolicyViolationError(
            "The plan_token has expired.",
            hint="Re-run `config_plan_import` to obtain a fresh token.",
        ) from exc
    except jwt.PyJWTError as exc:
        raise errors.PolicyViolationError(
            "Invalid plan_token signature or claims.",
            hint="Call `config_plan_import` to obtain a valid plan_token.",
        ) from exc

    expected_assets = sorted(str(a) for a in assets)
    mismatches = _collect_claim_mismatches(
        claims,
        principal=principal,
        destination_project_id=destination_project_id,
        destination_location=destination_location,
        bundle_uri=bundle_uri,
        bundle_sha256=bundle_sha256,
        expected_assets=expected_assets,
        activate_imported=activate_imported,
    )
    if mismatches:
        raise errors.PolicyViolationError(
            f"plan_token does not match apply parameters ({', '.join(mismatches)}).",
            hint=(
                "Re-run `config_plan_import` with the exact target project, "
                "location, bundle, and assets."
            ),
        )

    return claims
