"""Offline, administrator-controlled policy bundle distribution.

Air-gapped friendly: an administrator exports a signed bundle on one machine
and imports it on another via a file — no network, no server required. Import
verifies authenticity/integrity BEFORE the policy is parsed/activated, and
rejects stale versions (rollback protection) when a current version is known.

If a central control plane is later added, it only needs to serve the same
signed-bundle format over HTTPS; this local importer stays the trust anchor.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List, Optional

from .integrity import (
    IntegrityError,
    TrustedKeyStore,
    sign_bundle_ed25519,
    sign_bundle_hmac,
    verify_bundle,
)
from .policy import OrgPolicy, PolicyValidationError, validate_policy


class PolicyImportError(Exception):
    """Raised when a policy bundle cannot be imported."""


def export_bundle(
    policies: List[OrgPolicy],
    key_id: str,
    key_material: bytes,
    bundle_version: int = 1,
    alg: str = "Ed25519",
) -> Dict[str, Any]:
    """Build a signed, importable bundle from one or more policies.

    ``alg="Ed25519"`` (default) signs with a raw Ed25519 private key
    (``key_material``); desktops verify with the matching public key. ``alg=
    "HMAC-SHA256"`` uses the legacy shared-secret scheme (admin-only trust).
    """
    for p in policies:
        validate_policy(p)
    payload = {
        "bundle_version": bundle_version,
        "policies": [p.to_dict() for p in policies],
    }
    if alg == "Ed25519":
        return sign_bundle_ed25519(payload, key_id, key_material)
    if alg == "HMAC-SHA256":
        return sign_bundle_hmac(payload, key_id, key_material)
    raise ValueError(f"Unsupported signing algorithm: {alg!r}")


def write_bundle_file(bundle: Dict[str, Any], path: str) -> None:
    """Atomically write a bundle to ``path`` (temp + replace)."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def import_policy_bundle(
    source: Any,
    store: TrustedKeyStore,
    current_versions: Optional[Dict[str, int]] = None,
) -> List[OrgPolicy]:
    """Import and verify a policy bundle.

    ``source`` may be a bundle dict or a filesystem path to a JSON bundle.
    Verification order (fail-closed):
      1. Load JSON (reject unreadable/invalid).
      2. Verify signature with a trusted key (reject tampered/untrusted).
      3. Validate each policy's structure/schema.
      4. Reject a policy whose version is OLDER than the known current version
         for its org (rollback/downgrade protection).

    Returns the list of authenticated, validated policies on success.
    """
    bundle = _load_bundle(source)

    try:
        payload = verify_bundle(bundle, store)
    except IntegrityError as e:
        raise PolicyImportError(f"Integrity check failed: {e}") from e

    policies_raw = payload.get("policies")
    if not isinstance(policies_raw, list) or not policies_raw:
        raise PolicyImportError("Bundle contains no policies.")

    current_versions = current_versions or {}
    policies: List[OrgPolicy] = []
    for raw in policies_raw:
        try:
            policy = OrgPolicy.from_dict(raw)
            validate_policy(policy)
        except PolicyValidationError as e:
            raise PolicyImportError(f"Invalid policy in bundle: {e}") from e

        known = current_versions.get(policy.org_id)
        if known is not None and policy.version < known:
            raise PolicyImportError(
                f"Refusing to import stale policy for org '{policy.org_id}': "
                f"bundle version {policy.version} < current {known}."
            )
        policies.append(policy)

    return policies


def _load_bundle(source: Any) -> Dict[str, Any]:
    if isinstance(source, dict):
        return source
    if isinstance(source, (str, os.PathLike)):
        try:
            with open(source, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError as e:
            raise PolicyImportError(f"Bundle file not found: {source}") from e
        except (json.JSONDecodeError, OSError) as e:
            raise PolicyImportError(f"Could not read bundle: {e}") from e
    raise PolicyImportError("Unsupported bundle source type.")
