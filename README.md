# DocProof — a friendly manuscript proofreader

DocProof reads your manuscript or document, flags likely problems, and shows
them in an **inline diff report** — all without changing a single byte of your
original file. If you want a second opinion, an optional suggestion pass asks
any OpenAI-compatible model endpoint (a local [Ollama](https://ollama.com)
server by default) for extra fixes — and those land **only in annotated patch
files** that you review yourself. DocProof never auto-rewrites your work.

Built to be explained "like a friend would": plain English, step by step,
never condescending.

> Made with care by **Asdale Dynamics, LLC** — beginner-friendly AI education,
> books, and practical tools. Part of the toolkit around
> *The Massive AI Manual* and [dylanasdale.github.io](https://dylanasdale.github.io).

## What it checks (offline, no internet needed)

| Rule | Example it catches |
|------|--------------------|
| `typos` | "recieved" → "receive", "alot" → "a lot" (handles -s/-ed forms too) |
| `repeated_words` | "the the", "that that" (with a soft-spot allowlist like "ha ha") |
| `case_inconsistency` | "OpenAI" vs "openai" in the same document |
| `a_an_article` | "a apple" → "an apple", "an Wonka" → "a Wonka" (knows "an hour" is right) |
| `double_space` | two spaces between words |
| `trailing_space` | stray spaces before a line break |
| `extra_punctuation` | "Stop!!!!" |
| `weasel_words` | filler words like "very", "basically", "just" (a nudge, not a rewrite) |
| `passive_voice_hints` | "was denied", "has been taken" (a hint, not a rewrite) |

## Quickstart

No install needed — Python 3.11+ from the standard library only:

```bash
python3 -m docproof chapter_one.md
```

You get an inline report in the terminal. Caret marks show exactly where the
flag is, with a plain-English note:

```
    2 | We recieved alot of updates yesterday.
      |    ^^^^^^^^
  ✎ possible typo: Did you mean "received"?
      suggestion → "received"
```

Exit codes: `0` nothing found · `1` findings reported (handy for editors and CI) · `2` something went wrong.

## Options

```
python3 -m docproof FILE [--config PATH] [--rules RULE ...] [--output PATH]
                         [--suggest] [--base-url URL] [--model NAME]
                         [--api-key-env NAME] [--max-suggestions N]
                         [--patch-out DIR] [--quiet] [--version]
```

- `--output report.txt` — save the report (saves your terminal scrollback).
- `--rules typos repeated_words` — run only chosen rules.
- `--suggest` — run the optional endpoint suggestion pass (see below).
- `--base-url` / `--model` — point at any OpenAI-compatible endpoint.
- `--api-key-env NAME` — for endpoints that need a key: the *environment
  variable's name* goes in flags/config, the value never touches a file.
- `--patch-out DIR` — where patch artifacts go (default: next to the document).
- `--quiet` — suppress stdout; good when you only care about the exit code
  and the files.

## The suggestion pass (optional, review-only)

With `--suggest`, DocProof also asks a chat endpoint for extra small surface
fixes — spelling slips, doubled words, wrong a/an, stray spaces, obvious
capitalization inconsistencies. Defaults to a **local Ollama** server:

```bash
# one-time: make sure Ollama is running and has a small model
ollama pull llama3.2

python3 -m docproof chapter_one.md --suggest
```

Non-Ollama or remote endpoints work anywhere:

```bash
python3 -m docproof chapter_one.md --suggest \
    --base-url http://localhost:1234/v1 --model mistral-7b
```

What `--suggest` produces (always *new files*, never edits to your original):

- `chapter_one.md.suggested.patch` — a conventional unified diff you can apply
  with `patch` or `git apply`, **after you read it**.
- `chapter_one.md.suggested.md` — the same edits as an annotated table:
  where, before → after, and *why* for each suggestion.

The report itself gains a "Patch-candidate preview" section with a readable
`-`/`+` diff so you can see the whole picture in one place.

Privacy: your document text is sent only to the endpoint you configure. With
the default localhost Ollama setup, nothing leaves your machine. If the
endpoint needs a key, pass `--api-key-env MY_ENV_VAR_NAME`; DocProof reads the
value from your environment at request time and never stores or logs it.

## Config file

Save `proofreader.toml` in your working directory (or pass `--config`).
CLI flags always win over the file:

```toml
[endpoint]
base_url = "http://localhost:11434/v1"
model    = "llama3.2"
api_key_env = ""        # name only; value comes from the environment
timeout = 60            # seconds

[rules]
enabled = ["typos", "repeated_words", "case_inconsistency", "double_space"]
extra_typos = { "hte" = "the", "mispell" = "misspell" }
```

Your vocabulary lives in `extra_typos` — make it yours: character names,
product names, jargon.

## Installing as a command (optional)

```bash
pip install .
docproof --version
```

Everything also works without installing: run from the repo with
`python3 -m docproof …`.

## Running the tests

The suite is fully offline — the endpoint is mocked, no network, no secrets:

```bash
python3 -m pytest tests
```

## Design promises

1. **Read-only originals.** DocProof opens your file, never writes it. Verified
   in the test suite (byte-for-byte before/after checks).
2. **You decide.** Every suggestion is a flag plus a proposed fix, visible in
   the report. Applied edits exist only in patch artifacts you review.
3. **No secrets in files.** Keys live in environment variables, referenced by
   name only.
4. **Local-first.** Works entirely offline; downloads nothing.

## Known limits

- English prose focus; the wordlist follows general American usage.
- Suggestions come from a regex/heuristic rule set plus an optional model —
  it's a careful first pass, not a replacement for your own read-through.
- Code blocks and URLs in Markdown are scanned too; a `--rules` filter can
  quiet things down while drafting.

## License

MIT — see [LICENSE](LICENSE). © **Asdale Dynamics, LLC**.
