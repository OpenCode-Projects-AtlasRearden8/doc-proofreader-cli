from docproof.patcher import build_candidate
from docproof.report import render_report

SAMPLE = (
    "The the quick brown fox.\n"
    "We recieved the memo.  \n"
    "He is an Wonka fan.\n"
)


def findings():
    from docproof.rules import check_text

    return check_text(SAMPLE, rules=["repeated_words", "typos", "a_an_article", "trailing_space"])


def test_report_has_caret_under_repeated_word():
    report = render_report(SAMPLE, findings(), source_name="manuscript.md")
    lines = report.splitlines()
    flagged_row = next(i for i, l in enumerate(lines) if "The the quick" in l)
    caret_line = lines[flagged_row + 1]
    assert "^^" in caret_line
    assert "repeated word" in report


def test_report_labels_and_suggestions():
    report = render_report(SAMPLE, findings(), source_name="manuscript.md")
    assert "possible typo" in report
    assert "a/an mismatch" in report
    assert "trailing space" in report
    assert "suggestion →" in report


def test_report_clean_document_message():
    report = render_report("Perfect text.", [], source_name="clean.md")
    assert "Nothing flagged" in report
    assert "never touched" in report


def test_report_diff_preview_when_candidate_given():
    candidate, _ = build_candidate(SAMPLE, findings())
    report = render_report(
        SAMPLE, findings(), source_name="manuscript.md", candidate_text=candidate
    )
    assert "Patch-candidate preview" in report
    assert any(line.startswith("  - ") for line in report.splitlines())
    assert any(line.startswith("  + ") for line in report.splitlines())
    assert "NOT applied" in report


def test_report_respects_max_findings():
    from docproof.rules import check_text

    noisy = ("It was very  good thing, an apple recieved. " * 40)
    findings = check_text(noisy)
    report = render_report(noisy, findings, source_name="x.md", max_findings=3)
    assert "more finding(s) not shown" in report
