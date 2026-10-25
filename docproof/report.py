"""Inline diff report: flagged excerpts with caret markers, plus a word-level
diff preview whenever a patched candidate is available.

The report only reads. It never writes to the source document.
"""

import difflib
from dataclasses import dataclass

from .rules import Finding


@dataclass
class DocStats:
    lines: int = 0
    words: int = 0


def word_stats(text: str) -> DocStats:
    return DocStats(lines=text.count("\n") + 1, words=len(text.split()))


def render_report(
    text: str,
    findings: list[Finding],
    *,
    source_name: str,
    rules_disabled: list[str] | None = None,
    candidate_text: str | None = None,
    max_findings: int = 200,
) -> str:
    """Build the full inline report as a plain-text string."""
    stats = word_stats(text)
    out: list[str] = []
    out.append(f"DocProof report \u2014 {source_name}")
    out.append("=" * 60)
    out.append(f"{len(findings)} finding(s) · {stats.words:,} words · {stats.lines} lines")
    if rules_disabled:
        out.append(f"Rules skipped (--rules filter): {', '.join(sorted(rules_disabled))}")
    out.append("")

    count_by_rule: dict[str, int] = {}
    for f in findings:
        count_by_rule[f.label] = count_by_rule.get(f.label, 0) + 1
    if count_by_rule:
        out.append("Summary:")
        for label, n in sorted(count_by_rule.items(), key=lambda kv: (-kv[1], kv[0])):
            out.append(f"  {n:>4}  {label}")
        out.append("")
    else:
        out.append("Nothing flagged. Nice and clean — and your file was read, never touched.")
        out.append("")

    for f in findings[:max_findings]:
        out.extend(_render_finding(text, f))
        out.append("")
    if len(findings) > max_findings:
        out.append(f"… {len(findings) - max_findings} more finding(s) not shown.")
        out.append("")

    if candidate_text is not None and findings:
        out.extend(_render_diff_preview(text, candidate_text, findings))

    out.append("Your original file was not modified.")
    return "\n".join(out).rstrip() + "\n"


def _render_finding(text: str, f: Finding) -> list[str]:
    """Caret-marked excerpt for one finding: line, carets, label, suggestion."""
    line_start = text.rfind("\n", 0, f.start) + 1
    line_end = text.find("\n", f.end)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end].expandtabs(4)

    rel_s = len(text[line_start:f.start].expandtabs(4))
    rel_e = rel_s + max(1, len(text[f.start:f.end].expandtabs(4)))
    line_no = text.count("\n", 0, f.start) + 1

    # Keep the shown window under ~90 columns, centered on the finding.
    max_width, lead = 90, 30
    offset = 0
    if len(line) > max_width and rel_e > max_width:
        offset = min(min(rel_s - lead, len(line) - max_width), rel_s - lead)
        offset = max(0, offset)
    win = line[offset:offset + max_width] if len(line) > max_width else line
    prefix = "\u2026" if offset > 0 else ""
    suffix = "\u2026" if len(line) > max_width and offset + max_width < len(line) else ""

    carets = [" "] * _print_width(win)
    for idx in range(rel_s - offset, min(rel_e - offset, len(carets))):
        if idx >= 0:
            carets[idx] = "^"
    if all(c == " " for c in carets) and carets:
        carets[min(len(carets) - 1, max(0, rel_s - offset))] = "^"

    lines_out = [
        f"{line_no:>5} | {prefix}{win}{suffix}",
        f"      | {''.join(carets)}",
        f"  {_MARK_FOR.get(f.rule, '?')} {f.label}{': ' + f.note if f.note else ''}",
    ]
    if f.suggestion is not None and f.suggestion != text[f.start:f.end]:
        lines_out.append(f"      suggestion → {_quote(f.suggestion)}")
    return lines_out


def _render_diff_preview(
    original: str, candidate: str, findings: list[Finding]
) -> list[str]:
    """Line-level, readable diff of original vs. the patch candidate."""
    out = ["Patch-candidate preview (NOT applied to your file):", "-" * 60]
    engine = difflib.SequenceMatcher(None, original.splitlines(), candidate.splitlines())
    notes_by_start: dict[int, list[Finding]] = _locate_findings_by_line(original, findings)
    shown = 0
    for tag, i1, i2, j1, j2 in engine.get_opcodes():
        if tag == "equal":
            continue
        span_lines = range(i1 + 1, max(i1 + 1, i2) + 1)
        labels = sorted({f.label for ln in span_lines for f in notes_by_start.get(ln, [])})
        reason = f" · {', '.join(labels)}" if labels else ""
        out.append(f"line(s) {i1 + 1}{'–' + str(i2) if i2 > i1 + 1 else ''}{reason}")
        for line in original.splitlines()[i1:i2]:
            out.append(f"  - {line}")
        for line in candidate.splitlines()[j1:j2]:
            out.append(f"  + {line}")
        out.append("")
        shown += 1
        if shown >= 40:
            out.append("… preview truncated …")
            out.append("")
            break
    return out


def _locate_findings_by_line(
    text: str, findings: list[Finding]
) -> dict[int, list[Finding]]:
    by_line: dict[int, list[Finding]] = {}
    for f in findings:
        ln = text.count("\n", 0, f.start) + 1
        by_line.setdefault(ln, []).append(f)
    return by_line


def _quote(s: str) -> str:
    return "\u201c" + s + "\u201d" if s else "(remove)"


_PRINTABLE_MIN = 32


def _print_width(s: str) -> int:
    return len(s)


_MARK_FOR = {
    "typos": "\u270E",           # ✎
    "repeated_words": "\u26EC",  # ⛬
    "case_inconsistency": "Aa",
    "a_an_article": "\u204B",    # ⁋
    "double_space": "\u2423",    # ␣
    "trailing_space": "\u21B5",  # ↵
    "extra_punctuation": "!",
    "weasel_words": "\u2712",    # ✒
    "passive_voice_hints": "\u2693",  # ⚓
}
