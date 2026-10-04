# Phase 6J — Manual Validation Procedure (custom vocabulary)

For a human running SayIt on real hardware with a model installed. The automated
suite verifies the matching engine, conflict detection, persistence, migration,
and the UI load/save on synthetic data. It cannot verify how your microphone and
model recognize your spoken forms, or how the final text lands in real apps.
That requires you.

> Custom vocabulary is **user-controlled**. Nothing is learned automatically;
> every entry is one you added. It is stored locally and never transmitted.

## Preconditions
- A model is installed (default: Parakeet TDT 0.6B v2 int8).
- Open Settings → Vocabulary.

## Procedure

1. **Add entries.** Add:
   - spoken `next js` → written `Next.js`
   - spoken `open ai` → written `OpenAI`
   - spoken `fast api` → written `FastAPI`
   - spoken `my project` → written `ShadowSync AI`
   Save settings.

2. **Persistence.** Fully quit SayIt from the tray and relaunch. Open Settings →
   Vocabulary and confirm all four entries are still present.

3. **Dictate each.** Hold the hotkey and say each spoken form in a sentence
   (e.g. "ship the next js app"). Confirm the inserted text uses the written
   form ("ship the Next.js app"). Record what you observed.

4. **Whole-word safety.** Dictate a sentence where the spoken form appears as a
   substring of a larger word if you can produce one; confirm it is NOT replaced
   inside another word.

5. **Enable/disable.** Disable one entry (uncheck "On"), save, dictate its
   spoken form, and confirm it is NOT replaced. Re-enable and confirm it works
   again.

6. **Edit.** Double-click a Written cell, change it, save, relaunch, confirm the
   change persisted.

7. **Delete.** Delete an entry, save, relaunch, confirm it is gone.

8. **Conflicts.** Add both `new` → `N` and `new york` → `NYC`. Confirm the
   "Overlapping forms (longer wins)" note appears, and that dictating "new york"
   yields "NYC" (the longer form wins).

9. **Insertion target.** Dictate into a plain text editor AND a browser text
   field; confirm the written forms land correctly at the cursor, exactly once.

## What to watch for
- A spoken form replaced **inside** an unrelated word (whole-word failure).
- Disabled entry still applying.
- Entries lost after restart (persistence failure).
- Any network activity (there should be none for vocabulary).

## Automated vs manual
- **AUTOMATED VERIFIED:** matching semantics (whole-word, multi-word,
  longest-first, case-insensitive), disabled handling, conflict detection,
  idempotency, explainability, settings persistence round-trip, legacy
  migration, UI add/load/save, and that vocabulary runs after Phase 6G/6I in the
  worker. Latency measured at 10/100/500/1000 entries.
- **USER PHYSICAL VALIDATION REQUIRED:** real-speech recognition of your spoken
  forms by your mic/model, and insertion into real editors/browsers. Not
  observed by the developer; you must check it.

## Sign-off
- Tester / machine / model / date:
- Overall: PASS / FAIL / MIXED (explain):
