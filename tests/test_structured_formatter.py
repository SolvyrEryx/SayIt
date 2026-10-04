"""Phase 6I tests: context-aware structured formatting.

Covers URL / file-path / email / technical-slash / vN-version formatting plus a
strong negative corpus proving ordinary prose is left unchanged. All tests are
deterministic synthetic text (no ASR, no network). Synthetic coverage shows
transformation recall and false-positive resistance; it is NOT a real-world
accuracy claim.
"""

from src.sayit.core.transcript_processor import correct_transcript
from src.sayit.core.transcript_processor.structured_formatter import (
    format_structured,
)


def norm(text, **kw):
    return correct_transcript(text, **kw).text


class TestURLs:
    def test_simple_domain(self):
        # 'github' is a registered entity -> canonical brand casing is expected.
        assert norm("visit github dot com") == "visit GitHub.com"

    def test_plain_domain_no_entity(self):
        assert norm("go to example dot com") == "go to example.com"

    def test_domain_with_path(self):
        assert norm("open example dot com slash repo") == "open example.com/repo"

    def test_www_host(self):
        assert norm("www dot example dot com") == "www.example.com"

    def test_subdomain(self):
        assert norm("docs dot example dot com") == "docs.example.com"

    def test_unknown_tld_not_formatted(self):
        # No known TLD and not www -> left as prose (no strong anchor).
        assert norm("example dot banana") == "example dot banana"


class TestFilePaths:
    def test_py_path(self):
        assert norm("src slash sayit slash app dot py") == (
            "src/sayit/app.py"
        )

    def test_md_path(self):
        assert norm("docs slash README dot md") == "docs/README.md"

    def test_requires_extension_anchor(self):
        # Slashes but no known extension -> not a path (ambiguous), unchanged.
        assert norm("one slash two slash three") == "one slash two slash three"

    def test_unknown_extension_not_formatted(self):
        assert norm("src slash notes dot banana") == "src slash notes dot banana"


class TestEmails:
    def test_simple_email(self):
        assert norm("noah at example dot com") == "noah@example.com"

    def test_org_email(self):
        assert norm("support at example dot org") == "support@example.org"

    def test_at_without_domain_shape_unchanged(self):
        # 'at' as ordinary word must not create an email.
        assert norm("email John at noon") == "email John at noon"
        assert norm("meet me at noon") == "meet me at noon"


class TestTechSlashAndVersion:
    def test_api_v1_spelled(self):
        assert norm("call the a p i slash v one") == "call the API/v1"

    def test_api_v2(self):
        assert norm("a p i slash v two") == "API/v2"

    def test_v_version(self):
        assert norm("v one point two") == "v1.2"

    def test_lowercase_api_not_anchor(self):
        # ordinary 'api' word is not a tech anchor.
        assert norm("the api slash is wrong") == "the api slash is wrong"


class TestPhase6GPreserved:
    def test_decimal_version_still_works(self):
        assert norm("version three point two") == "version 3.2"

    def test_percent_still_works(self):
        assert norm("ninety five percent") == "95%"
        assert norm("one hundred percent") == "100%"

    def test_date_still_works(self):
        assert norm("March fourteenth") == "March 14th"

    def test_entities_still_work(self):
        assert norm("push to git hub") == "push to GitHub"
        assert norm("the c i slash c d pipeline") == "the CI/CD pipeline"


class TestNegativeCorpus:
    """Ordinary prose that MUST remain unchanged (false-positive resistance)."""

    def test_ordinary_prose_unchanged(self):
        samples = [
            "Put a dot here.",
            "Walk down the path.",
            "Use a slash in the sentence.",
            "I said API but meant the ordinary word.",
            "The file is in the folder.",
            "Meet me at noon.",
            "I put a dot on the page.",
            "There is a dot here.",
            "Give me a break at the end.",
            "She drew a line and a slash.",
            "The dog ran down the path to the park.",
            "We will meet at the office.",
        ]
        for s in samples:
            assert norm(s) == s, s

    def test_dot_between_non_tld_unchanged(self):
        assert norm("the ball dot the net") == "the ball dot the net"

    def test_single_at_unchanged(self):
        assert norm("look at this") == "look at this"


class TestIdempotency:
    def test_idempotent(self):
        samples = [
            "visit github dot com slash repo",
            "noah at example dot com",
            "src slash sayit slash app dot py",
            "a p i slash v one",
            "v one point two",
            "www dot example dot com",
            "Put a dot here.",
        ]
        for s in samples:
            once = norm(s)
            twice = norm(once)
            assert once == twice, (s, once, twice)


class TestExplainability:
    def test_url_change_recorded(self):
        res = correct_transcript("visit example dot com slash repo")
        assert res.text == "visit example.com/repo"
        assert any(c.rule == "url_structure" for c in res.changes)
        assert all(c.category and c.rule for c in res.changes)

    def test_email_rule(self):
        res = correct_transcript("noah at example dot com")
        assert any(c.rule == "email_address" for c in res.changes)

    def test_path_rule(self):
        res = correct_transcript("src slash app dot py")
        assert any(c.rule == "file_path" for c in res.changes)

    def test_no_change_empty_list(self):
        res = correct_transcript("Walk down the path.")
        assert res.text == "Walk down the path."
        assert res.changes == []


class TestFormatStructuredUnit:
    def test_returns_spans_and_rules(self):
        out = format_structured("go to example dot com")
        assert len(out) == 1
        cstart, cend, original, replacement, rule = out[0]
        assert original == "example dot com"
        assert replacement == "example.com"
        assert rule == "url_structure"

    def test_pure_no_mutation(self):
        text = "example dot com"
        _ = format_structured(text)
        assert text == "example dot com"

    def test_disabled_with_formatting_off(self):
        assert norm("visit example dot com", enable_formatting=False) == (
            "visit example dot com"
        )

    def test_enable_structured_false_keeps_phase6g(self):
        # enable_structured=False disables ONLY Phase 6I structured detection;
        # Phase 6G number/date/percent and entity normalization still run.
        assert norm("visit example dot com", enable_structured=False) == (
            "visit example dot com"
        )
        assert norm("version three point two", enable_structured=False) == (
            "version 3.2"
        )
        assert norm("push to git hub", enable_structured=False) == "push to GitHub"
