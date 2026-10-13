"""Organization policy format, validation, and precedence resolution.

A policy declares organization-managed vocabulary, approved deterministic
correction rules, formatting conventions, and feature locks. Policies are
versioned so updates and rollback are explicit.

Precedence (highest wins), per the enterprise spec:
    1. Mandatory security/organization policies (``locked`` settings).
    2. Administrator-managed vocabulary and correction rules.
    3. User-level vocabulary and preferences (only where not locked).

Administrator-locked settings are ENFORCED here (the resolver drops any user
value for a locked key), not merely hidden in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# The schema version this build understands. A bundle declaring a higher major
# version is rejected (unsupported) rather than silently partially applied.
SUPPORTED_SCHEMA_MAJOR = 1


class PolicyValidationError(ValueError):
    """Raised when a policy fails structural/semantic validation."""


class PolicyLayer:
    """Named precedence layers (lowest to highest)."""

    USER = "user"
    ADMIN = "admin"
    SECURITY = "security"

    ORDER = {USER: 0, ADMIN: 1, SECURITY: 2}


@dataclass
class OrgPolicy:
    """A single versioned organization policy document."""

    org_id: str
    version: int  # monotonic; higher = newer
    schema_version: str = "1.0"
    layer: str = PolicyLayer.ADMIN  # which precedence layer this belongs to
    vocabulary: Dict[str, str] = field(default_factory=dict)  # spoken -> written
    correction_rules: List[Dict[str, str]] = field(default_factory=list)
    formatting: Dict[str, Any] = field(default_factory=dict)
    # Feature availability controlled by policy. True = allowed, False = blocked.
    feature_flags: Dict[str, bool] = field(default_factory=dict)
    # Settings the administrator locks. Mapping of setting key -> enforced value.
    # A locked key cannot be overridden by lower layers.
    locked_settings: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "org_id": self.org_id,
            "version": self.version,
            "schema_version": self.schema_version,
            "layer": self.layer,
            "vocabulary": self.vocabulary,
            "correction_rules": self.correction_rules,
            "formatting": self.formatting,
            "feature_flags": self.feature_flags,
            "locked_settings": self.locked_settings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OrgPolicy":
        if not isinstance(data, dict):
            raise PolicyValidationError("Policy must be a JSON object.")
        try:
            return cls(
                org_id=data["org_id"],
                version=data["version"],
                schema_version=data.get("schema_version", "1.0"),
                layer=data.get("layer", PolicyLayer.ADMIN),
                vocabulary=data.get("vocabulary", {}) or {},
                correction_rules=data.get("correction_rules", []) or [],
                formatting=data.get("formatting", {}) or {},
                feature_flags=data.get("feature_flags", {}) or {},
                locked_settings=data.get("locked_settings", {}) or {},
            )
        except KeyError as e:
            raise PolicyValidationError(f"Policy missing required field: {e}") from e


def validate_policy(policy: OrgPolicy) -> None:
    """Validate a policy before activation. Raises PolicyValidationError with a
    diagnostic message on the first problem found."""
    if not isinstance(policy.org_id, str) or not policy.org_id.strip():
        raise PolicyValidationError("org_id must be a non-empty string.")
    if not isinstance(policy.version, int) or policy.version < 0:
        raise PolicyValidationError("version must be a non-negative integer.")

    # Schema version gate: reject unsupported MAJOR versions explicitly.
    try:
        major = int(str(policy.schema_version).split(".")[0])
    except (ValueError, IndexError):
        raise PolicyValidationError(
            f"Invalid schema_version: {policy.schema_version!r}."
        )
    if major > SUPPORTED_SCHEMA_MAJOR:
        raise PolicyValidationError(
            f"Unsupported policy schema major version {major}; this build "
            f"supports up to {SUPPORTED_SCHEMA_MAJOR}."
        )

    if policy.layer not in PolicyLayer.ORDER:
        raise PolicyValidationError(f"Unknown policy layer: {policy.layer!r}.")

    if not isinstance(policy.vocabulary, dict):
        raise PolicyValidationError("vocabulary must be an object (spoken->written).")
    for k, v in policy.vocabulary.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise PolicyValidationError("vocabulary keys and values must be strings.")

    for rule in policy.correction_rules:
        if not isinstance(rule, dict) or "from" not in rule or "to" not in rule:
            raise PolicyValidationError(
                "each correction rule must be an object with 'from' and 'to'."
            )

    if not isinstance(policy.feature_flags, dict):
        raise PolicyValidationError("feature_flags must be an object.")
    for k, v in policy.feature_flags.items():
        if not isinstance(v, bool):
            raise PolicyValidationError(f"feature_flag {k!r} must be a boolean.")

    if not isinstance(policy.locked_settings, dict):
        raise PolicyValidationError("locked_settings must be an object.")


@dataclass
class ResolvedPolicy:
    """The effective configuration after precedence resolution."""

    vocabulary: Dict[str, str] = field(default_factory=dict)
    correction_rules: List[Dict[str, str]] = field(default_factory=list)
    formatting: Dict[str, Any] = field(default_factory=dict)
    feature_flags: Dict[str, bool] = field(default_factory=dict)
    effective_settings: Dict[str, Any] = field(default_factory=dict)
    locked_keys: List[str] = field(default_factory=list)
    # Provenance: which layer/version supplied each resolved setting value.
    provenance: Dict[str, Tuple[str, int]] = field(default_factory=dict)

    def is_locked(self, key: str) -> bool:
        return key in self.locked_keys


def resolve_policies(
    policies: List[OrgPolicy],
    user_settings: Optional[Dict[str, Any]] = None,
    user_vocabulary: Optional[Dict[str, str]] = None,
) -> ResolvedPolicy:
    """Merge policies by precedence and apply user values only where allowed.

    - Higher layers override lower layers; within a layer, a higher ``version``
      wins (newer policy).
    - ``locked_settings`` from any layer are enforced: the key becomes locked
      and lower layers / the user cannot change it.
    - User vocabulary/settings apply only to keys not locked by a higher layer.
    """
    for p in policies:
        validate_policy(p)

    # Sort ascending so later entries (higher precedence) overwrite earlier.
    ordered = sorted(policies, key=lambda p: (PolicyLayer.ORDER[p.layer], p.version))

    resolved = ResolvedPolicy()
    user_settings = user_settings or {}
    user_vocabulary = user_vocabulary or {}

    # 1) Start with the USER layer values (lowest precedence).
    resolved.vocabulary.update(user_vocabulary)
    for k, v in user_settings.items():
        resolved.effective_settings[k] = v
        resolved.provenance[k] = (PolicyLayer.USER, 0)

    # 2) Apply admin + security policies in precedence order.
    locked: Dict[str, Any] = {}
    for p in ordered:
        resolved.vocabulary.update(p.vocabulary)
        resolved.correction_rules.extend(p.correction_rules)
        resolved.formatting.update(p.formatting)
        resolved.feature_flags.update(p.feature_flags)
        for k, v in p.locked_settings.items():
            locked[k] = v
            resolved.effective_settings[k] = v
            resolved.provenance[k] = (p.layer, p.version)

    # 3) Re-assert locks over any user value (enforcement, not hiding).
    for k, v in locked.items():
        resolved.effective_settings[k] = v
    resolved.locked_keys = sorted(locked.keys())

    return resolved
