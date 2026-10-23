# SayIt v0.2.0 — Final Release Gate

Status snapshot for the v0.2.0 release candidate. This document separates what
**CI has objectively validated** from what still requires **real hardware** or
**owner-configured secrets**. It does not claim any manual or signing result
that has not actually been produced.

- PR: #9 (open, **draft**) — do not merge/tag/publish/deploy from it.
- CI-validated code commit: `33a323c` — run
  [39946798291](https://github.com/VptrCipher/SayIt/actions/runs/39946798291),
  **all five jobs green**. (Branch head `11da61a` adds docs only; no code,
  workflow, or packaging change.)

---

## 1. What CI has objectively validated (automated, no human)

| Check | Evidence |
|---|---|
| Python test suite (non-slow) | `Run Tests` job — success |
| Windows online + offline installers build + validate + checksum | `Build Windows Installers` — success |
| Linux AppImage build + smoke test + size/ELF/name validation + checksum | `Build Linux AppImage (x64)` — success |
| macOS **arm64** .app + both DMG variants (dynamic payload-sized `hdiutil`), native-arch check, bundled-model integrity gate, DMG mount + payload verification | `Build macOS (arm64)` on `macos-14` — success |
| macOS **x86_64** — same as above | `Build macOS (x86_64)` on `macos-15-intel` — success |
| Offline bundled-model integrity (4 INT8 models, per-file SHA-256) | `Fetch + verify bundled models` + in-build `gate_offline_contents` — success, both archs |

**Not covered by CI:** live microphone, OS permission prompts, real
keystroke/clipboard insertion into other apps, notification delivery, and
signed/notarized distribution. Those are in sections 2–3.

---

## 2. Platform acceptance matrix (MANUAL — NOT yet performed)

Run on real hardware with an **installed** build. Record pass/fail + notes per
cell. Do not mark any cell without running it. CI success does **not** satisfy
these.

| Acceptance item | macOS arm64 | macOS Intel | Linux X11 | Linux Wayland |
|---|---|---|---|---|
| Microphone permission prompt + honest denial handling | ☐ | ☐ | ☐ (n/a prompt; device access) | ☐ (n/a prompt; device access) |
| Global hotkey registers (Accessibility/Input Monitoring on macOS; portal on Wayland) | ☐ | ☐ | ☐ | ☐ |
| Hold-to-record / release-to-transcribe | ☐ | ☐ | ☐ | ☐ |
| Esc cancels active recording AND in-flight transcription | ☐ | ☐ | ☐ | ☐ |
| Real transcription produces usable text (real model) | ☐ | ☐ | ☐ | ☐ |
| Clipboard insertion at cursor in representative apps (list apps) | ☐ (Cmd+V) | ☐ (Cmd+V) | ☐ (`xclip`/`xsel`) | ☐ (`wl-clipboard`; else clipboard-only + paste notice) |
| Notifications appear (Notification Center / desktop service) | ☐ | ☐ | ☐ | ☐ |
| Offline models available with NO network; 4 expected models present in package | ☐ | ☐ | ☐ | ☐ |
| Restart behavior: app relaunches; custom hotkey persists + re-registers; no stuck Recording/Processing state | ☐ | ☐ | ☐ | ☐ |
| Gatekeeper first-launch matches the build's real signing status | ☐ | ☐ | n/a | n/a |

Environment required: a physical (or fully-provisioned VM) macOS 14+ Apple
Silicon machine, a macOS 13+/15 Intel machine, and a Linux box able to run both
an X11 session and a Wayland session (e.g. GNOME on both). Owner / QA performs
these; they cannot be run in this headless environment.

---

## 3. macOS signing + notarization — safe non-publishing test path

### 3.1 Owner action (one-time secret configuration)
Configure four **repository secrets** (names only — never paste values into
chat, logs, or commits). See `RELEASE_CHECKLIST.md` for how to obtain each:
`MACOS_SIGN_IDENTITY`, `MACOS_NOTARY_API_KEY`, `MACOS_NOTARY_API_KEY_ID`,
`MACOS_NOTARY_API_ISSUER`. Required **together** for notarization.

### 3.2 Why a manual dispatch is safe (verified against the workflow)
The `release` job in `.github/workflows/build.yml` runs only if:

```
github.event_name == 'release'
  || startsWith(github.ref, 'refs/tags/v')
  || (github.ref == 'refs/heads/main' && contains(head_commit.message, '[release]'))
```

For a **`workflow_dispatch` of "Build Desktop App" on `feature/v0.2.0-work`**:
- event is `workflow_dispatch` (not `release`) → clause 1 false;
- ref is `refs/heads/feature/v0.2.0-work` (not a `v*` tag) → clause 2 false;
- ref is not `refs/heads/main` → clause 3 false.

→ **The release job does not run; nothing is published.** The `website-deploy`
workflow is a *separate* workflow; dispatching "Build Desktop App" does not
start it — do **not** dispatch "Deploy Website".

The signing step is gated on `have_notary == true`, **independent of tag
status** (see the `Determine release/signing context` step). So a dispatch with
the secrets present will **sign + notarize + staple + Gatekeeper-assess** both
DMGs and mark them `signed-notarized`, while the public release job stays
dormant. The fast-fail-on-missing-secrets branch only triggers when
`is_tag=true`, so a dispatch never fails for absent secrets.

### 3.3 Safe invocation
1. Owner configures the four secrets (section 3.1).
2. Actions → **Build Desktop App** → **Run workflow** → branch
   `feature/v0.2.0-work`. (Do NOT run "Deploy Website". Do NOT push a `v*` tag.)
3. Watch `build-macos` (arm64 + x86_64). Expect `Determine release/signing
   context` to emit `have_sign=true`, `have_notary=true` (booleans only), the
   `Notarize, staple, and verify (Gatekeeper)` step to RUN (not skip), and the
   `SIGNING_STATUS-<arch>.txt` marker to read `signed-notarized`.

### 3.4 How to verify signing / notarization / stapling / Gatekeeper (both archs)
On a macOS machine, per downloaded DMG (and the `.app` inside):

```bash
# 1) Code signature on the .app is valid and from the Developer ID identity
codesign --verify --deep --strict --verbose=2 "/Volumes/SayIt/SayIt.app"
codesign -dv --verbose=4 "/Volumes/SayIt/SayIt.app"   # check Authority / TeamID

# 2) Notarization + stapling of the DMG (offline-validatable ticket)
xcrun stapler validate -v SayIt-macOS-arm64.dmg
xcrun stapler validate -v SayIt-macOS-x86_64.dmg

# 3) Gatekeeper acceptance
spctl --assess --type open --context context:primary-signature -vv SayIt-macOS-arm64.dmg
spctl --assess --type open --context context:primary-signature -vv SayIt-macOS-x86_64.dmg

# 4) Confirm native arch of each build
lipo -info "/Volumes/SayIt/SayIt.app/Contents/MacOS/SayIt"   # expect arm64 / x86_64 respectively
```

Expected: step 1 "satisfies its Designated Requirement"; step 2 "The validate
action worked!"; step 3 "accepted / source=Notarized Developer ID"; step 4 the
matching architecture. Any rejection means the artifact is NOT release-ready.

The CI notarization step also calls `notarytool submit --wait` (fails on an
Apple rejection) and `stapler validate` + `spctl --assess` inside the job, so a
green `build-macos` with secrets present is the primary signal; the commands
above are the independent, downloadable-artifact confirmation.

---

## 4. Current artifact honesty

The run-39946798291 macOS DMGs are **`unsigned-dev`** development artifacts:
the `Notarize, staple, and verify (Gatekeeper)` step was **skipped** (no
credentials) on both archs, and the `release` job refuses to publish any
`unsigned-dev` DMG. No signing/notarization/stapling/Gatekeeper result is
claimed for them.

---

## 5. Objective release-acceptance criteria (all must hold before a `v*` tag)

1. CI `33a323c`-equivalent run green on all five jobs (met for `33a323c`).
2. Section-2 acceptance matrix completed with pass results on real hardware for
   macOS arm64, macOS Intel, Linux X11, Linux Wayland (tested apps documented).
3. A secrets-present `workflow_dispatch` (section 3.3) shows both DMGs
   `signed-notarized`, and the section-3.4 commands pass on both archs.
4. `RELEASE_CHECKLIST.md` privacy/legal/licensing/docs gates satisfied.
5. Only then: push the `v0.2.0` tag so the tag-gated `release` job builds
   signed+notarized DMGs and publishes. Not before.

Until all of the above are objectively met, keep PR #9 in draft and leave the
project unreleased.
