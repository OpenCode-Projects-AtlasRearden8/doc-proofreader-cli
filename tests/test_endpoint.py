import io
import json
import urllib.error

import pytest

from docproof.endpoint import DEFAULT_BASE_URL, Endpoint, EndpointError

CONTENT_BARE = json.dumps(
    {
        "choices": [
            {"message": {"content": json.dumps(
                [
                    {"find": "recieved", "replace": "received", "reason": "misspelling"},
                    {"find": "an apple", "replace": "a apple", "reason": "ignore"},
                ]
            )}}
        ]
    }
)

CONTENT_FENCED = json.dumps(
    {
        "choices": [
            {
                "message": {
                    "content": "Sure! Here you go:\n```json\n"
                    + json.dumps(
                        [
                            {
                                "find": "very",
                                "replace": "",
                                "reason": "filler word",
                            }
                        ]
                    )
                    + "\n```\nHope that helps."
                }
            }
        ]
    }
)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def endpoint_with(content: str, url_assert=None) -> Endpoint:
    def fake_urlopen(request, timeout=None):
        if url_assert:
            url_assert(request)
        return FakeResponse(content.encode("utf-8"))

    return Endpoint(base_url=DEFAULT_BASE_URL, model="llama3.2", urlopen=fake_urlopen)


def test_parses_bare_json_from_endpoint():
    seen = {}

    def check_url(request):
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["model"] = json.loads(request.data.decode())["model"]

    endpoint = endpoint_with(CONTENT_BARE, check_url)
    suggestions = endpoint.fetch_suggestions("We recieved the memo.")
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert seen["method"] == "POST"
    assert seen["model"] == "llama3.2"
    assert suggestions[0]["find"] == "recieved"
    assert suggestions[0]["replace"] == "received"


def test_parses_fenced_json_block():
    suggestions = endpoint_with(CONTENT_FENCED).fetch_suggestions("It was very good.")
    assert suggestions == [{"find": "very", "replace": "", "reason": "filler word"}]


def test_custom_base_url_is_used():
    def make_with(url):
        def fake_urlopen(request, timeout=None):
            assert request.full_url == f"{url}/chat/completions"
            return FakeResponse(CONTENT_BARE.encode("utf-8"))

        return Endpoint(base_url=url, urlopen=fake_urlopen)

    assert make_with("https://api.example.com/v1").fetch_suggestions("x")


def test_garbage_answer_raises_endpoint_error():
    bad = json.dumps({"choices": [{"message": {"content": "I found no issues, sorry!"}}]})
    with pytest.raises(EndpointError):
        endpoint_with(bad).fetch_suggestions("text")


def test_http_error_is_wrapped():
    def boom(request, timeout=None):
        raise urllib.error.HTTPError("http://localhost:11434/v1", 404, "not found", None, None)

    endpoint = Endpoint(urlopen=boom)
    with pytest.raises(EndpointError, match="HTTP 404"):
        endpoint.fetch_suggestions("text")


def test_connection_error_message_mentions_url():
    def boom(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    endpoint = Endpoint(urlopen=boom)
    with pytest.raises(EndpointError, match="localhost:11434"):
        endpoint.fetch_suggestions("text")


def test_api_key_env_never_stored_in_payload(monkeypatch):
    fake_key = "fake-key-only-for-tests"
    monkeypatch.setenv("MY_MODEL_KEY", fake_key)
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = request.data
        return FakeResponse(CONTENT_BARE.encode("utf-8"))

    endpoint = Endpoint(api_key_env="MY_MODEL_KEY", urlopen=fake_urlopen)
    endpoint.fetch_suggestions("text")
    assert seen["auth"].startswith("Bearer fake-")
    # and the key value never lands in the request body itself
    assert fake_key.encode() not in seen["body"]


def test_short_find_values_are_dropped():
    content = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            [
                                {"find": "a", "replace": "b", "reason": "too short"},
                                {"find": "", "replace": "x", "reason": "empty"},
                                {"find": "recieved", "replace": "received", "reason": "ok"},
                            ]
                        )
                    }
                }
            ]
        }
    )
    suggestions = endpoint_with(content).fetch_suggestions("We recieved the memo.")
    assert [s["find"] for s in suggestions] == ["recieved"]


def test_max_suggestions_cap():
    voluminous = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            [{"find": f"word{i}", "replace": "fix", "reason": "r"} for i in range(50)]
                        )
                    }
                }
            ]
        }
    )
    suggestions = endpoint_with(voluminous).fetch_suggestions("word0 word1", max_suggestions=5)
    assert len(suggestions) == 5
