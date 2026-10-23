"""Structured, redacted audit logging for enterprise/security events.

Records administrative and security-relevant actions (login/logout, policy
import/validation/change, admin actions, licence/seat changes, security-setting
changes, integrity-validation failures) with safe metadata only.

Hard privacy rule (enforced, not just documented):
    Microphone audio and dictated transcript content are NEVER written to the
    audit log. ``redact`` strips known-sensitive keys and the writer refuses to
    serialize banned fields. This keeps the audit trail safe to collect
    centrally while local transcription stays private.

The log is append-only JSONL. Access control is enforced at the OS layer by
creating the file with owner-only permissions where the platform supports it.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Keys that must never appear in an audit record. If present in supplied
# metadata they are dropped and replaced with a redaction marker. These cover
# transcript/audio content and common secret-bearing fields.
_BANNED_KEYS = {
    "transcript",
    "transcript_text",
    "raw_text",
    "enhanced_text",
    "text",
    "audio",
    "audio_data",
    "waveform",
    "samples",
    "api_key",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
}

_REDACTION_MARKER = "[redacted]"


def redact(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a copy of ``metadata`` with banned/sensitive keys removed.

    Redaction is case-insensitive and recursive for nested dicts. A dropped key
    is recorded under ``_redacted`` so audits remain honest about what was
    withheld without leaking the value.
    """
    if not metadata:
        return {}
    clean: Dict[str, Any] = {}
    dropped = []
    for key, value in metadata.items():
        if not isinstance(key, str):
            continue
        if key.lower() in _BANNED_KEYS:
            dropped.append(key)
            continue
        if isinstance(value, dict):
            clean[key] = redact(value)
        else:
            clean[key] = value
    if dropped:
        clean["_redacted"] = sorted(dropped)
    return clean


@dataclass
class AuditEvent:
    action: str  # e.g. "policy.import", "auth.login"
    actor: str = "unknown"  # user/admin identifier (not a secret)
    result: str = "success"  # "success" | "failure" | "denied"
    policy_version: Optional[int] = None
    org_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[str] = None  # ISO-8601 UTC; filled at write time

    def to_record(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(),
            "action": self.action,
            "actor": self.actor,
            "result": self.result,
            "org_id": self.org_id,
            "policy_version": self.policy_version,
            "metadata": redact(self.metadata),
        }


class AuditLog:
    """Append-only JSONL audit log with owner-only file permissions."""

    def __init__(self, path: str):
        self._path = path
        directory = os.path.dirname(os.path.abspath(path)) or "."
        os.makedirs(directory, exist_ok=True)
        if not os.path.exists(path):
            # Create empty with restrictive permissions where supported.
            fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
        self._restrict_permissions()

    def _restrict_permissions(self) -> None:
        try:
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)
        except (OSError, NotImplementedError):
            # Best-effort; some filesystems/platforms don't support chmod.
            pass

    def record(self, event: AuditEvent) -> Dict[str, Any]:
        """Append one event. Returns the written (redacted) record."""
        rec = event.to_record()
        line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return rec

    def read_all(self) -> list[Dict[str, Any]]:
        """Read all records (admin/diagnostic use)."""
        if not os.path.exists(self._path):
            return []
        out = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return out


class TamperEvidentAuditLog(AuditLog):
    """Hash-chained audit log — tamper-EVIDENT (not merely append-only).

    Each record stores ``prev_hash`` and ``entry_hash`` where
        entry_hash = sha256(prev_hash + canonical(record_without_hash)).
    Any retroactive edit, reordering, or deletion of an interior record breaks
    the chain, which ``verify_chain`` detects. This is the distinction the
    enterprise spec requires:

    - ``AuditLog`` (base): ordinary append-only logging. Cheap, but an actor
      with file write access can silently alter past lines.
    - ``TamperEvidentAuditLog``: edits/removals become *detectable* via the
      chain. (It is tamper-evident, not tamper-proof: a sufficiently privileged
      actor could recompute the whole chain. True tamper-RESISTANCE requires
      append-only external storage or a signed/anchored log, documented as a
      server-side concern.)
    """

    _GENESIS = "0" * 64

    def _last_hash(self) -> str:
        records = self.read_all()
        if not records:
            return self._GENESIS
        return records[-1].get("entry_hash", self._GENESIS)

    def record(self, event: AuditEvent) -> Dict[str, Any]:
        rec = event.to_record()
        prev = self._last_hash()
        rec["prev_hash"] = prev
        chain_input = (
            prev
            + json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        ).encode("utf-8")
        rec["entry_hash"] = hashlib.sha256(chain_input).hexdigest()
        line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return rec

    def verify_chain(self) -> bool:
        """Return True iff the hash chain is intact (no record was altered,
        reordered, or removed)."""
        prev = self._GENESIS
        for rec in self.read_all():
            if rec.get("prev_hash") != prev:
                return False
            stored = rec.get("entry_hash")
            recomputed_src = dict(rec)
            recomputed_src.pop("entry_hash", None)
            chain_input = (
                prev
                + json.dumps(
                    recomputed_src,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            ).encode("utf-8")
            if hashlib.sha256(chain_input).hexdigest() != stored:
                return False
            prev = stored
        return True
