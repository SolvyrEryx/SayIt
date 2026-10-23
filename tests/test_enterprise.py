"""Tests for the modular enterprise foundation.

Covers genuine behaviour (not simulated): policy precedence + admin-lock
enforcement, schema validation, cryptographic tamper/untrusted-key rejection,
offline bundle import with rollback protection, and audit redaction that never
records transcript/audio/secret content.
"""

import os

import pytest

from src.sayit.core.enterprise import (
    AuditEvent,
    AuditLog,
    OrgPolicy,
    PolicyImportError,
    PolicyLayer,
    PolicyValidationError,
    TrustedKeyStore,
    export_bundle,
    generate_ed25519_keypair,
    import_policy_bundle,
    redact,
    resolve_policies,
    sign_bundle_hmac,
    validate_policy,
    verify_bundle,
)
from src.sayit.core.enterprise.integrity import IntegrityError

SECRET = b"0123456789abcdef0123456789abcdef"
# Admin-side Ed25519 keypair; only the PUBLIC key goes into the verifier store.
PRIV, PUB = generate_ed25519_keypair()


def _ed25519_store():
    s = TrustedKeyStore()
    s.add_ed25519_public_key("k1", PUB)
    return s


def _admin_policy(version=3):
    return OrgPolicy(
        org_id="acme",
        version=version,
        layer=PolicyLayer.ADMIN,
        vocabulary={"k eight s": "Kubernetes"},
        correction_rules=[{"from": "node js", "to": "Node.js"}],
        feature_flags={"cloud_enhancement": False},
        locked_settings={"history_enabled": False},
    )


class TestPolicyPrecedence:
    def test_security_lock_overrides_user(self):
        sec = OrgPolicy(
            org_id="acme",
            version=1,
            layer=PolicyLayer.SECURITY,
            locked_settings={"history_enabled": False},
        )
        res = resolve_policies([sec], user_settings={"history_enabled": True})
        assert res.effective_settings["history_enabled"] is False
        assert res.is_locked("history_enabled")

    def test_user_value_kept_when_not_locked(self):
        res = resolve_policies([_admin_policy()], user_settings={"theme": "dark"})
        assert res.effective_settings["theme"] == "dark"
        assert not res.is_locked("theme")

    def test_higher_version_wins_within_layer(self):
        p_old = OrgPolicy(
            org_id="acme",
            version=1,
            layer=PolicyLayer.ADMIN,
            locked_settings={"x": "old"},
        )
        p_new = OrgPolicy(
            org_id="acme",
            version=5,
            layer=PolicyLayer.ADMIN,
            locked_settings={"x": "new"},
        )
        res = resolve_policies([p_new, p_old])
        assert res.effective_settings["x"] == "new"
        assert res.provenance["x"] == (PolicyLayer.ADMIN, 5)

    def test_vocabulary_merged(self):
        res = resolve_policies([_admin_policy()], user_vocabulary={"a": "A"})
        assert res.vocabulary["k eight s"] == "Kubernetes"
        assert res.vocabulary["a"] == "A"


class TestPolicyValidation:
    def test_rejects_unsupported_schema_major(self):
        p = _admin_policy()
        p.schema_version = "99.0"
        with pytest.raises(PolicyValidationError):
            validate_policy(p)

    def test_rejects_bad_vocabulary(self):
        p = _admin_policy()
        p.vocabulary = {"ok": 123}  # non-string value
        with pytest.raises(PolicyValidationError):
            validate_policy(p)

    def test_rejects_bad_feature_flag(self):
        p = _admin_policy()
        p.feature_flags = {"x": "yes"}  # not a bool
        with pytest.raises(PolicyValidationError):
            validate_policy(p)


class TestIntegrityEd25519:
    """Primary scheme: asymmetric. Verifier holds only the public key."""

    def test_sign_then_verify_roundtrip(self):
        store = _ed25519_store()
        bundle = export_bundle([_admin_policy()], "k1", PRIV)  # Ed25519 default
        assert bundle["signature"]["alg"] == "Ed25519"
        payload = verify_bundle(bundle, store)
        assert payload["policies"][0]["org_id"] == "acme"

    def test_tampered_payload_rejected(self):
        store = _ed25519_store()
        bundle = export_bundle([_admin_policy()], "k1", PRIV)
        bundle["payload"]["policies"][0]["version"] = 999
        with pytest.raises(IntegrityError):
            verify_bundle(bundle, store)

    def test_untrusted_key_rejected(self):
        store = _ed25519_store()
        bundle = export_bundle([_admin_policy()], "other", PRIV)
        with pytest.raises(IntegrityError):
            verify_bundle(bundle, store)

    def test_revoked_key_rejected(self):
        store = _ed25519_store()
        bundle = export_bundle([_admin_policy()], "k1", PRIV)
        store.revoke("k1")
        with pytest.raises(IntegrityError):
            verify_bundle(bundle, store)

    def test_wrong_private_key_rejected(self):
        # A bundle signed by a DIFFERENT private key must not verify against the
        # trusted public key (core asymmetric guarantee).
        other_priv, _ = generate_ed25519_keypair()
        store = _ed25519_store()
        bundle = export_bundle([_admin_policy()], "k1", other_priv)
        with pytest.raises(IntegrityError):
            verify_bundle(bundle, store)

    def test_public_key_cannot_forge(self):
        # The verifier's store only has the PUBLIC key; it carries no signing
        # material, so a desktop client cannot produce a valid signature.
        store = _ed25519_store()
        tk = store.get("k1")
        assert tk.kind == "ed25519"
        # The stored object is a public key with no private bytes exposed.
        assert not hasattr(tk.material, "private_bytes")


