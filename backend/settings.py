"""Model settings, kept in backend/.env and edited from the app.

The file is the single source: the API reads it at start, Settings writes to it and
reloads it, and a person can still edit it by hand. Keys never leave this process in
full; the page is shown that a key is set and its last four characters, enough to
recognise which one.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv, set_key

from agents import base

ENV_PATH = Path(__file__).parent / ".env"

# What each provider needs, and where it lives in .env.
PROVIDERS: dict[str, dict] = {
    "claude_cli": {
        "label": "Claude Code",
        "help": "Your signed-in Claude Code session. No key; billed to the subscription. Run `claude` once in a terminal to sign in.",
        "model_env": "CLAUDE_CLI_MODEL",
    },
    "anthropic": {
        "label": "Anthropic API",
        "help": "An API key from console.anthropic.com. Faster than the CLI, metered.",
        "key_env": "ANTHROPIC_API_KEY",
        "model_env": "ANTHROPIC_MODEL",
    },
    "openai": {
        "label": "OpenAI, or any OpenAI-compatible endpoint",
        "help": "An API key from platform.openai.com. Set a base URL to use another provider that speaks the same API: Ollama, Groq, OpenRouter, Mistral.",
        "key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "base_url_env": "OPENAI_BASE_URL",
    },
    "azure": {
        "label": "Azure OpenAI",
        "help": "Your resource endpoint and a deployment name.",
        "key_env": "AZURE_OPENAI_API_KEY",
        "model_env": "AZURE_OPENAI_DEPLOYMENT",
        "endpoint_env": "AZURE_OPENAI_ENDPOINT",
    },
}


def _hint(value: str) -> str:
    """The tail of a key, enough to tell two apart, never enough to use."""
    return value[-4:] if len(value) >= 8 else ""


def current() -> dict:
    """What the page shows. No key values."""
    try:
        active = base.get_provider()
        problem = ""
    except RuntimeError as exc:
        active = os.environ.get("LLM_PROVIDER", "") or ""
        problem = str(exc)

    providers = {}
    for name, spec in PROVIDERS.items():
        key = os.environ.get(spec.get("key_env", ""), "") if spec.get("key_env") else ""
        providers[name] = {
            "label": spec["label"],
            "help": spec["help"],
            "model": os.environ.get(spec["model_env"], "") or "",
            "default_model": base.DEFAULT_MODELS[name],
            "needs_key": bool(spec.get("key_env")),
            "key_set": bool(key),
            "key_hint": _hint(key),
            "base_url": os.environ.get(spec.get("base_url_env", ""), "") if spec.get("base_url_env") else None,
            "endpoint": os.environ.get(spec.get("endpoint_env", ""), "") if spec.get("endpoint_env") else None,
        }
    return {"provider": active, "problem": problem, "providers": providers, "env_path": str(ENV_PATH),
            "contact_email": contact_email()}


def save(provider: str, model: str = "", api_key: str = "", base_url: str | None = None,
         endpoint: str | None = None) -> dict:
    """Write one provider's settings and make them live. An empty key keeps the old one."""
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise ValueError(f"Unknown provider {provider!r}. Use one of {', '.join(PROVIDERS)}.")

    ENV_PATH.touch(exist_ok=True)
    _set("LLM_PROVIDER", provider)
    _set(spec["model_env"], model.strip())
    if spec.get("key_env") and api_key.strip():
        _set(spec["key_env"], api_key.strip())
    if spec.get("base_url_env") and base_url is not None:
        _set(spec["base_url_env"], base_url.strip())
    if spec.get("endpoint_env") and endpoint is not None:
        _set(spec["endpoint_env"], endpoint.strip())

    load_dotenv(ENV_PATH, override=True)
    # An empty value in the file must not leave a stale one in the process.
    for env in (spec["model_env"], spec.get("base_url_env"), spec.get("endpoint_env")):
        if env and not _read(env):
            os.environ.pop(env, None)
    base.reset()
    return current()


CONTACT_ENV = "UNPAYWALL_EMAIL"


def contact_email() -> str:
    return _read(CONTACT_ENV)


def save_contact(email: str) -> str:
    """The address Unpaywall asks for when the app looks up where a paper's PDF lives."""
    ENV_PATH.touch(exist_ok=True)
    _set(CONTACT_ENV, email.strip())
    load_dotenv(ENV_PATH, override=True)
    if not email.strip():
        os.environ.pop(CONTACT_ENV, None)
    return contact_email()


def _set(key: str, value: str) -> None:
    set_key(str(ENV_PATH), key, value, quote_mode="always")


def _read(key: str) -> str:
    from dotenv import dotenv_values

    return dotenv_values(ENV_PATH).get(key) or ""
