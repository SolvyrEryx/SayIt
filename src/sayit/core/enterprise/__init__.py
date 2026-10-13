"""Modular enterprise/compliance foundation for SayIt.

This package is an ADDITIVE layer. None of it runs or changes behaviour for a
personal user unless an administrator explicitly imports a policy bundle. It is
designed so that missing server/identity infrastructure never destabilises
local dictation.

Modules
-------
- ``policy``        Versioned organization policy format + precedence + validation.
- ``integrity``     Genuine cryptographic authenticity/integrity verification.
                    Primary scheme is Ed25519 asymmetric signatures (public key
                    on verifiers); HMAC-SHA256 is retained as a labelled legacy
                    shared-secret path. Trusted-key management + tamper rejection.
- ``distribution``  Offline, administrator-controlled policy bundle import
                    (air-gapped friendly). No cloud dependency.
- ``audit``         Structured, redacted audit logging. Never records audio or
                    transcript content.

What is intentionally NOT implemented here (documented, not faked):
- SSO/OIDC login flows (require an external IdP + redirect URIs to verify).
- Per-seat license *enforcement* against a server (requires a license service).
These are left as documented interfaces so no "fake login/SSO" is shipped.
"""

from .audit import AuditEvent, AuditLog, TamperEvidentAuditLog, redact
from .distribution import (
    PolicyImportError,
    export_bundle,
    import_policy_bundle,
)
from .integrity import (
    IntegrityError,
    TrustedKeyStore,
    generate_ed25519_keypair,
    sign_bundle,
    sign_bundle_ed25519,
    sign_bundle_hmac,
    verify_bundle,
)
from .policy import (
    OrgPolicy,
    PolicyLayer,
    PolicyValidationError,
    ResolvedPolicy,
    resolve_policies,
    validate_policy,
)

__all__ = [
    "OrgPolicy",
    "PolicyLayer",
    "PolicyValidationError",
    "ResolvedPolicy",
    "resolve_policies",
    "validate_policy",
    "IntegrityError",
    "TrustedKeyStore",
    "generate_ed25519_keypair",
    "sign_bundle",
    "sign_bundle_ed25519",
    "sign_bundle_hmac",
    "verify_bundle",
    "PolicyImportError",
    "export_bundle",
    "import_policy_bundle",
    "AuditLog",
    "TamperEvidentAuditLog",
    "AuditEvent",
    "redact",
]
