"""Cryptographic authenticity + integrity for policy bundles.

Primary scheme: **Ed25519 asymmetric signatures** (RFC 8032) via the audited
``cryptography`` library. The administrator holds the Ed25519 *private* signing
key; desktop verifiers hold only the corresponding *public* key, which is safe
to distribute. This removes the shared-secret weakness of the previous HMAC
scheme (where every desktop verifier would need the secret and could therefore
forge bundles).

Legacy scheme: **HMAC-SHA256** over a canonical serialization. Retained ONLY
for backward compatibility and clearly labelled ``alg="HMAC-SHA256"``. It is a
shared-secret MAC: appropriate only when the same trusted party both signs and
verifies (e.g. a single admin workstation), NOT for distributing signed bundles
to many desktop clients. New bundles should use Ed25519.

Key management:
- ``TrustedKeyStore`` holds trusted keys by ``key_id``. Multiple ids may be
  trusted at once (supporting rotation). ``revoke`` removes a key id so bundles
  signed with it are rejected.
- Verification selects the key by the ``key_id`` embedded in the signature and
  the algorithm declared in ``alg``. An unknown/revoked id, a wrong algorithm
  for the stored key type, or any signature mismatch is rejected (fail-closed).

If ``cryptography`` is unavailable, Ed25519 signing/verification raise a clear
``IntegrityError`` (never a silent pass); HMAC continues to work with stdlib.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:  # Established, audited Ed25519 implementation.
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )

    _ED25519_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when dep missing
    _ED25519_AVAILABLE = False


class IntegrityError(Exception):
    """Raised when a bundle fails authenticity/integrity verification."""


def _canonical_bytes(payload: Any) -> bytes:
    """Deterministic serialization used for signing and verification."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Trusted key store (supports Ed25519 public keys + legacy HMAC secrets)
# ---------------------------------------------------------------------------
@dataclass
class _TrustedKey:
    kind: str  # "ed25519" | "hmac"
    material: Any  # Ed25519PublicKey | bytes


class TrustedKeyStore:
    """Holds trusted verification keys by id. Supports rotation + revocation."""

    def __init__(self, keys: Optional[Dict[str, bytes]] = None):
        # Back-compat: a plain {key_id: secret} dict is treated as HMAC keys.
        self._keys: Dict[str, _TrustedKey] = {}
        for kid, secret in (keys or {}).items():
            self.add_hmac_key(kid, secret)

    # -- Ed25519 (asymmetric; public key only on the verifier) -------------
    def add_ed25519_public_key(self, key_id: str, public_key_bytes: bytes) -> None:
        if not _ED25519_AVAILABLE:
            raise IntegrityError(
                "Ed25519 requires the 'cryptography' package, which is not "
                "installed."
            )
        if not key_id or not isinstance(key_id, str):
            raise ValueError("key_id must be a non-empty string.")
        if (
            not isinstance(public_key_bytes, (bytes, bytearray))
            or len(public_key_bytes) != 32
        ):
            raise ValueError("Ed25519 public key must be exactly 32 raw bytes.")
        pub = Ed25519PublicKey.from_public_bytes(bytes(public_key_bytes))
        self._keys[key_id] = _TrustedKey("ed25519", pub)

    # -- Legacy HMAC (shared secret) --------------------------------------
    def add_hmac_key(self, key_id: str, secret: bytes) -> None:
        if not key_id or not isinstance(key_id, str):
            raise ValueError("key_id must be a non-empty string.")
        if isinstance(secret, str):
            secret = secret.encode("utf-8")
        if not isinstance(secret, (bytes, bytearray)) or len(secret) < 16:
            raise ValueError("key secret must be >= 16 bytes.")
        self._keys[key_id] = _TrustedKey("hmac", bytes(secret))

    # Backwards-compatible alias used by older callers/tests.
    def add_key(self, key_id: str, secret: bytes) -> None:
        self.add_hmac_key(key_id, secret)

    def get(self, key_id: str) -> Optional[_TrustedKey]:
        return self._keys.get(key_id)

    def is_trusted(self, key_id: str) -> bool:
        return key_id in self._keys

    def revoke(self, key_id: str) -> None:
        self._keys.pop(key_id, None)


