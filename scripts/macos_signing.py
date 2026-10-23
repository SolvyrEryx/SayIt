"""Pure decision logic for the macOS CI signing / notarization gate.

This module contains NO macOS/keychain side effects. It exists so the
credential-completeness and signing-status rules that gate the ``build-macos``
job in ``.github/workflows/build.yml`` are unit-testable on any platform,
instead of living only as un-testable inline shell.

Two independent decisions:

1. :func:`resolve_signing_context` — BEFORE the build. Given which credentials
   are present (as booleans derived from secret presence) and whether this is a
   tagged release, decide whether the build can produce a real Developer ID
   signed + notarized artifact, whether it must remain an explicit unsigned
   development build, or whether the job must fail fast.

   Crucially, ``can_sign`` requires BOTH the signing identity NAME *and* an
   importable certificate (p12 + password). A configured identity name alone
   does NOT make signing possible on a fresh runner whose keychain has no
   private key — that was the original defect.

2. :func:`final_signing_status` — AFTER the build/notarize steps. The published
   ``SIGNING_STATUS`` marker must reflect the steps that ACTUALLY SUCCEEDED, not
   merely the presence of secrets. ``signed-notarized`` is returned only when
   signing, notarization, stapling, and Gatekeeper assessment all succeeded.
"""

from __future__ import annotations

from dataclasses import dataclass

# Signing status marker values. These strings are written to
# SIGNING_STATUS-<arch>.txt and the release job refuses to publish anything that
# is not exactly SIGNED_NOTARIZED.
SIGNED_NOTARIZED = "signed-notarized"
UNSIGNED_DEV = "unsigned-dev"


@dataclass(frozen=True)
class SigningContext:
    """Result of the pre-build signing decision.

    Attributes:
        can_sign: True only if a REAL Developer ID signature is possible, i.e.
            the identity name AND an importable certificate (p12 + password)
            are all present. Drives whether the cert-import step runs and
            whether Briefcase is given ``--identity`` vs ``--adhoc-sign``.
        should_notarize: True only if ``can_sign`` AND notary creds are present.
            Never notarize an ad-hoc-signed app.
        fail_fast: True if the job must fail before the expensive build.
        fail_reason: Human-readable reason when ``fail_fast`` is True, else "".
        status_precheck: The BEST-CASE status this configuration could reach
            (signed-notarized when should_notarize else unsigned-dev). This is
            NOT the published status; the published status is decided after the
            fact by :func:`final_signing_status`.
    """

    can_sign: bool
    should_notarize: bool
    fail_fast: bool
    fail_reason: str
    status_precheck: str


def resolve_signing_context(
    *,
    have_cert: bool,
    have_identity_name: bool,
    have_notary: bool,
    is_tag: bool,
) -> SigningContext:
    """Decide the pre-build signing context.

    Args:
        have_cert: The certificate p12 (base64) AND its password are both
            configured (an importable Developer ID cert + private key).
        have_identity_name: ``MACOS_SIGN_IDENTITY`` (the identity name) is set.
        have_notary: All three notary secrets are set.
        is_tag: This build is a ``refs/tags/v*`` public release build.

    Rules:
        * Real signing requires BOTH an importable certificate AND the identity
          name. An identity name alone is insufficient (fresh-runner keychain
          has no key).
        * Notarization requires real signing AND notary creds. Never notarize
          an ad-hoc build.
        * A TAGGED release must have a fully working signed+notarized path
          (cert + identity + notary); otherwise fail fast, before the long
          build, rather than publish or waste a build.
        * A non-tag build with incomplete/absent signing config does NOT fail;
          it proceeds as an explicit unsigned development build.
        * A non-tag build that has a certificate but a broken/partial
          configuration (e.g. cert present but no identity name, or cert
          present but notary missing while identity present) must not silently
          mislabel itself; it stays unsigned-dev unless the FULL signed path is
          available.
    """
    can_sign = bool(have_cert and have_identity_name)
    should_notarize = bool(can_sign and have_notary)
    status_precheck = SIGNED_NOTARIZED if should_notarize else UNSIGNED_DEV

    fail_fast = False
    fail_reason = ""
    if is_tag and not should_notarize:
        missing = []
        if not have_cert:
            missing.append(
                "MACOS_CERTIFICATE_P12_BASE64/MACOS_CERTIFICATE_PASSWORD"
            )
        if not have_identity_name:
            missing.append("MACOS_SIGN_IDENTITY")
        if not have_notary:
            missing.append(
                "MACOS_NOTARY_API_KEY/_ID/_ISSUER"
            )
        fail_fast = True
        fail_reason = (
            "Tagged release build but a signed+notarized macOS artifact is not "
            "possible; missing/incomplete: " + ", ".join(missing) + ". A public "
            "macOS release must be Developer ID signed AND notarized. Failing "
            "before the build instead of shipping an unsigned DMG."
        )

    return SigningContext(
        can_sign=can_sign,
        should_notarize=should_notarize,
        fail_fast=fail_fast,
        fail_reason=fail_reason,
        status_precheck=status_precheck,
    )


