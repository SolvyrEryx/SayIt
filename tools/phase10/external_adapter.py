"""Phase 10C — external-data evaluation adapters (VALIDATION ONLY).

Converts external benchmark corpora (Svarah, TIE) into one deterministic
evaluation manifest consumed by the SayIt validation harness. It does NOT ship
or bundle any dataset; it reads a local copy a human has placed under
``artifacts/phase10/external/<source>/`` and builds a manifest referencing those
files. If no external data is present, the adapter yields an empty manifest
(the harness then self-tests on the existing real corpus).

Common manifest entry schema:
    {
      "sample_id": str,
      "speaker_id": str,
      "reference": str,
      "source": "svarah" | "tie" | "sayit_corpus",
      "audio_path": str,            # absolute/local path (never bundled)
      "duration": float | None,
      "metadata": {...},            # source-specific (anonymous)
      "target_terms": [str, ...]    # technical/entity terms extracted from ref
    }

Deterministic: entries are sorted by (source, sample_id). Corrupted/missing
audio is recorded with a status flag and excluded from scored entries.
"""

from __future__ import annotations

import json
import re
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# A small, explicit technical-term extractor for references. It is deliberately
# conservative: it extracts tokens that look like technical entities (CamelCase,
# ALLCAPS acronyms, dotted/hyphenated identifiers, or multiword known phrases)
# WITHOUT consulting the SayIt knowledge base (so known/unseen stays unbiased).
_TECH_RE = re.compile(
    r"\b([A-Z][a-z]+[A-Z][A-Za-z0-9]*"      # CamelCase (FastAPI)
    r"|[A-Z]{2,}[0-9]*"                       # ALLCAPS acronym (TLS, OAuth2 upper)
    r"|[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+"  # dotted (Next.js)
    r"|[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+)"  # hyphenated (scikit-learn)
)


def extract_target_terms(reference: str) -> List[str]:
    """Extract candidate technical/entity terms from a reference transcript.
    Knowledge-base-independent so the known/unseen split is not biased."""
    if not reference:
        return []
    seen = set()
    out = []
    for m in _TECH_RE.finditer(reference):
        t = m.group(0)
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


@dataclass
class ManifestEntry:
    sample_id: str
    speaker_id: str
    reference: str
    source: str
    audio_path: str = ""
    duration: Optional[float] = None
    metadata: Dict = field(default_factory=dict)
    target_terms: List[str] = field(default_factory=list)
    audio_status: str = "unknown"   # ok | missing | corrupt

    def to_dict(self) -> dict:
        return {
            "sample_id": self.sample_id, "speaker_id": self.speaker_id,
            "reference": self.reference, "source": self.source,
            "audio_path": self.audio_path, "duration": self.duration,
            "metadata": self.metadata, "target_terms": self.target_terms,
            "audio_status": self.audio_status,
        }


def _check_audio(path: Path) -> (str, Optional[float]):
    if not path.exists():
        return "missing", None
    try:
        w = wave.open(str(path), "rb")
        n, sr = w.getnframes(), w.getframerate()
        w.close()
        if sr <= 0 or n <= 0:
            return "corrupt", None
        return "ok", round(n / sr, 3)
    except Exception:
        return "corrupt", None


