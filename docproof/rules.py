"""Offline proofreading rules: no network, no rewriting, just findings.

Every rule scans plain text and reports ``Finding`` objects with exact
character offsets so reports can draw caret markers and the patch writer can
build candidate replacements safely.
"""

import re
from collections import Counter
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Common English misspellings -> corrected form.
# Small and high-confidence by design: this tool flags, a human decides.
# --------------------------------------------------------------------------

MOSTLY_MISPELLED = {
    "alot": "a lot",
    "adress": "address",
    "agressive": "aggressive",
    "amature": "amateur",
    "apparant": "apparent",
    "arguement": "argument",
    "beleive": "believe",
    "begining": "beginning",
    "calender": "calendar",
    "cant": "can't",
    "cemetary": "cemetery",
    "cheif": "chief",
    "collegue": "colleague",
    "commited": "committed",
    "concious": "conscious",
    "definately": "definitely",
    "definitly": "definitely",
    "embarass": "embarrass",
    "enviroment": "environment",
    "exagerate": "exaggerate",
    "existance": "existence",
    "familar": "familiar",
    "finaly": "finally",
    "foriegn": "foreign",
    "freind": "friend",
    "gaurd": "guard",
    "goverment": "government",
    "grammer": "grammar",
    "harrass": "harass",
    "hierachy": "hierarchy",
    "immediatly": "immediately",
    "independant": "independent",
    "knowlege": "knowledge",
    "liason": "liaison",
    "libary": "library",
    "maintainance": "maintenance",
    "managment": "management",
    "neccessary": "necessary",
    "noticable": "noticeable",
    "occassion": "occasion",
    "occured": "occurred",
    "occurence": "occurrence",
    "pavillion": "pavilion",
    "peice": "piece",
    "perseverence": "perseverance",
    "personel": "personnel",
    "posession": "possession",
    "potatoe": "potato",
    "priviledge": "privilege",
    "probaly": "probably",
    "publically": "publicly",
    "recieve": "receive",
    "reciept": "receipt",
    "recomend": "recommend",
    "refered": "referred",
    "relevent": "relevant",
    "resistence": "resistance",
    "responsibilty": "responsibility",
    "sacrafice": "sacrifice",
    "seperate": "separate",
    "sieze": "seize",
    "similiar": "similar",
    "succesful": "successful",
    "supercede": "supersede",
    "supress": "suppress",
    "tendancy": "tendency",
    "threshhold": "threshold",
    "tounge": "tongue",
    "truely": "truly",
    "unfortunatly": "unfortunately",
    "unneccessary": "unnecessary",
    "untill": "until",
    "usefull": "useful",
    "usally": "usually",
    "wether": "whether",
    "wierd": "weird",
    "wich": "which",
    "writting": "writing",
    "yeild": "yield",
}

# Doubles that are legitimate in context ("ha ha", "yes yes", "boom boom").
REPEATED_WORD_ALLOWLIST = {
    "ha", "haha", "blah", "choo", "tut", "boo", "yada",
    "bon", "jam", "yes", "yo", "bam", "ho", "boom",
}

# Words that weaken writing without being wrong -- nudged, never rewritten.
WEASEL_WORDS = {
    "very": "Stronger: drop it or pick a sharper word.",
    "really": "Stronger: drop it or pick a sharper word.",
    "quite": "Often adds nothing; try dropping it.",
    "just": "Often filler; try dropping it.",
    "actually": "Often filler; try dropping it.",
    "basically": "Usually can go; a plainer sentence is behind it.",
    "literally": "Often not literal; try dropping it.",
    "totally": "Often filler; try dropping it.",
    "extremely": "Try a more precise word instead.",
    "thing": "Vague; try naming the thing.",
    "things": "Vague; try naming them.",
    "stuff": "Vague; try naming it.",
}

PASSIVE_HINTS = {
    "given", "taken", "done", "made", "shown", "known", "written", "heard",
    "sent", "found", "held", "kept", "left", "built", "caught", "brought",
    "seen", "put", "set",
}

