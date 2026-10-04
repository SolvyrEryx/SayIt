"""Tests for the Phase 6G technical correction + formatting layer."""

from src.sayit.core.transcript_processor import (
    TechnicalCorrector,
    correct_transcript,
)


def norm(text, **kw):
    return correct_transcript(text, **kw).text


class TestTechnicalEntities:
    def test_github(self):
        assert norm("push to git hub") == "push to GitHub"

    def test_github_actions(self):
        assert norm("run git hub actions") == "run GitHub Actions"

    def test_postgresql(self):
        assert norm("connect to postgre sql") == "connect to PostgreSQL"
        assert norm("use post gres sql") == "use PostgreSQL"

    def test_nextjs_nodejs(self):
        assert norm("build with next js") == "build with Next.js"
        assert norm("the node js server") == "the Node.js server"

    def test_vs_code(self):
        assert norm("open vs code") == "open VS Code"

    def test_type_java_script(self):
        assert norm("written in type script") == "written in TypeScript"
        assert norm("some java script code") == "some JavaScript code"


class TestAcronyms:
    def test_ci_cd(self):
        assert norm("the c i slash c d pipeline") == "the CI/CD pipeline"
        assert norm("ci slash cd pipeline") == "CI/CD pipeline"

    def test_tls(self):
        assert norm("rotate the t l s certificate") == "rotate the TLS certificate"

    def test_api_ssh_json_yaml(self):
        assert norm("call the a p i") == "call the API"
        assert norm("open an s s h session") == "open an SSH session"
        assert norm("parse the j s o n") == "parse the JSON"
        assert norm("edit the y a m l file") == "edit the YAML file"


class TestCorrectTextPreserved:
    def test_already_correct_unchanged(self):
        for s in [
            "Push the code to GitHub.",
            "The TLS certificate is valid.",
            "Run the Python script.",
            "Deploy with Docker and Kubernetes.",
        ]:
            assert norm(s) == s


class TestFalsePositiveResistance:
    def test_ordinary_prose_unchanged(self):
        # Words that merely resemble tech tokens must not be rewritten.
        samples = [
            "I will meet you at the api of the river.",  # 'api' as a word (not spelled)
            "She gave a passionate speech about rest and relaxation.",
            "The git of the matter is simple.",
            "A node in the family tree.",
        ]
        for s in samples:
            # None of these contain registered spelled-acronym phrases or
            # multi-word aliases, so they must be unchanged.
            assert norm(s) == s

    def test_rest_word_not_uppercased(self):
        # 'rest' as an ordinary word should not become REST (REST has no alias).
        assert norm("take some rest") == "take some rest"

    def test_sql_word_boundary(self):
        # 'sql' standalone IS canonical SQL; ensure it doesn't corrupt a larger word.
        assert norm("mysqlthing") == "mysqlthing"


class TestStructuredFormatting:
    def test_percent(self):
        assert norm("ninety five percent") == "95%"
        assert norm("5 percent") == "5%"

    def test_decimal_version(self):
        assert norm("version three point two") == "version 3.2"
        assert norm("3 point 2") == "3.2"

    def test_date(self):
        assert norm("March fourteenth") == "March 14th"
        assert norm("march first") == "March 1st"

    def test_ambiguous_left_unchanged(self):
        # 'point' not between two numbers should be untouched.
        assert norm("get to the point quickly") == "get to the point quickly"
        # 'percent' with a non-number word should be untouched.
        assert norm("the percent sign") == "the percent sign"

    def test_formatting_can_be_disabled(self):
        assert norm("ninety five percent", enable_formatting=False) == (
            "ninety five percent"
        )


class TestCustomVocabulary:
    def test_alias_replacement(self):
        r = norm("deploy my project now", user_vocabulary=[("my project", "ShadowSync AI")])
        assert r == "deploy ShadowSync AI now"

    def test_case_insensitive_match(self):
        r = norm("say it is great", user_vocabulary=[("say it", "SayIt")])
        assert r == "SayIt is great"

    def test_disabled_when_empty(self):
        assert norm("my project", user_vocabulary=[]) == "my project"

    def test_multiword_phrase(self):
        r = norm(
            "contact my company today",
            user_vocabulary=[("my company", "Example Corp")],
        )
        assert r == "contact Example Corp today"


class TestEdgeCases:
    def test_empty(self):
        assert norm("") == ""

    def test_whitespace_only(self):
        assert norm("   ") == "   "

    def test_collapses_internal_spaces(self):
        assert norm("push   to    git hub") == "push to GitHub"

    def test_punctuation_preserved(self):
        assert norm("Deploy to git hub, then run the script.") == (
            "Deploy to GitHub, then run the script."
        )

    def test_unicode_safe(self):
        s = "café résumé naïve — GitHub"
        assert norm(s) == s

    def test_newlines_preserved(self):
        assert norm("line one\nline two") == "line one\nline two"


class TestIdempotency:
    def test_idempotent(self):
        samples = [
            "push to git hub and run c i slash c d",
            "version three point two ninety five percent",
            "March fourteenth connect to postgre sql",
            "Push the code to GitHub.",
        ]
        for s in samples:
            once = norm(s)
            twice = norm(once)
            assert once == twice, (s, once, twice)


class TestExplainability:
    def test_changes_recorded(self):
        res = correct_transcript("push to git hub")
        assert res.raw == "push to git hub"
        assert res.text == "push to GitHub"
        assert any(c.replacement == "GitHub" for c in res.changes)
        assert all(c.category and c.rule for c in res.changes)

    def test_no_changes_empty_list(self):
        res = correct_transcript("Run the Python script.")
        assert res.text == "Run the Python script."
        assert res.changes == []


class TestDisableTechnical:
    def test_technical_disabled(self):
        assert norm("push to git hub", enable_technical=False) == "push to git hub"