class TestIntegrityHmacLegacy:
    """Legacy shared-secret scheme retained for backward compatibility."""

    def test_hmac_roundtrip(self):
        store = TrustedKeyStore({"h1": SECRET})
        bundle = export_bundle([_admin_policy()], "h1", SECRET, alg="HMAC-SHA256")
        assert bundle["signature"]["alg"] == "HMAC-SHA256"
        payload = verify_bundle(bundle, store)
        assert payload["policies"][0]["org_id"] == "acme"

    def test_hmac_tamper_rejected(self):
        store = TrustedKeyStore({"h1": SECRET})
        bundle = sign_bundle_hmac(
            {"policies": [_admin_policy().to_dict()]}, "h1", SECRET
        )
        bundle["payload"]["policies"][0]["version"] = 999
        with pytest.raises(IntegrityError):
            verify_bundle(bundle, store)

    def test_algorithm_keytype_mismatch_rejected(self):
        # An Ed25519-trusted key id must not verify an HMAC bundle and vice versa.
        store = _ed25519_store()
        bundle = export_bundle([_admin_policy()], "k1", SECRET, alg="HMAC-SHA256")
        with pytest.raises(IntegrityError):
            verify_bundle(bundle, store)


class TestOfflineImport:
    def test_import_from_file(self, tmp_path):
        from src.sayit.core.enterprise.distribution import write_bundle_file

        store = _ed25519_store()
        bundle = export_bundle([_admin_policy()], "k1", PRIV)
        path = tmp_path / "policy.bundle.json"
        write_bundle_file(bundle, str(path))
        policies = import_policy_bundle(str(path), store)
        assert policies[0].org_id == "acme"

    def test_import_rejects_stale_version(self):
        store = _ed25519_store()
        bundle = export_bundle([_admin_policy(version=2)], "k1", PRIV)
        with pytest.raises(PolicyImportError):
            import_policy_bundle(bundle, store, current_versions={"acme": 5})

    def test_import_missing_file(self, tmp_path):
        store = TrustedKeyStore({"k1": SECRET})
        with pytest.raises(PolicyImportError):
            import_policy_bundle(str(tmp_path / "nope.json"), store)


class TestAuditRedaction:
    def test_redact_strips_transcript_and_secrets(self):
        out = redact(
            {
                "transcript": "hello",
                "api_key": "X",
                "actor": "admin",
                "nested": {"token": "t", "ok": 1},
            }
        )
        assert "transcript" not in out
        assert "api_key" not in out
        assert out["actor"] == "admin"
        assert "token" not in out["nested"]
        assert out["nested"]["ok"] == 1
        assert "transcript" in out["_redacted"] and "api_key" in out["_redacted"]

    def test_audit_log_never_writes_transcript(self, tmp_path):
        log = AuditLog(str(tmp_path / "audit.jsonl"))
        rec = log.record(
            AuditEvent(
                action="policy.import",
                actor="admin@acme",
                result="success",
                org_id="acme",
                policy_version=3,
                metadata={"transcript": "secret speech", "note": "ok"},
            )
        )
        assert "transcript" not in rec["metadata"]
        assert rec["metadata"]["note"] == "ok"
        # On-disk content must not contain the transcript text.
        content = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
        assert "secret speech" not in content
        assert "policy.import" in content

    def test_integrity_failure_event_recorded(self, tmp_path):
        log = AuditLog(str(tmp_path / "audit.jsonl"))
        rec = log.record(
            AuditEvent(
                action="policy.integrity_check",
                result="failure",
                metadata={"reason": "signature_mismatch"},
            )
        )
        assert rec["result"] == "failure"
        assert rec["metadata"]["reason"] == "signature_mismatch"


class TestTamperEvidentAudit:
    def test_chain_intact_after_appends(self, tmp_path):
        from src.sayit.core.enterprise import TamperEvidentAuditLog

        log = TamperEvidentAuditLog(str(tmp_path / "chain.jsonl"))
        log.record(AuditEvent(action="auth.login", actor="a"))
        log.record(AuditEvent(action="policy.import", actor="a", policy_version=3))
        log.record(AuditEvent(action="auth.logout", actor="a"))
        assert log.verify_chain() is True

    def test_detects_retroactive_edit(self, tmp_path):
        from src.sayit.core.enterprise import TamperEvidentAuditLog

        path = tmp_path / "chain.jsonl"
        log = TamperEvidentAuditLog(str(path))
        log.record(AuditEvent(action="auth.login", actor="a"))
        log.record(AuditEvent(action="policy.import", actor="a", policy_version=3))
        # Tamper: rewrite the first line's action.
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0].replace("auth.login", "auth.superadmin")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert log.verify_chain() is False

    def test_detects_deleted_record(self, tmp_path):
        from src.sayit.core.enterprise import TamperEvidentAuditLog

        path = tmp_path / "chain.jsonl"
        log = TamperEvidentAuditLog(str(path))
        log.record(AuditEvent(action="a1"))
        log.record(AuditEvent(action="a2"))
        log.record(AuditEvent(action="a3"))
        lines = path.read_text(encoding="utf-8").splitlines()
        del lines[1]  # remove interior record
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert log.verify_chain() is False

    def test_tamper_evident_log_still_redacts(self, tmp_path):
        from src.sayit.core.enterprise import TamperEvidentAuditLog

        log = TamperEvidentAuditLog(str(tmp_path / "chain.jsonl"))
        rec = log.record(
            AuditEvent(action="policy.import", metadata={"transcript": "x", "ok": 1})
        )
        assert "transcript" not in rec["metadata"]
        assert rec["metadata"]["ok"] == 1