def parse_svarah(root: Path) -> List[ManifestEntry]:
    """Parse a local Svarah copy. Manifest JSONL lines
    {"audio_filepath":…, "duration":…, "text":…}; speaker meta from
    meta_speaker_stats.csv if present."""
    entries: List[ManifestEntry] = []
    manifest = root / "svarah_manifest.json"
    if not manifest.exists():
        return entries
    for i, line in enumerate(manifest.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        ref = str(rec.get("text", "")).strip()
        ap = str(rec.get("audio_filepath", ""))
        apath = (root / ap) if ap and not Path(ap).is_absolute() else Path(ap)
        status, dur = _check_audio(apath)
        sid = Path(ap).stem or f"svarah_{i}"
        entries.append(ManifestEntry(
            sample_id=f"svarah_{sid}", speaker_id=sid.split('_')[0] if '_' in sid else "svarah",
            reference=ref, source="svarah", audio_path=str(apath),
            duration=rec.get("duration", dur), metadata={}, audio_status=status,
            target_terms=extract_target_terms(ref)))
    return entries


def parse_tie(root: Path) -> List[ManifestEntry]:
    """Parse a local TIE copy. Final_Dataset.csv metadata + Final_Transcripts/
    <id>_manual transcripts + Final_Dataset_audios/<id>.wav."""
    import csv
    entries: List[ManifestEntry] = []
    csv_path = root / "Final_Dataset.csv"
    if not csv_path.exists():
        return entries
    tr_dir = root / "Final_Transcripts"
    au_dir = root / "Final_Dataset_audios"
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            aid = (row.get("Audio_ID") or row.get("audio_id") or "").strip()
            if not aid:
                continue
            tr = tr_dir / f"{aid}_manual"
            ref = tr.read_text(encoding="utf-8").strip() if tr.exists() else ""
            apath = au_dir / f"{aid}.wav"
            status, dur = _check_audio(apath)
            entries.append(ManifestEntry(
                sample_id=f"tie_{aid}", speaker_id=aid, reference=ref,
                source="tie", audio_path=str(apath), duration=dur,
                metadata={"discipline": row.get("discipline_group", ""),
                          "region": row.get("region", "")},
                audio_status=status, target_terms=extract_target_terms(ref)))
    return entries


def parse_generic(root: Path, source: str) -> List[ManifestEntry]:
    """Parse a dataset a human has staged in a NORMALIZED form, so SayIt needs
    no dataset-specific library (e.g. HF `datasets`). Expected layout:

        <root>/manifest.csv   with columns: sample_id, speaker_id, text
                              (optional: audio, duration, <metadata...>)
        <root>/audio/<sample_id>.wav   (or the 'audio' column path)

    OR a JSONL `<root>/manifest.jsonl` with the same fields. References are used
    verbatim (never altered). Returns [] if no manifest is present.
    """
    import csv as _csv
    entries: List[ManifestEntry] = []
    csvp = root / "manifest.csv"
    jsonl = root / "manifest.jsonl"
    rows: List[dict] = []
    if csvp.exists():
        with open(csvp, encoding="utf-8") as f:
            rows = list(_csv.DictReader(f))
    elif jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    else:
        return entries
    for i, row in enumerate(rows):
        sid = str(row.get("sample_id") or f"{source}_{i}")
        ref = str(row.get("text") or row.get("reference") or "").strip()
        ap = row.get("audio") or f"audio/{sid}.wav"
        apath = (root / ap) if not Path(str(ap)).is_absolute() else Path(str(ap))
        status, dur = _check_audio(apath)
        meta = {k: v for k, v in row.items()
                if k not in ("sample_id", "speaker_id", "text", "reference", "audio", "duration")}
        entries.append(ManifestEntry(
            sample_id=f"{source}_{sid}", speaker_id=str(row.get("speaker_id") or source),
            reference=ref, source=source, audio_path=str(apath),
            duration=row.get("duration", dur), metadata=meta,
            audio_status=status, target_terms=extract_target_terms(ref)))
    return entries


def build_manifest(external_root: Path) -> List[ManifestEntry]:
    """Build the deterministic manifest from any external corpora present.

    Supports each source in its native documented layout OR a normalized staged
    form (manifest.csv / manifest.jsonl). This lets a human stage gated/large
    datasets (Svarah, TIE_shorts) after a manual download without SayIt adding a
    dataset-download dependency.
    """
    entries: List[ManifestEntry] = []
    sv = external_root / "svarah"
    tie = external_root / "tie"
    tie_shorts = external_root / "tie_shorts"
    if sv.exists():
        entries += parse_svarah(sv)
        entries += parse_generic(sv, "svarah")
    if tie.exists():
        entries += parse_tie(tie)
        entries += parse_generic(tie, "tie")
    if tie_shorts.exists():
        entries += parse_generic(tie_shorts, "tie_shorts")
    # De-duplicate by sample_id (native + generic may both match); first wins.
    seen = set()
    deduped = []
    for e in entries:
        if e.sample_id in seen:
            continue
        seen.add(e.sample_id)
        deduped.append(e)
    deduped.sort(key=lambda e: (e.source, e.sample_id))
    return deduped


def scored_entries(entries: List[ManifestEntry]) -> List[ManifestEntry]:
    return [e for e in entries if e.audio_status == "ok"]
