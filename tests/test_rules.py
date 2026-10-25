
from docproof.rules import (
    RULES,
    check_text,
    load_extra_typos,
)


def spans(findings, rule=None):
    return [f for f in findings if rule is None or f.rule == rule]


def flags(checks, rule):
    return [f for f in checks if f.rule == rule]


def test_typos_base_form_flagged_with_fix():
    findings = check_text("We recieved the memo.")
    hit = flags(findings, "typos")[0]
    assert hit.suggestion == "received"
    assert hit.excerpt


def test_typos_inflected_forms():
    findings = check_text("They recieved it and they wants? no, sieze it.")
    fixes = {f.suggestion for f in flags(findings, "typos")}
    assert "received" in fixes      # recieved -> received (-ed inflection)
    assert "seize" in fixes


def test_typos_preserve_capitalization():
    findings = check_text("Definately!")
    hit = flags(findings, "typos")[0]
    assert hit.suggestion == "Definitely"


def test_clean_text_flags_nothing_for_typos():
    assert flags(check_text("The quick brown fox."), "typos") == []


def test_repeated_word_flagged():
    findings = check_text("He said that that idea worked.")
    hits = flags(findings, "repeated_words")
    assert len(hits) == 1
    assert hits[0].suggestion in {"that", "That"}


def test_repeated_word_allowlist_is_quiet():
    assert flags(check_text("Ha ha, nice one."), "repeated_words") == []


def test_repeated_word_across_line_break():
    assert flags(check_text("the\nthe cat"), "repeated_words")


def test_repeated_word_not_across_blank_line():
    findings = check_text("End.\n\nThe end.")
    assert flags(findings, "repeated_words") == []


def test_case_inconsistency_flagged_mid_sentence():
    findings = check_text("The OpenAI model sees openai work.")
    hits = flags(findings, "case_inconsistency")
    assert len(hits) == 1
    assert hits[0].suggestion == "OpenAI"


def test_case_inconsistency_ignores_sentence_starts():
    findings = check_text("The book. The sequel. the end of the story.")
    assert flags(findings, "case_inconsistency") == []


def test_article_mismatch_both_directions():
    findings = check_text("a apple. an hour. an Wonka fan.")
    notes = [f.suggestion for f in flags(findings, "a_an_article")]
    assert "an apple" in notes      # "a" before vowel
    assert "a Wonka" in notes       # "an" before consonant
    # "an hour" is correct: no finding for it
    assert "an hour" not in notes


def test_article_mismatch_skips_acronyms():
    findings = check_text("a HDT badge; a unique gift.")
    assert flags(findings, "a_an_article") == []


def test_double_and_trailing_space():
    findings = check_text("Too many  spaces here.   \nNext line.")
    rules_hit = {f.rule for f in findings}
    assert "double_space" in rules_hit
    assert "trailing_space" in rules_hit


def test_extra_punctuation():
    findings = check_text("Stop!!!!")
    hit = flags(findings, "extra_punctuation")[0]
    assert hit.suggestion == "!"


def test_weasel_words_is_style_hint_without_suggestion():
    findings = check_text("It was basically fine.")
    hit = flags(findings, "weasel_words")[0]
    assert hit.suggestion is None
    assert not hit.auto_fix


def test_passive_voice_hint():
    findings = check_text("The request was denied by the desk.")
    assert flags(findings, "passive_voice_hints")


def test_rules_filter_limits_scope():
    findings = check_text("We recieved alot  .", rules=["typos"])
    assert {f.rule for f in findings} == {"typos"}


def test_extra_typos_from_config_merge_in():
    merged = load_extra_typos({"hte": "the", "mispell": "misspell"})
    assert merged["hte"] == "the"
    assert merged["recieve"] == "receive"
    findings = check_text("Fix the hte typo.", extra_typos={"hte": "the"})
    hit = flags(findings, "typos")[0]
    assert hit.suggestion == "the"


def test_every_rule_is_listed():
    sample = "recieved  alot an apple was taken!!!! thing  "
    findings = check_text(sample)
    rules_seen = {f.rule for f in findings}
    assert rules_seen <= set(RULES)


def test_findings_sorted_by_position():
    findings = check_text("a apple recieved  here.")
    starts = [f.start for f in findings]
    assert starts == sorted(starts)