# ---------------------------------------------------------------------------
# Key generation (admin-side helper; private key never ships to desktops)
# ---------------------------------------------------------------------------
def generate_ed25519_keypair() -> tuple[bytes, bytes]:
    """Return (private_key_bytes, public_key_bytes) as raw 32-byte values.

    Admin keeps the private bytes secret; the public bytes are distributed to
    desktop verifiers via ``TrustedKeyStore.add_ed25519_public_key``.
    """
    if not _ED25519_AVAILABLE:
        raise IntegrityError(
            "Ed25519 requires the 'cryptography' package, which is not installed."
        )
    from cryptography.hazmat.primitives import serialization

    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv_raw, pub_raw


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------
def sign_bundle_ed25519(
    payload: Dict[str, Any], key_id: str, private_key_bytes: bytes
) -> Dict[str, Any]:
    """Sign a payload with an Ed25519 private key (admin side)."""
    if not _ED25519_AVAILABLE:
        raise IntegrityError(
            "Ed25519 requires the 'cryptography' package, which is not installed."
        )
    priv = Ed25519PrivateKey.from_private_bytes(bytes(private_key_bytes))
    sig = priv.sign(_canonical_bytes(payload)).hex()
    return {
        "payload": payload,
        "signature": {"alg": "Ed25519", "key_id": key_id, "sig": sig},
    }


def sign_bundle_hmac(
    payload: Dict[str, Any], key_id: str, secret: bytes
) -> Dict[str, Any]:
    """Legacy HMAC-SHA256 signing (shared secret). Prefer Ed25519 for new
    bundles distributed to desktop clients."""
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    mac = hmac.new(secret, _canonical_bytes(payload), hashlib.sha256).hexdigest()
    return {
        "payload": payload,
        "signature": {"alg": "HMAC-SHA256", "key_id": key_id, "mac": mac},
    }


# Default signer is the asymmetric scheme. Kept named ``sign_bundle`` for the
# existing public API; it now REQUIRES an Ed25519 private key.
def sign_bundle(
    payload: Dict[str, Any], key_id: str, key_material: bytes
) -> Dict[str, Any]:
    """Sign with Ed25519 (default). ``key_material`` is a raw Ed25519 private
    key (32 bytes). For the legacy shared-secret scheme use ``sign_bundle_hmac``.
    """
    return sign_bundle_ed25519(payload, key_id, key_material)


# ---------------------------------------------------------------------------
# Verification (algorithm auto-detected from the signature block)
# ---------------------------------------------------------------------------
def verify_bundle(bundle: Dict[str, Any], store: TrustedKeyStore) -> Dict[str, Any]:
    """Verify a signed bundle against the trusted key store.

    Supports ``alg="Ed25519"`` (asymmetric, preferred) and the legacy
    ``alg="HMAC-SHA256"``. Returns the authenticated ``payload`` on success.
    Raises ``IntegrityError`` for malformed structure, unsupported/mismatched
    algorithm, unknown/revoked key id, or any signature mismatch.
    """
    if (
        not isinstance(bundle, dict)
        or "payload" not in bundle
        or "signature" not in bundle
    ):
        raise IntegrityError("Malformed bundle: missing payload or signature.")

    sig = bundle["signature"]
    if not isinstance(sig, dict):
        raise IntegrityError("Malformed signature block.")

    alg = sig.get("alg")
    key_id = sig.get("key_id")
    if not isinstance(key_id, str):
        raise IntegrityError("Missing or invalid key_id.")

    trusted = store.get(key_id)
    if trusted is None:
        raise IntegrityError(f"Untrusted or unknown key_id: {key_id!r}.")

    message = _canonical_bytes(bundle["payload"])

    if alg == "Ed25519":
        if trusted.kind != "ed25519":
            raise IntegrityError(f"key_id {key_id!r} is not an Ed25519 key.")
        if not _ED25519_AVAILABLE:
            raise IntegrityError(
                "Ed25519 verification requires the 'cryptography' package."
            )
        sig_hex = sig.get("sig")
        if not isinstance(sig_hex, str) or not sig_hex:
            raise IntegrityError("Missing Ed25519 signature.")
        try:
            trusted.material.verify(bytes.fromhex(sig_hex), message)
        except (InvalidSignature, ValueError) as e:
            raise IntegrityError(
                "Signature mismatch: bundle is corrupt or tampered."
            ) from e
        return bundle["payload"]

    if alg == "HMAC-SHA256":
        if trusted.kind != "hmac":
            raise IntegrityError(f"key_id {key_id!r} is not an HMAC key.")
        provided_mac = sig.get("mac")
        if not isinstance(provided_mac, str) or not provided_mac:
            raise IntegrityError("Missing signature MAC.")
        expected = hmac.new(trusted.material, message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, provided_mac):
            raise IntegrityError("Signature mismatch: bundle is corrupt or tampered.")
        return bundle["payload"]

    raise IntegrityError(f"Unsupported signature algorithm: {alg!r}.")