def final_signing_status(
    *,
    signed: bool,
    notarized: bool,
    stapled: bool,
    gatekeeper_ok: bool,
) -> str:
    """Return the status marker to PUBLISH, based on actual step outcomes.

    ``signed-notarized`` is returned only when every release-grade step
    succeeded: Developer ID signing, notarization, stapling, and Gatekeeper
    assessment. Any failure or skipped step yields ``unsigned-dev`` so the
    release job never publishes an artifact whose signing chain is incomplete.
    """
    if signed and notarized and stapled and gatekeeper_ok:
        return SIGNED_NOTARIZED
    return UNSIGNED_DEV


def _b(s: str) -> bool:
    """Parse a shell-passed boolean ('true'/'1'/'yes' -> True)."""
    return str(s).strip().lower() in {"true", "1", "yes", "y"}


def _main(argv: list[str]) -> int:
    """Tiny CLI so the workflow can call the pure logic without inlining it.

    Usage:
      resolve  --have-cert B --have-identity B --have-notary B --is-tag B
          -> prints GitHub-Actions ``key=value`` output lines:
             can_sign, should_notarize, fail_fast, status_precheck, fail_reason
          exits non-zero (2) when fail_fast is True.
      final    --signed B --notarized B --stapled B --gatekeeper B
          -> prints ``signing_status=<value>``.
    """
    import argparse

    ap = argparse.ArgumentParser(description="macOS signing-context decider")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("resolve")
    for name in ("have-cert", "have-identity", "have-notary", "is-tag"):
        r.add_argument(f"--{name}", default="false")

    f = sub.add_parser("final")
    for name in ("signed", "notarized", "stapled", "gatekeeper"):
        f.add_argument(f"--{name}", default="false")

    args = ap.parse_args(argv)

    if args.cmd == "resolve":
        ctx = resolve_signing_context(
            have_cert=_b(args.have_cert),
            have_identity_name=_b(args.have_identity),
            have_notary=_b(args.have_notary),
            is_tag=_b(args.is_tag),
        )
        print(f"can_sign={'true' if ctx.can_sign else 'false'}")
        print(f"should_notarize={'true' if ctx.should_notarize else 'false'}")
        print(f"fail_fast={'true' if ctx.fail_fast else 'false'}")
        print(f"status_precheck={ctx.status_precheck}")
        # fail_reason is a single line (no secrets); safe to echo.
        print(f"fail_reason={ctx.fail_reason}")
        return 2 if ctx.fail_fast else 0

    status = final_signing_status(
        signed=_b(args.signed),
        notarized=_b(args.notarized),
        stapled=_b(args.stapled),
        gatekeeper_ok=_b(args.gatekeeper),
    )
    print(f"signing_status={status}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(_main(sys.argv[1:]))