# "an" is right before these consonant letters only by sound, not spelling.
AN_SOUND_EXCEPTIONS = {
    "hour", "hours", "honest", "honestly", "honesty", "honor", "honors",
    "honour", "honours", "heir", "heirs", "hono", "xbox",
}

# "a" stays right before these vowel-starting words, which sound like "yu"/"wuh".
A_VOWEL_SOUND_EXCEPTIONS = {
    "unique", "uniquely", "university", "universities", "user", "users",
    "usage", "use", "used", "useful", "usually", "one", "once", "ones",
    "eulogy", "eulogies", "europe", "european", "europeans", "euro",
    "ubiquitous", "unanimous", "union", "unions", "unit", "units", "unicorn",
    "utensil", "utensils", "youth", "youths",
}

RULES = [
    "typos",
    "repeated_words",
    "case_inconsistency",
    "a_an_article",
    "double_space",
    "trailing_space",
    "extra_punctuation",
    "weasel_words",
    "passive_voice_hints",
]

_RULE_LABELS = {
    "typos": "possible typo",
    "repeated_words": "repeated word",
    "case_inconsistency": "inconsistent capitalization",
    "a_an_article": "a/an mismatch",
    "double_space": "double space",
    "trailing_space": "trailing space",
    "extra_punctuation": "extra punctuation",
    "weasel_words": "style: filler word",
    "passive_voice_hints": "style: passive-voice hint",
}


@dataclass
class Finding:
    """One flagged spot in the text, located by character offsets."""

    rule: str
    start: int
    end: int
    excerpt: str
    suggestion: str | None = None
    note: str = ""
    label: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            self.label = _RULE_LABELS.get(self.rule, self.rule)

    @property
    def auto_fix(self) -> bool:
        """True when the suggested replacement is a confident, safe swap."""
        return self.suggestion is not None and self.rule in {
            "typos", "repeated_words", "double_space",
            "trailing_space", "extra_punctuation", "a_an_article",
        }


def load_extra_typos(pairs: dict[str, str] | None) -> dict[str, str]:
    """Merge user-supplied typo candidates with the built-in list."""
    merged = dict(MOSTLY_MISPELLED)
    merged.update(pairs or {})
    return merged


def check_text(
    text: str,
    rules: list[str] | None = None,
    extra_typos: dict[str, str] | None = None,
) -> list[Finding]:
    """Run every enabled rule over ``text`` and return sorted findings."""
    enabled = set(rules) if rules is not None else set(RULES)
    findings: list[Finding] = []
    typo_map = load_extra_typos(extra_typos)

    if "typos" in enabled:
        findings.extend(_find_typos(text, typo_map))
    if "repeated_words" in enabled:
        findings.extend(_find_repeated_words(text))
    if "case_inconsistency" in enabled:
        findings.extend(_find_case_inconsistency(text))
    if "a_an_article" in enabled:
        findings.extend(_find_article_mismatch(text))
    if "double_space" in enabled:
        findings.extend(_find_double_space(text))
    if "trailing_space" in enabled:
        findings.extend(_find_trailing_space(text))
    if "extra_punctuation" in enabled:
        findings.extend(_find_extra_punctuation(text))
    if "weasel_words" in enabled:
        findings.extend(_find_weasel_words(text))
    if "passive_voice_hints" in enabled:
        findings.extend(_find_passive_hints(text))

    seen: set[tuple[str, int, int]] = set()
    unique: list[Finding] = []
    for f in findings:
        key = (f.rule, f.start, f.end)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    unique.sort(key=lambda f: (f.start, f.end, f.rule))
    return unique


# --------------------------------------------------------------------------
# Individual rules
# --------------------------------------------------------------------------

def _find_typos(text: str, typo_map: dict[str, str]) -> list[Finding]:
    findings = []
    pattern = re.compile(r"[A-Za-z][A-Za-z'-]+")
    for m in pattern.finditer(text):
        word = m.group(0)
        fix = _typo_fix(word, typo_map)
        if fix is None:
            continue
        findings.append(
            Finding(
                rule="typos",
                start=m.start(),
                end=m.end(),
                excerpt=_short_excerpt(text, m.start(), m.end()),
                suggestion=fix,
                note=f"Did you mean \u201c{fix}\u201d?",
            )
        )
    return findings


