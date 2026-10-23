"""Unit tests for scripts/macos_signing.py — the pure CI signing decision logic.

Platform-independent. These lock in the credential-completeness and
outcome-based status rules that gate the macOS signing/notarization path in
.github/workflows/build.yml, including the core defect fix: a configured
identity NAME alone must NOT enable signing without an importable certificate.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _mod():
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return importlib.import_module("macos_signing")


# ---------------------------------------------------------------------------
# resolve_signing_context — credential completeness
# ---------------------------------------------------------------------------
def test_full_path_non_tag_can_sign_and_notarize():
    m = _mod()
    ctx = m.resolve_signing_context(
        have_cert=True, have_identity_name=True, have_notary=True, is_tag=False
    )
    assert ctx.can_sign is True
    assert ctx.should_notarize is True
    assert ctx.fail_fast is False
    assert ctx.status_precheck == m.SIGNED_NOTARIZED


def test_identity_name_without_certificate_cannot_sign():
    """THE DEFECT FIX: an identity name with no importable cert must not sign."""
    m = _mod()
    ctx = m.resolve_signing_context(
        have_cert=False, have_identity_name=True, have_notary=True, is_tag=False
    )
    assert ctx.can_sign is False
    assert ctx.should_notarize is False
    assert ctx.fail_fast is False  # non-tag: proceeds as unsigned dev
    assert ctx.status_precheck == m.UNSIGNED_DEV


def test_certificate_without_identity_name_cannot_sign():
    m = _mod()
    ctx = m.resolve_signing_context(
        have_cert=True, have_identity_name=False, have_notary=True, is_tag=False
    )
    assert ctx.can_sign is False
    assert ctx.should_notarize is False


def test_missing_notary_never_notarizes_even_if_signable():
    m = _mod()
    ctx = m.resolve_signing_context(
        have_cert=True, have_identity_name=True, have_notary=False, is_tag=False
    )
    assert ctx.can_sign is True          # can sign (Developer ID)
    assert ctx.should_notarize is False  # but never notarize without notary creds
    assert ctx.status_precheck == m.UNSIGNED_DEV


def test_no_credentials_non_tag_is_unsigned_dev():
    m = _mod()
    ctx = m.resolve_signing_context(
        have_cert=False, have_identity_name=False, have_notary=False, is_tag=False
    )
    assert ctx.can_sign is False
    assert ctx.should_notarize is False
    assert ctx.fail_fast is False
    assert ctx.status_precheck == m.UNSIGNED_DEV


# ---------------------------------------------------------------------------
# resolve_signing_context — tagged-release fail-fast
# ---------------------------------------------------------------------------
def test_tag_without_certificate_fails_fast():
    m = _mod()
    ctx = m.resolve_signing_context(
        have_cert=False, have_identity_name=True, have_notary=True, is_tag=True
    )
    assert ctx.fail_fast is True
    assert "MACOS_CERTIFICATE_P12_BASE64" in ctx.fail_reason


def test_tag_without_notary_fails_fast():
    m = _mod()
    ctx = m.resolve_signing_context(
        have_cert=True, have_identity_name=True, have_notary=False, is_tag=True
    )
    assert ctx.fail_fast is True
    assert "NOTARY" in ctx.fail_reason


def test_tag_without_identity_fails_fast():
    m = _mod()
    ctx = m.resolve_signing_context(
        have_cert=True, have_identity_name=False, have_notary=True, is_tag=True
    )
    assert ctx.fail_fast is True
    assert "MACOS_SIGN_IDENTITY" in ctx.fail_reason


def test_tag_with_full_path_does_not_fail_fast():
    m = _mod()
    ctx = m.resolve_signing_context(
        have_cert=True, have_identity_name=True, have_notary=True, is_tag=True
    )
    assert ctx.fail_fast is False
    assert ctx.should_notarize is True
    assert ctx.status_precheck == m.SIGNED_NOTARIZED


# ---------------------------------------------------------------------------
# final_signing_status — outcome-based (NOT presence-based)
# ---------------------------------------------------------------------------
def test_final_signed_notarized_only_when_all_succeed():
    m = _mod()
    assert (
        m.final_signing_status(
            signed=True, notarized=True, stapled=True, gatekeeper_ok=True
        )
        == m.SIGNED_NOTARIZED
    )


def test_final_unsigned_when_any_step_failed():
    m = _mod()
    # Each single failure degrades to unsigned-dev.
    for kw in ("signed", "notarized", "stapled", "gatekeeper_ok"):
        args = dict(signed=True, notarized=True, stapled=True, gatekeeper_ok=True)
        args[kw] = False
        assert m.final_signing_status(**args) == m.UNSIGNED_DEV, kw


def test_final_unsigned_when_nothing_ran():
    m = _mod()
    assert (
        m.final_signing_status(
            signed=False, notarized=False, stapled=False, gatekeeper_ok=False
        )
        == m.UNSIGNED_DEV
    )


# ---------------------------------------------------------------------------
# CLI contract (the workflow parses these exact lines / exit codes)
# ---------------------------------------------------------------------------
def test_cli_resolve_emits_outputs_and_zero_exit_on_ok():
    m = _mod()
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = m._main(
            ["resolve", "--have-cert", "true", "--have-identity", "true",
             "--have-notary", "true", "--is-tag", "false"]
        )
    out = buf.getvalue()
    assert rc == 0
    assert "can_sign=true" in out
    assert "should_notarize=true" in out
    assert "status_precheck=signed-notarized" in out


def test_cli_resolve_fail_fast_returns_exit_2():
    m = _mod()
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = m._main(
            ["resolve", "--have-cert", "false", "--have-identity", "true",
             "--have-notary", "true", "--is-tag", "true"]
        )
    assert rc == 2
    assert "fail_fast=true" in buf.getvalue()


def test_cli_final_emits_status():
    m = _mod()
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = m._main(
            ["final", "--signed", "true", "--notarized", "true",
             "--stapled", "true", "--gatekeeper", "true"]
        )
    assert rc == 0
    assert "signing_status=signed-notarized" in buf.getvalue()


def test_cli_bool_parsing_variants():
    m = _mod()
    assert m._b("true") and m._b("1") and m._b("YES") and m._b("y")
    assert not m._b("false") and not m._b("0") and not m._b("") and not m._b("no")
