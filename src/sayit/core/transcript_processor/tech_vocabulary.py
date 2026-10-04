"""Built-in technical vocabulary registry (data only).

This module holds *data* used by the technical corrector; it contains no
processing logic. Keeping it separate makes the vocabulary easy to extend.

Each entry maps a canonical technical form to a conservative set of spoken/ASR
alias phrases. Aliases are matched case-insensitively on whole-word boundaries
by the corrector; they are intentionally specific (multi-word or clearly
technical tokens) to avoid rewriting ordinary English. This list is NOT
exhaustive and is deliberately conservative.
"""

from __future__ import annotations

# category -> list of (canonical, [aliases])
# Aliases should be forms a speech model plausibly emits for the canonical term.
# Keep them specific; do not add single ordinary words that collide with prose.
TECH_ENTITIES: dict[str, list[tuple[str, list[str]]]] = {
    "version-control": [
        ("GitHub", ["git hub", "github"]),
        ("GitHub Actions", ["git hub actions", "github actions"]),
        ("Git", []),  # canonical only; "git" alone is ambiguous, not aliased
    ],
    "programming-language": [
        ("Python", []),
        ("JavaScript", ["java script"]),
        ("TypeScript", ["type script"]),
    ],
    "framework": [
        ("React", []),
        ("Next.js", ["next js", "next dot js", "nextjs"]),
        ("Node.js", ["node js", "node dot js", "nodejs"]),
    ],
    "database": [
        ("PostgreSQL", ["postgre sql", "postgres sql", "post gres sql", "postgresql"]),
        ("SQL", []),
        ("GraphQL", ["graph ql", "graphql"]),
    ],
    "devops": [
        ("Docker", []),
        ("Kubernetes", ["kubernetes"]),
        ("CI/CD", ["ci slash cd", "ci cd", "c i slash c d", "c i c d"]),
    ],
    "cloud": [
        ("AWS", []),
        ("GCP", []),
        ("Azure", []),
    ],
    "product": [
        ("VS Code", ["vs code", "v s code"]),
    ],
    "protocol": [
        ("HTTP", []),
        ("HTTPS", []),
        ("SSH", []),
        ("TCP", []),
        ("UDP", []),
        ("DNS", []),
        ("REST", []),
    ],
    "operating-system": [
        ("Linux", []),
        ("Windows", []),
    ],
}

# Acronyms recognized when spelled out letter-by-letter in speech. The key is
# the canonical acronym; values are the spoken letter sequences (space-joined
# single letters) the ASR might emit. Matched only when the WHOLE spelled-out
# phrase is present, so ordinary words are never collapsed into an acronym.
SPELLED_ACRONYMS: dict[str, list[str]] = {
    "API": ["a p i"],
    "SDK": ["s d k"],
    "TLS": ["t l s"],
    "SSH": ["s s h"],
    "JSON": ["j s o n"],
    "YAML": ["y a m l"],
    "JWT": ["j w t"],
    "OAuth": ["o auth"],
    "HTTP": ["h t t p"],
    "HTTPS": ["h t t p s"],
    "TCP": ["t c p"],
    "UDP": ["u d p"],
    "DNS": ["d n s"],
    "SQL": ["s q l"],
    "AWS": ["a w s"],
    "GCP": ["g c p"],
    "CI/CD": ["c i slash c d", "c i c d"],
}
