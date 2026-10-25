"""Patch writer: turns accepted suggestions into candidate text, then writes
two artifact files -- never the original:

  * ``<name>.suggested.patch``  -- a unified diff (applyable by ``patch`` or
    ``git apply`` when the user chooses to).
  * ``<name>.suggested.md``     -- the same changes, annotated with reasons.

The original document is treated as read-only everywhere in this code path.
"""

import difflib
from dataclasses import dataclass

from .rules import Finding


@dataclass
class AppliedFix:
    span_start: int
    span_end: int
    original: str
    replacement: str
    rule: str
    label: str
    reason: str
    source: str  # "offline rule" or "llm"


def build_candidate(
    text: str, findings: list[Finding], llm_edits: list[dict] | None = None
) -> tuple[str, list[AppliedFix]]:
    """Apply confident, safe fixes into an in-memory candidate.

    Only findings with an auto-fixable suggestion are applied, and each
    replacement takes its surroundings with it, so nothing outside the flagged
    span can shift.
    """
    fixes: list[AppliedFix] = []
    edits: list[tuple[int, int, str]] = []  # (start, end, replacement)
    for f in findings:
        if not f.auto_fix:
            continue
        original = text[f.start:f.end]
        edits.append((f.start, f.end, f.suggestion or ""))
        fixes.append(
            AppliedFix(
                span_start=f.start,
                span_end=f.end,
                original=original,
                replacement=f.suggestion or "",
                rule=f.rule,
                label=f.label,
                reason=f.note,
                source="offline rule",
            )
        )

    for ed in llm_edits or []:
        find = ed.get("find", "")
        replace = ed.get("replace", "")
        reason = ed.get("reason", "(no reason given)")
        if not find or find not in text:
            continue  # endpoint suggested text that isn't in the doc: skip it
        idx = text.find(find)
        if _overlaps(edits, idx, idx + len(find)):
            continue  # don't stack two edits on the same characters
        edits.append((idx, idx + len(find), replace))
        fixes.append(
            AppliedFix(
                span_start=idx,
                span_end=idx + len(find),
                original=find,
                replacement=replace,
                rule="llm_suggestion",
                label="endpoint suggestion",
                reason=reason,
                source="endpoint",
            )
        )

    edits.sort()
    candidate_parts: list[str] = []
    cursor = 0
    for start, end, replacement in edits:
        candidate_parts.append(text[cursor:start])
        candidate_parts.append(replacement)
        cursor = end
    candidate_parts.append(text[cursor:])
    return "".join(candidate_parts), fixes


def _overlaps(edits: list[tuple[int, int, str]], start: int, end: int) -> bool:
    return any(start < e and s < end for s, e, _ in edits)


def write_unified_patch(
    original: str, candidate: str, source_path: str
) -> str:
    """A conventional unified diff, as saved to ``.suggested.patch``."""
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        candidate.splitlines(keepends=True),
        fromfile=f"a/{source_path}",
        tofile=f"b/{source_path}",
        n=3,
    )
    diff_text = "".join(diff)
    if diff_text and not diff_text.endswith("\n"):
        diff_text += "\n\\ No newline at end of file\n"
    elif not diff_text:
        diff_text = ""
    return diff_text


def render_annotated_markdown(
    original: str, candidate: str, fixes: list[AppliedFix], source_path: str
) -> str:
    """Human-readable, annotated patch: what, where, why. Also shows the
    unified diff below the table, so both audiences are covered."""
    lines: list[str] = []
    lines.append(f"# Suggested edits for `{source_path}`")
    lines.append("")
    lines.append(
        "This file was produced by DocProof. **Your original document was not "
        "changed.** Review each suggestion below; you decide what to accept."
    )
    lines.append("")
    if fixes:
        lines.append("| # | Where | Before | After | Why | Source |")
        lines.append("|---|-------|--------|-------|-----|--------|")
        for i, fx in enumerate(fixes, 1):
            line_no = original.count("\n", 0, fx.span_start) + 1
            lines.append(
                f"| {i} | line {line_no} | "
                f"`{_cell(fx.original)}` | `{_cell(fx.replacement)}` | "
                f"{_cell(fx.reason)} | {fx.source} |"
            )
        lines.append("")
        lines.append("## Suggested text, side by side")
        lines.append("")
        for line in difflib.unified_diff(
            original.splitlines(),
            candidate.splitlines(),
            fromfile="original",
            tofile="suggested",
            n=1, lineterm="",
        ):
            lines.append("    " + line)
    else:
        lines.append("Nothing met the confidence bar, so the patch is empty.")
    lines.append("")
    lines.append(
        "To apply the patch yourself, **after reviewing it**, e.g.:\n"
        f"    patch {source_path} < {source_path}.suggested.patch"
    )
    lines.append("")
    return "\n".join(lines)


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ¶ ")
