"""Optional suggestion pass over an OpenAI-compatible chat endpoint.

Default target is a local Ollama server (http://localhost:11434/v1), but any
OpenAI-compatible base URL works via flags or config. No secrets are stored in
files: if the endpoint needs a key, its *name goes in config* and the value is
read from the environment at call time.

The client only ever requests suggestions; applying them is a separate,
explicit step that produces patch files, never a rewritten original.
"""

import json
import re
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.2"
DEFAULT_TIMEOUT = 60.0
SYSTEM_PROMPT = (
    "You are a careful proofreading assistant. The user gives you a short "
    "document. Find small, high-confidence surface fixes only: spelling "
    "slips, doubled words, wrong a/an, missing or doubled spaces, obvious "
    "capitalization inconsistencies within the same document. Respond with "
    "ONLY a JSON array, each item shaped as {\"find\", \"replace\", \"reason\"}. "
    "\"find\" MUST be an exact substring copied from the document. Never "
    "restructure sentences, never invent text that is not in the document, "
    "and limit yourself to the clearest issues."
)

MAX_PROMPT_CHARS = 12_000  # keep requests small and predictable


class EndpointError(RuntimeError):
    """Raised when the endpoint is unreachable, slow, or answers nonsense."""


class Endpoint:
    """Minimal OpenAI-compatible chat client using the standard library only."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key_env: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        urlopen=None,  # injectable for tests: same signature as urllib's
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env or ""
        self.timeout = timeout
        self._urlopen = urlopen or urllib.request.urlopen

    # ------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        import os

        headers = {"Content-Type": "application/json"}
        if self.api_key_env:
            value = os.environ.get(self.api_key_env, "")
            if value:
                headers["Authorization"] = f"Bearer {value}"
        return headers

    def _payload(self, text: str, max_suggestions: int) -> bytes:
        doc = text[:MAX_PROMPT_CHARS]
        user_prompt = (
            f"Proofread the following document. Return at most "
            f"{max_suggestions} suggestions as a JSON array. "
            "Document:\n\n" + doc
        )
        body = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        return json.dumps(body).encode("utf-8")

    # ------------------------------------------------------------------
    def fetch_suggestions(self, text: str, max_suggestions: int = 25) -> list[dict]:
        """Return parsed suggestions: [{find, replace, reason}, ...]."""
        url = f"{self.base_url}/chat/completions"
        request = urllib.request.Request(
            url, data=self._payload(text, max_suggestions), headers=self._headers(), method="POST"
        )
        try:
            with self._urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise EndpointError(f"endpoint HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise EndpointError(
                f"could not reach {url} ({exc}); is your local server running, "
                "or is the base URL right?"
            ) from exc

        content = self._extract_message_content(raw)
        return self._parse_suggestions(content, max_suggestions)

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_message_content(raw: str) -> str:
        try:
            payload = json.loads(raw)
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
            raise EndpointError(f"unexpected endpoint response shape: {raw[:200]!r}") from exc
        return content

    @staticmethod
    def _parse_suggestions(content: str, max_suggestions: int) -> list[dict]:
        """Tolerant parsing: accept bare arrays or fenced JSON blocks."""
        candidates: list[str] = [content]
        fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content, re.DOTALL)
        if fence:
            candidates.insert(0, fence.group(1))
        bare = re.search(r"\[\s*\{.*\}\s*\]", content, re.DOTALL)
        if bare:
            candidates.insert(0, bare.group(0))

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, list):
                continue
            suggestions = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                find = item.get("find")
                replace = item.get("replace", "")
                if not isinstance(find, str) or len(find.strip()) < 2:
                    continue
                suggestions.append(
                    {
                        "find": find,
                        "replace": replace if isinstance(replace, str) else "",
                        "reason": str(item.get("reason", ""))[:300],
                    }
                )
            if suggestions:
                return suggestions[:max_suggestions]
        raise EndpointError("the endpoint did not return a usable JSON array of suggestions")
