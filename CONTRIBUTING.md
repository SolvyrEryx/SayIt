# Contributing to SayIt

Thanks for your interest in SayIt. This is a local-first desktop voice-typing
app ([VptrCipher/SayIt](https://github.com/VptrCipher/SayIt)).

## Development setup

```bash
git clone https://github.com/VptrCipher/SayIt.git
cd SayIt
uv sync --frozen          # install the exact validated environment
uv run pytest -m "not slow"
uv run python -m sayit
```

The validated runtime is **sherpa-onnx 1.12.21 + sherpa-onnx-core 1.12.23**
(pinned in `uv.lock`). Please do **not** upgrade these or run bare `uv lock` in a
PR — the ASR stack is validated against these exact versions.

## Ground rules

- Run `uv run pytest -m "not slow"` before opening a PR; keep the suite green.
- Keep changes focused; explain what you changed and how you verified it.
- Do not change ASR model/decoder/tokenizer behavior without benchmark evidence.
- Preserve privacy defaults (cloud enhancement and history are off by default).
- Match the existing code style (`black` / `isort` configs are in the repo).

## Pull requests

1. Fork and create a feature branch.
2. Make your change with tests.
3. Run the suite and, for anything touching ASR/latency, the relevant benchmark.
4. Open a PR describing the change, the tests run, and any tradeoffs.

## Reporting issues

Open an issue at
[github.com/VptrCipher/SayIt/issues](https://github.com/VptrCipher/SayIt/issues)
with steps to reproduce, your OS/version, and expected vs. actual behavior.

By contributing you agree your contributions are licensed under the project's
[MIT License](LICENSE).
