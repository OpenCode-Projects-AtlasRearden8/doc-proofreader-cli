"""Config file support: ``proofreader.toml`` next to the doc, or --config PATH.

Every key is optional; CLI flags always win over the file.

Example TOML:

    [endpoint]
    base_url = "http://localhost:11434/v1"
    model    = "llama3.2"
    api_key_env = ""          # name only; the value comes from the environment

    [rules]
    enabled     = ["typos", "repeated_words", "case_inconsistency"]
    extra_typos = { "hte" = "the", "mispell" = "misspell" }
"""

import tomllib
from pathlib import Path

from .endpoint import DEFAULT_BASE_URL, DEFAULT_MODEL


class ConfigError(ValueError):
    pass


def load_config(path: str | None) -> dict:
    """Read a TOML config, returning {} for absent/empty configs."""
    if path is None:
        default = Path("proofreader.toml")
        if not default.is_file():
            return {}
        path = str(default)
    file = Path(path)
    if not file.is_file():
        raise ConfigError(f"config file not found: {file}")
    try:
        with file.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {file}: {exc}") from exc
    return _validate(data, file)


def _validate(data: dict, source: Path) -> dict:
    if not isinstance(data, dict):
        raise ConfigError(f"config must be a TOML table: {source}")
    endpoint = data.get("endpoint") or {}
    rules = data.get("rules") or {}
    out: dict = {}
    if endpoint:
        allowed = {"base_url", "model", "api_key_env", "timeout"}
        unknown = set(endpoint) - allowed
        if unknown:
            raise ConfigError(f"{source}: unknown [endpoint] keys: {', '.join(sorted(unknown))}")
        out["endpoint"] = {k: v for k, v in endpoint.items() if v not in (None, "")}
    if rules:
        allowed = {"enabled", "extra_typos"}
        unknown = set(rules) - allowed
        if unknown:
            raise ConfigError(f"{source}: unknown [rules] keys: {', '.join(sorted(unknown))}")
        rules_out: dict = {}
        if "enabled" in rules and rules["enabled"] not in (None, []):
            values = rules["enabled"]
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                raise ConfigError(f"{source}: rules.enabled must be a list of rule names")
            from .rules import RULES

            bad = set(values) - set(RULES)
            if bad:
                raise ConfigError(
                    f"{source}: unknown rule(s): {', '.join(sorted(bad))}. "
                    f"Valid rules: {', '.join(RULES)}"
                )
            rules_out["enabled"] = values
        if rules.get("extra_typos"):
            pairs = rules["extra_typos"]
            if not isinstance(pairs, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in pairs.items()
            ):
                raise ConfigError(f"{source}: rules.extra_typos must be a table of word = fix")
            rules_out["extra_typos"] = pairs
        if rules_out:
            out["rules"] = rules_out
    return out


def endpoint_overrides(config: dict) -> dict:
    merged: dict = {
        "base_url": DEFAULT_BASE_URL,
        "model": DEFAULT_MODEL,
    }
    merged.update(config.get("endpoint", {}))
    return merged
