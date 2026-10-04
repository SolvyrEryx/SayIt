"""Phase 9B — small controlled candidate pack (PROOF-OF-CAPABILITY data only).

This is a hand-reviewed, bounded set used solely to test the correction
mechanism. It is NOT a knowledge base and NOT an external-dataset integration
(those are future phases). Context weights and negative contexts are initial
values that the 9B benchmark sweeps/ablates; they are not claimed optimal.

Context profiles (from Phase 8A): normal / developer / email / chat / notes /
prompt. Weight >= 1.0 means "strong technical context" (can override ordinary
protection); lower weights protect ordinary prose.
"""

from __future__ import annotations

from .post_context import Candidate, CandidatePack

# Weight presets.
_DEV = {"developer": 1.0, "prompt": 1.0, "normal": 0.85, "notes": 0.8,
        "email": 0.5, "chat": 0.55}
# Entities whose spoken form is a clean ordinary phrase -> protected_ordinary.
# Their variants include the exact ordinary spelling, so similarity alone is
# ~1.0; only strong context (weight>=1.0) may correct them.

_CANDIDATES = [
    # --- protected ordinary-phrase entities (hard negatives) ---
    Candidate("FastAPI", ("fastapi", "fast api"), "framework", _DEV,
              protected_ordinary=True),
    Candidate("OpenAI", ("openai", "open ai"), "company", _DEV,
              protected_ordinary=True),
    Candidate("Next.js", ("nextjs", "next js", "next.js"), "framework", _DEV,
              protected_ordinary=True),
    Candidate("SQLAlchemy", ("sqlalchemy", "sql alchemy"), "library", _DEV,
              protected_ordinary=True),
    Candidate("TensorFlow", ("tensorflow", "tensor flow"), "library", _DEV,
              protected_ordinary=True),
    Candidate("Python", ("python",), "language", _DEV, protected_ordinary=True),
    Candidate("Rust", ("rust",), "language", _DEV, protected_ordinary=True),
    Candidate("React", ("react",), "framework", _DEV, protected_ordinary=True),

    # --- entities whose correct form is a mangled non-word when misheard ---
    # (not ordinary phrases; safe to recover on strong similarity)
    Candidate("PostgreSQL",
              ("postgresql", "postgres", "postgrey sql", "post dre sql",
               "postjsql", "post gres sql"),
              "database", _DEV),
    Candidate("WebAuthn", ("webauthn", "web auth n", "webant", "web auth"),
              "protocol", _DEV),
    Candidate("kubectl", ("kubectl", "kube control", "ubitil", "cube control",
                          "tube control", "hubitel"),
              "tool", _DEV),
    Candidate("GitHub", ("github", "git hub"), "platform", _DEV),
    Candidate("Docker", ("docker",), "tool", _DEV),
    Candidate("Kubernetes", ("kubernetes", "kube netes"), "tool", _DEV),
    Candidate("Pydantic", ("pydantic", "pie dantic"), "library", _DEV),
    Candidate("ONNX", ("onnx", "o n n x"), "format", _DEV),

    # --- multi-word phrases ---
    Candidate("GitHub Actions", ("github actions", "git hub actions"),
              "phrase", _DEV),
    Candidate("Docker Compose", ("docker compose",), "phrase", _DEV),
    Candidate("vector database", ("vector database",), "phrase", _DEV),
    Candidate("machine learning", ("machine learning",), "phrase", _DEV),
]


def default_pack() -> CandidatePack:
    return CandidatePack(list(_CANDIDATES))


def all_candidates():
    return list(_CANDIDATES)
