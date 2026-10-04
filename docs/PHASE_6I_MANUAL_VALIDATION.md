# Phase 6I — Manual Validation Procedure (context-aware formatting)

This is for a human running SayIt on real hardware with a model installed. The
automated suite verifies the formatting rules on deterministic synthetic text
and confirms the recorded A–F benchmark clips are left unchanged by Phase 6I.
It cannot verify how real dictated speech is recognized by your microphone/model
or how the final text lands in your editor. That requires you.

> Record only what you actually observe. Phase 6I formats **structured spoken
> expressions** (URLs, paths, emails, API/vN, versions). It deliberately leaves
> ordinary prose alone. If a structure is not recognized, that is the
> conservative design, not necessarily a bug.

## Preconditions
- A model is installed (default: Parakeet TDT 0.6B v2 int8).
- "Structured formatting" is enabled in Settings → Configuration (default on).

## Test matrix

| # | Category | Say this | Expected-ish result | Observed |
|---|----------|----------|---------------------|----------|
| 1 | Normal prose | "Let's meet tomorrow afternoon." | unchanged | |
| 2 | URL | "visit example dot com slash repo" | "example.com/repo" | |
| 3 | URL (brand) | "go to git hub dot com" | "GitHub.com" | |
| 4 | File path | "open src slash app dot py" | "src/app.py" | |
| 5 | Command words | "run git status" | unchanged words (no execution) | |
| 6 | Programming term | "deploy with next js" | "Next.js" | |
| 7 | Percentage | "ninety five percent" | "95%" | |
| 8 | Version | "version three point two" / "v one point two" | "3.2" / "v1.2" | |
| 9 | Date | "March fourteenth" | "March 14th" | |
| 10 | Email | "noah at example dot com" | "noah@example.com" | |
| 11 | Ambiguous "dot" | "put a dot here" | unchanged | |
| 12 | Ambiguous "slash"/"at" | "use a slash" / "meet me at noon" | unchanged | |

## What to watch for (failure modes)
- **Over-formatting:** ordinary prose turned into a URL/path/email. Report any
  such case; conservatism is the priority.
- **Brand casing:** "git hub dot com" becomes "GitHub.com" (canonical brand),
  not literal lowercase "github.com". This is expected.
- **Unknown TLD/extension not formatted** (e.g. "example dot banana"): expected
  — only known anchors are formatted.
- Text must still insert **exactly once** at the cursor (Phase 6H guarantee).

## Automated vs manual
- **AUTOMATED VERIFIED:** all rules above on synthetic text; A–F recorded clips
  unchanged by Phase 6I; sub-millisecond overhead; no WER regression vs 6G.
- **USER PHYSICAL VALIDATION REQUIRED:** real speech recognition of these
  structures by your mic/model, and insertion into real editors/browsers. Not
  observed by the developer; must be checked by you.

## Sign-off
- Tester / machine / model / date:
- Overall: PASS / FAIL / MIXED (explain):
