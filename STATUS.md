# STATUS — DocProof (doc-proofreader-cli)

Last updated: 2026-10-25
Built and committed by request on behalf of **Asdale Dynamics, LLC**.

## What was built

`docproof`, a Python 3.11+ CLI that proofreads manuscripts and documents
(writing-friendly: .txt / .md prose) **without ever modifying the original
file**. Standard library only — zero runtime dependencies, fully offline by
default.

### Components

- `docproof/rules.py` — offline rule engine. Flags: common typos (with -s/-ed
  inflection handling and user-extendable word list), repeated words
  (respecting a casual-speak allowlist, works across single line wraps but not
  blank lines), inconsistent capitalization (immune to sentence-start
  artifacts), a/an article mismatches (sound-aware: "an hour" stays, "an
  Wonka" flags), double spaces, trailing spaces, long punctuation runs, plus
  style nudges for filler words and passive-voice hints (nudge only, no
  rewrite).
- `docproof/report.py` — inline diff report: caret-marked excerpts, plain-
  English notes, suggestions shown, summary by rule type, and a readable
  `-`/`+` patch-candidate preview when suggestions were gathered.
- `docproof/endpoint.py` — optional suggestion pass against any
  **OpenAI-compatible** chat endpoint. Default: **Ollama at
  `http://localhost:11434/v1`**, any base URL via `--base-url` or
  `proofreader.toml`. Tolerant response parsing (bare or fenced JSON), capped
  suggestions, real error messages when a server is down. API keys are read
  from an environment variable named via `--api-key-env` and never written to
  or read from files.
- `docproof/patcher.py` — builds a candidate text in memory and writes two
  artifacts only: `FILE.suggested.patch` (conventional unified diff, verified
  applying cleanly with both the `patch` tool and `git apply`) and
  `FILE.suggested.md` (annotated table: where, before → after, why, source).
  LLM suggestions not found in the document, or overlapping a confident
  offline fix, are skipped safely.
- `docproof/cli.py` / `docproof/config.py` — argparse CLI + TOML config
  (`proofreader.toml` or `--config`); flags win over file. Exit codes:
  0 clean · 1 findings · 2 error.

## How to run it

```bash
# report only (offline, original untouched)
python3 -m docproof chapter_one.md
python3 -m docproof chapter_one.md --output report.txt

# extra suggestions from a local Ollama server (default endpoint)
ollama pull llama3.2   # once
python3 -m docproof chapter_one.md --suggest

# any other OpenAI-compatible endpoint
python3 -m docproof chapter_one.md --suggest \
    --base-url http://localhost:1234/v1 --model mistral-7b

# optional install for the `docproof` command
pip install .
docproof --version

# patch artifacts land next to the doc (or --patch-out DIR):
#   chapter_one.md.suggested.patch   (apply by hand after review)
#   chapter_one.md.suggested.md      (annotated why for each edit)
```

Config file `proofreader.toml` supports endpoint settings (base_url, model,
api_key_env name, timeout) and rule settings (enabled list, extra_typos).

## Verification results (all run in this folder)

| Check | Result |
|---|---|
| `python3 -m pytest tests` (offline; endpoint mocked) | **46/46 pass** |
| `ruff check docproof tests` | **All checks passed** |
| `python3 -m compileall docproof tests` | OK |
| `pip install .` build + `docproof` console script | Builds; entry point runs (`docproof 0.1.0`) |
| End-to-end HTTP: real loopback server speaking OpenAI-style `/v1/chat/completions`, doc content verified arriving at the server, suggestions parsed, patch artifacts written | OK |
| Original file integrity | Byte-for-byte identical before/after in CLI tests (incl. `--suggest`) and smoke runs |
| Generated `.suggested.patch` applyability | `patch file < x.patch` succeeds; `git apply --check` passes |
| Endpoint down / bad JSON behavior | Graceful: "suggestion pass skipped … continuing with the offline report only"; artifacts still written |
| No secrets/personal data scan | Clean; test only uses a clearly-fake key value and asserts it stays out of request bodies |

## Known gaps / honest limits

1. English-focused rule lists; adding other languages means adding wordlists.
2. Code blocks, URLs, and front-matter in Markdown are scanned like prose; a
   `--rules` filter (or `extra_typos`) is the current workaround.
3. LLM matching is exact-substring only — the endpoint is prompted to copy
   exact text, and anything else is safely dropped rather than guessed.
4. `--max-prompt-chars` caps the doc sent for suggestions at 12,000 chars
   (longer docs get truncated for the suggestion pass; offline rules always
   scan the full text).
5. Windows/Unicode edge cases (CRLF endings) untested in CI here; the tool is
   posix-developed in this environment.
6. `pip install .` in the verification environment required
   `--no-build-isolation` (PEP 668-managed system Python); from source with
   `python3 -m docproof` there are no requirements at all.

## Repo

- Git initialized; single-branch local history, no remote, nothing published.
- Commit: `Initial commit: DocProof manuscript proofreader CLI`
- License: MIT — `Copyright (c) 2026 Asdale Dynamics, LLC` (exact line in LICENSE).
- README credits Asdale Dynamics, LLC and links the beginner-AI hub framing.
