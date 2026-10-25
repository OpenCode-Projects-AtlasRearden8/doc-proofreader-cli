
import pytest

from docproof import cli
from docproof.endpoint import Endpoint

SAMPLE = (
    "The the quick brown fox.\n"
    "We recieved alot of updates yesterday.\n"
    "He is an Wonka fan.\n"
)


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "chapter_one.md"
    path.write_text(SAMPLE, encoding="utf-8")
    return tmp_path, path


def run_cli(*argv):
    return cli.main(list(argv))


def test_clean_document_exits_zero(tmp_path):
    clean = tmp_path / "clean.md"
    clean.write_text("The quick brown fox.\n", encoding="utf-8")
    assert run_cli(str(clean)) == 0


def test_findings_exit_one_and_original_untouched(doc):
    _tmp_path, path = doc
    original_bytes = path.read_bytes()
    exit_code = run_cli(str(path))
    assert exit_code == 1
    assert path.read_bytes() == original_bytes


def test_report_written_via_output_option(doc):
    tmp_path, path = doc
    report_path = tmp_path / "out" / "report.txt"
    exit_code = run_cli(str(path), "--output", str(report_path), "--quiet")
    assert exit_code == 1
    report = report_path.read_text(encoding="utf-8")
    assert "chapter_one.md" in report
    assert "repeated word" in report


def test_rules_filter_via_cli(doc, capsys):
    _tmp_path, path = doc
    assert run_cli(str(path), "--rules", "typos") == 1
    out = capsys.readouterr().out
    assert "possible typo" in out
    assert "repeated word" not in out


def test_missing_file_exits_two():
    assert run_cli("no/such/file.md") == 2


def test_bad_config_exits_two(doc):
    tmp_path, path = doc
    cfg = tmp_path / "proofreader.toml"
    cfg.write_text("[rules]\nenabled = ['nope']\n", encoding="utf-8")
    assert run_cli(str(path), "--config", str(cfg)) == 2


def test_config_extra_typos_take_effect(doc, capsys):
    tmp_path, path = doc
    cfg = tmp_path / "proofreader.toml"
    cfg.write_text(
        '[rules]\nextra_typos = { "wonka" = "Wanka" }\n',
        encoding="utf-8",
    )
    run_cli(str(path), "--config", str(cfg), "--quiet")
    report = capsys.readouterr().out
    # quiet: report still goes only to the file? No: quiet suppresses stdout,
    # so use --output instead.
    assert report == ""
    report_path = tmp_path / "cfg_report.txt"
    run_cli(str(path), "--config", str(cfg), "--output", str(report_path), "--quiet")
    content = report_path.read_text(encoding="utf-8")
    assert "Wanka" in content


def test_suggestion_pass_writes_patch_files_but_never_the_original(doc, monkeypatch):
    tmp_path, path = doc
    monkeypatch.setattr(
        Endpoint,
        "fetch_suggestions",
        lambda self, text, max_suggestions=25: [
            {"find": "recieved", "replace": "received", "reason": "misspelling"},
            {"find": "colour", "replace": "color", "reason": "not in the doc at all"},
            {"find": "yesterday", "replace": "earlier today", "reason": "endpoint taste"},
        ],
    )
    before = path.read_bytes()
    exit_code = run_cli(str(path), "--suggest", "--patch-out", str(tmp_path / "edits"))
    after = path.read_bytes()

    assert after == before, "the original document must never change"
    patch_file = tmp_path / "edits" / "chapter_one.md.suggested.patch"
    md_file = tmp_path / "edits" / "chapter_one.md.suggested.md"
    assert patch_file.is_file() and md_file.is_file()

    patch_text = patch_file.read_text(encoding="utf-8")
    assert patch_text.startswith("--- a/chapter_one.md")
    assert "+We received a lot" in patch_text
    assert "earlier today" in patch_text
    # endpoint suggestion appears in the annotated table
    md_text = md_file.read_text(encoding="utf-8")
    assert "| endpoint |" in md_text
    assert "endpoint taste" in md_text
    # the "not in the doc at all" suggestion was dropped
    assert "colour" not in md_text
    assert exit_code == 1


def test_suggest_endpoint_failure_graceful(doc, monkeypatch, capsys):
    from docproof.endpoint import EndpointError

    tmp_path, path = doc
    monkeypatch.setattr(
        Endpoint,
        "fetch_suggestions",
        lambda self, text, max_suggestions=25: (_ for _ in ()).throw(
            EndpointError("could not reach http://localhost:11434/v1 (down)")
        ),
    )
    exit_code = run_cli(str(path), "--suggest", "--patch-out", str(tmp_path / "e"))
    err = capsys.readouterr().err
    assert "skipped" in err and "down" in err
    assert exit_code == 1
    assert (tmp_path / "e" / "chapter_one.md.suggested.patch").is_file()


def test_base_url_flag_reaches_endpoint(doc, monkeypatch):
    _tmp_path, path = doc
    captured = {}

    def fake_suggest(self, text, max_suggestions=25):
        captured["base_url"] = self.base_url
        captured["model"] = self.model
        return []

    monkeypatch.setattr(Endpoint, "fetch_suggestions", fake_suggest)
    run_cli(
        str(path),
        "--suggest",
        "--base-url", "http://192.168.1.10:1234/v1",
        "--model", "mistral-7b",
    )
    assert captured == {"base_url": "http://192.168.1.10:1234/v1", "model": "mistral-7b"}


def test_generated_patch_can_be_ignored_safely(doc):
    """The patch file must not contain the doc's full future content in the
    original direction: originals stay pristine even after artifact writing."""
    tmp_path, path = doc
    run_cli(str(path), "--suggest", "--patch-out", str(tmp_path / "p"))
    assert path.read_text(encoding="utf-8") == SAMPLE


def test_patch_helper_explicitly_available_after_fixes():
    from docproof.patcher import build_candidate
    from docproof.rules import check_text

    candidate, fixes = build_candidate(SAMPLE, check_text(SAMPLE))
    assert fixes
    assert "The quick brown fox." in candidate.splitlines()[0]
    assert "We received a lot of updates" in candidate.splitlines()[1]
