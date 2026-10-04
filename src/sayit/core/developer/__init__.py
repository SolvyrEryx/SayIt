"""Phase 8D Developer Mode helpers.

Developer Mode builds on the existing technical layers (6G aliases/acronyms, 6I
URL/path/version formatting, 6J vocabulary, 8A Developer profile). It does NOT
re-implement any of those. It adds two genuinely new, strictly-explicit
capabilities:

1. **Explicit identifier casing.** When the user ends an utterance with an
   explicit casing command, the preceding words are joined into an identifier:
       "get user by id, camel case"  -> "getUserById"
       "get user by id, snake case"  -> "get_user_by_id"
       "get user by id, kebab case"  -> "get-user-by-id"
       "get user by id, pascal case" -> "GetUserById"
   This is the ONLY way casing is applied. Ordinary developer prose
   ("We use snake case in this repository.") is never transformed because the
   casing word there is not an anchored trailing command over a word list.

2. **Code block mode.** "code block ... end code block" wraps the enclosed text
   in a Markdown fenced block and marks it to skip prose/technical correction.
   Nothing is generated or executed — the content is preserved verbatim.

All functions are pure and deterministic.
"""

from .casing import CasingResult, detect_casing_command
from .codeblock import CodeBlockResult, detect_code_block

__all__ = [
    "CasingResult",
    "detect_casing_command",
    "CodeBlockResult",
    "detect_code_block",
]
