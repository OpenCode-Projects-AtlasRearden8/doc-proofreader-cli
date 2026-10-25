"""DocProof command line interface.

Examples
--------
Report only (no network, original untouched):

    python -m docproof chapter_one.txt
    python -m docproof chapter_one.txt --output report.txt

With an optional suggestion pass via any OpenAI-compatible endpoint
(default: local Ollama). Produces patch files only; never rewrites:

    python -m docproof chapter_one.txt --suggest
    python -m docproof chapter_one.txt --suggest --base-url http://localhost:11434/v1 \
        --model llama3.2 --patch-out edits/
"""

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, endpoint_overrides, load_config
from .endpoint import DEFAULT_BASE_URL, DEFAULT_MODEL, Endpoint, EndpointError
from .patcher import build_candidate
from .report import render_report
from .rules import RULES, check_text

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docproof",
        description="Proofread a manuscript without touching the original.",
        epilog="Full guide: README.md · Made by Asdale Dynamics, LLC",
    )
    parser.add_argument("file", help="document to proofread (text or markdown)")
    parser.add_argument(
        "--config", metavar="PATH",
        help="TOML config file (default: ./proofreader.toml if present)",
    )
    parser.add_argument(
        "--rules", nargs="+", metavar="RULE", choices=RULES,
        help="run only these rules; valid: " + ", ".join(RULES),
    )
    parser.add_argument(
        "--output", metavar="PATH",
        help="write the report here instead of stdout",
    )
    parser.add_argument(
        "--suggest", action="store_true",
        help="ask an OpenAI-compatible endpoint for extra suggestions; "
             "results land in patch files, you still decide what to accept",
    )
    parser.add_argument("--base-url", metavar="URL", default=None,
                        help=f"endpoint base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--model", metavar="NAME", default=None,
                        help=f"endpoint model (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--api-key-env", metavar="NAME", default=None,
        help="environment variable that holds the API key, if the endpoint "
             "needs one (the value is never read from or written to files)",
    )
    parser.add_argument("--endpoint-timeout", metavar="SECONDS", type=float, default=None,
                        help="seconds to wait for the endpoint (default: 60)")
    parser.add_argument("--max-suggestions", metavar="N", type=int, default=25,
                        help="cap on endpoint suggestions (default: 25)")
    parser.add_argument(
        "--patch-out", metavar="DIR", default=None,
        help="folder for patch artifacts (default: next to the document)",
    )
    parser.add_argument("--quiet", action="store_true",
                        help="only the exit code; put the report in --output")
    parser.add_argument(
        "--version", action="version", version=f"docproof {__version__}"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"docproof: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    source = Path(args.file)
    if not source.is_file():
        print(f"docproof: error: file not found: {source}", file=sys.stderr)
        return EXIT_ERROR
    try:
        original = source.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError:
        try:
            original = source.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            print(
                f"docproof: error: {source} is not valid UTF-8 text; convert it "
                "first (e.g. save as .txt or .md from your editor)",
                file=sys.stderr,
            )
            return EXIT_ERROR

    rules_cfg = config.get("rules", {})
    enabled_rules = args.rules if args.rules is not None else rules_cfg.get("enabled")
    findings = check_text(original, rules=enabled_rules, extra_typos=rules_cfg.get("extra_typos"))

    candidate, fixes = build_candidate(original, findings)
    patch_paths: list[Path] = []

    endpoint_cfg = endpoint_overrides(config)
    if args.suggest:
        endpoint_cfg = {
            "base_url": args.base_url or endpoint_cfg["base_url"],
            "model": args.model or endpoint_cfg["model"],
            "api_key_env": args.api_key_env or endpoint_cfg.get("api_key_env", ""),
            "timeout": args.endpoint_timeout or float(endpoint_cfg.get("timeout", 60)),
        }
        endpoint = Endpoint(
            base_url=endpoint_cfg["base_url"],
            model=endpoint_cfg["model"],
            api_key_env=endpoint_cfg["api_key_env"],
            timeout=endpoint_cfg["timeout"],
        )
        try:
            suggestions = endpoint.fetch_suggestions(
                original, max_suggestions=max(1, args.max_suggestions)
            )
        except EndpointError as exc:
            print(
                f"docproof: suggestion pass skipped: {exc}\n"
                "          Continuing with the offline report only.",
                file=sys.stderr,
            )
            suggestions = []
        candidate, llm_fixes = build_candidate(original, findings, llm_edits=suggestions)
        fixes = llm_fixes

    if args.suggest:
        patch_paths = write_patch_artifacts(
            original, candidate, fixes, source, args.patch_out
        )

    skipped = [r for r in RULES if enabled_rules and r not in enabled_rules]
    report = render_report(
        original, findings, source_name=source.name, rules_disabled=skipped,
        candidate_text=candidate if args.suggest else None,
    )
    if args.output:
        out_path = Path(args.output)
        if out_path.parent and str(out_path.parent) not in ("", "."):
            out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        if not args.quiet:
            print(f"docproof: report written to {out_path}")
    elif not args.quiet:
        sys.stdout.write(report)

    if patch_paths and not args.quiet:
        for pp in patch_paths:
            print(f"docproof: patch artifact: {pp}")

    return EXIT_CLEAN if not findings and not fixes else EXIT_FINDINGS


def write_patch_artifacts(
    original: str, candidate: str, fixes, source: Path, out_dir: str | None
) -> list[Path]:
    """
    Writes ``.suggested.patch`` and ``.suggested.md``.
    The original document is never written to.
    """
    from .patcher import render_annotated_markdown, write_unified_patch

    target_dir = Path(out_dir) if out_dir else source.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = source.name + ".suggested"
    patch_path = target_dir / (stem + ".patch")
    md_path = target_dir / (stem + ".md")

    patch_text = write_unified_patch(original, candidate, source.name)
    patch_path.write_text(patch_text, encoding="utf-8")
    md_path.write_text(
        render_annotated_markdown(original, candidate, fixes, source.name),
        encoding="utf-8",
    )
    return [patch_path, md_path]


if __name__ == "__main__":
    sys.exit(main())
