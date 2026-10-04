# Phase 9I Recording Protocol — Multi-Speaker Real-Audio Validation

This environment has **no microphone, no second human speaker, and no local
offline TTS**, so the multi-speaker corpus cannot be produced here. Per the
global rules (no fabricated human benchmark data; no synthetic speech presented
as real-user evidence), 9I ships the **protocol + ingest infrastructure** and
performs the validations that are possible on the existing real corpus. Real
multi-speaker clips, when recorded by humans, drop into
`artifacts/phase9i/corpus/` and are picked up automatically.

## Capture format
- Mono, 16000 Hz, 16-bit PCM WAV (matches SayIt capture).
- Quiet room; natural pace; no over-enunciation.
- One utterance per file.

## Speakers
- Record with **≥ 3 speakers** (varied accent/gender/age where possible).
- Use **anonymous** speaker identifiers only: `S1`, `S2`, `S3`, …
- Do **not** collect names, emails, device IDs, or any identifying metadata.

## Required coverage (per speaker where practical)
ordinary English · developer terms · AI/ML · cybersecurity · cloud/devops ·
web dev · databases · proper names · ambiguous terms · multi-word entities ·
numbers/versions · ordinary phrases resembling technical terms · email/chat
language. Plus **targeted developer-context ambiguity** (the known 9H blocker):
e.g. "I need a fast API" (ordinary) vs "build it with FastAPI" (technical) in
developer vs email context.

## Per-clip manifest fields (filled in `labels.json`)
`speaker_id, clip_id, domain, context, reference, target_terms,
negative_terms, split` where `split ∈ {dev, holdout}`.

## Holdout discipline (anti-leakage)
- Mark ~half of clips `holdout`; never tune thresholds/weights against holdout
  references.
- Development tuning uses only `dev` clips.

## Ingest
1. Place `<clip_id>.wav` files in `artifacts/phase9i/corpus/`.
2. Add their rows to `artifacts/phase9i/labels.json`.
3. Run `uv run python tools/phase9i/validate.py` — it auto-detects/validates the
   clips (spec + non-silence), computes all metrics per-speaker/per-domain/
   per-context/per-split, and refreshes the gate.