def _typo_fix(word: str, typo_map: dict[str, str]) -> str | None:
    """Fix a misspelling, tolerating simple -s/-ed inflections of a known slip."""
    lower = word.lower()
    fix = typo_map.get(lower)
    if fix is None and lower.endswith("s"):
        fix = typo_map.get(lower[:-1])
        if fix is not None:
            fix += "s"
    if fix is None and lower.endswith(("ed", "d")):
        stem = lower[:-1]
        stem_fix = typo_map.get(stem)
        if stem_fix is None and lower.endswith("ed"):
            stem_fix = typo_map.get(lower[:-2])
            stem = lower[:-2]
        if stem_fix is not None and not stem_fix.endswith("d"):
            fix = stem_fix + "d"
    if fix is None:
        return None
    if word[:1].isupper():
        return fix[0].upper() + fix[1:]
    return fix


def _find_repeated_words(text: str) -> list[Finding]:
    findings = []
    # Same line, or across a single line break (but never across a blank line):
    # "The the" on one line, or "the\nthe" from an accidental line wrap.
    pattern = re.compile(
        r"\b([A-Za-z']+)(?:[ \t]+|\n(?!\n)[ \t]*)\1\b",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        word = m.group(1)
        if word.lower() in REPEATED_WORD_ALLOWLIST:
            continue
        findings.append(
            Finding(
                rule="repeated_words",
                start=m.start(),
                end=m.end(),  # both twins; candidate keeps the first one
                excerpt=_short_excerpt(text, m.start(), m.end()),
                suggestion=word,
                note="Doubled word; the patch candidate keeps the first one.",
            )
        )
    return findings


def _is_sentence_start(text: str, pos: int) -> bool:
    """True when the word at ``pos`` plausibly starts a sentence or line."""
    i = pos - 1
    while i >= 0 and text[i].isspace():
        if text[i] == "\n":
            return True
        i -= 1
    if i < 0:
        return True
    prev = text[i]
    if prev in ".!?:;" or prev == "#":
        return True
    return bool(i > 0 and text[i - 1] == "\n" and prev in "#>*+-\u2022\u2023")


def _find_case_inconsistency(text: str) -> list[Finding]:
    """Flag words that appear under different capitalizations.

    Sentence-start occurrences are treated as explained, so
    "The ... the ..." stays quiet, but two mid-sentence variants
    (say "OpenAI" and "openai") get flagged.
    """
    forms_by_word: dict[str, list[tuple[str, int, bool]]] = {}
    for m in re.finditer(r"[A-Za-z][A-Za-z']*", text):
        word = m.group(0)
        if len(word) < 3 and "'" not in word:
            continue
        at_sentence_start = _is_sentence_start(text, m.start())
        forms_by_word.setdefault(word.lower(), []).append(
            (word, m.start(), at_sentence_start)
        )

    findings: list[Finding] = []
    for _, occurrences in sorted(forms_by_word.items()):
        distinct = {occ[0] for occ in occurrences}
        if len(distinct) < 2:
            continue
        mid_forms = Counter(occ[0] for occ in occurrences if not occ[2])
        if len(mid_forms) < 2:
            continue  # every other variant is a sentence-start/title artifact
        canonical = mid_forms.most_common(1)[0][0]
        for form, pos, at_start in occurrences:
            if at_start or form == canonical:
                continue
            findings.append(
                Finding(
                    rule="case_inconsistency",
                    start=pos,
                    end=pos + len(form),
                    excerpt=_short_excerpt(text, pos, pos + len(form)),
                    suggestion=canonical,
                    note=f"Also appears as \u201c{canonical}\u201d; pick one style.",
                )
            )
    return findings


def _find_article_mismatch(text: str) -> list[Finding]:
    findings = []
    pattern = re.compile(r"\b(a|an)\s+([A-Za-z]\w+)\b")
    for m in pattern.finditer(text):
        article, word = m.group(1).lower(), m.group(2)
        target = word.lower()
        if len(target) < 2 or word.isupper() or not target.isalpha():
            continue  # acronyms/alphanumerics decide by sound; stay quiet
        if article == "a":
            if (target[0] in "aeiou" and target not in A_VOWEL_SOUND_EXCEPTIONS) or (
                target in AN_SOUND_EXCEPTIONS
            ):
                wrong = "an"
            else:
                continue
        else:  # "an"
            if target[0] in "aeiou":
                continue
            if target[0] == "h" or target in AN_SOUND_EXCEPTIONS:
                continue
            wrong = "a"
            # "x"-initial words usually start with the "ex" sound.
            if target[0] == "x":
                continue
        findings.append(
            Finding(
                rule="a_an_article",
                start=m.start(),
                end=m.end(),
                excerpt=_short_excerpt(text, m.start(), m.end()),
                suggestion=f"{wrong} {word}",
                note=f"Sounds like \u201c{wrong} {word}\u201d.",
            )
        )
    return findings


def _find_double_space(text: str) -> list[Finding]:
    findings = []
    for m in re.finditer(r"(?<=\S) {2,}(?=\S)", text):
        findings.append(
            Finding(
                rule="double_space",
                start=m.start(),
                end=m.end(),
                excerpt=_short_excerpt(text, max(0, m.start() - 24), min(len(text), m.end() + 24)),
                suggestion=" ",
                note="Extra spaces between words.",
            )
        )
    return findings


def _find_trailing_space(text: str) -> list[Finding]:
    findings = []
    for m in re.finditer(r"(?<=\S)[ \t]+(?=\n)", text):
        findings.append(
            Finding(
                rule="trailing_space",
                start=m.start(),
                end=m.end(),
                excerpt=_short_excerpt(text, max(0, m.start() - 30), m.end()),
                suggestion="",
                note="Trailing whitespace before the line break.",
            )
        )
    return findings


def _find_extra_punctuation(text: str) -> list[Finding]:
    findings = []
    for m in re.finditer(r"([.!?])\1{3,}", text):
        findings.append(
            Finding(
                rule="extra_punctuation",
                start=m.start(),
                end=m.end(),
                excerpt=_short_excerpt(text, max(0, m.start() - 24), min(len(text), m.end() + 16)),
                suggestion=m.group(1),
                note="Long punctuation run; one mark is usually enough.",
            )
        )
    return findings


def _find_weasel_words(text: str) -> list[Finding]:
    findings = []
    for m in re.finditer(r"[A-Za-z]+", text):
        word = m.group(0).lower()
        if word in WEASEL_WORDS:
            findings.append(
                Finding(
                    rule="weasel_words",
                    start=m.start(),
                    end=m.end(),
                    excerpt=_short_excerpt(text, max(0, m.start() - 30), min(len(text), m.end() + 34)),
                    note=WEASEL_WORDS[word],
                )
            )
    return findings


def _find_passive_hints(text: str) -> list[Finding]:
    findings = []
    hint_words = "|".join(sorted(PASSIVE_HINTS))
    pattern = re.compile(
        r"\b(was|were|been|being)\s+(?:\w+ed\b|" + hint_words + r"\b)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        findings.append(
            Finding(
                rule="passive_voice_hints",
                start=m.start(),
                end=m.end(),
                excerpt=_short_excerpt(text, max(0, m.start() - 28), min(len(text), m.end() + 28)),
                note="Passive-voice hint; active voice often reads stronger.",
            )
        )
    return findings


def _short_excerpt(text: str, start: int, end: int, max_len: int = 78) -> str:
    """A compact, whitespace-normalized clip around the flagged span."""
    lo = max(0, start - 30)
    hi = min(len(text), end + 30)
    clip = " ".join(text[lo:hi].split()).strip()
    if len(clip) > max_len:
        clip = clip[: max_len - 1] + "\u2026"
    return clip if clip else text[start:end]
