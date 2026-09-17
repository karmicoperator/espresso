"""Model providers and the one call helper every agent uses.

Four providers, chosen in Settings or by LLM_PROVIDER in backend/.env:

* ``claude_cli``  a signed-in Claude Code session. No key, billed to the subscription.
* ``anthropic``   the Anthropic API with your own key, through the official SDK.
* ``openai``      the OpenAI API with your own key, or any OpenAI-compatible endpoint
                  (Ollama, Groq, OpenRouter, ...) through OPENAI_BASE_URL.
* ``azure``       Azure OpenAI, keyed by deployment name.

Nothing here reads a key except to build a client, and nothing logs one.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, use system env vars

PROVIDERS = ("claude_cli", "anthropic", "openai", "azure")

DEFAULT_MODELS = {
    "claude_cli": "claude-opus-5",
    "anthropic": "claude-opus-5",
    "openai": "gpt-5",
    "azure": "gpt-5",
}

# GPT-5 reasoning tokens count against max_completion_tokens. Agents size max_tokens for
# the visible answer, so give the model extra room to think or it can return an empty
# message after exhausting the cap on reasoning.
_REASONING_HEADROOM = 4096


# ---------------------------------------------------------------------------
# Which provider
# ---------------------------------------------------------------------------

def _detect_provider() -> str:
    """Resolve the provider from env: LLM_PROVIDER wins, else the first configured one."""
    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower().replace("-", "_")
    aliases = {"cli": "claude_cli", "claude": "claude_cli", "claudecode": "claude_cli",
               "claude_code": "claude_cli", "subscription": "claude_cli",
               "anthropic_api": "anthropic"}
    explicit = aliases.get(explicit, explicit)

    if explicit:
        if explicit not in PROVIDERS:
            raise RuntimeError(
                f"Unknown LLM_PROVIDER={explicit!r}. Use one of {', '.join(PROVIDERS)}."
            )
        _require(explicit)
        return explicit

    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("AZURE_OPENAI_API_KEY") and os.environ.get("AZURE_OPENAI_ENDPOINT"):
        return "azure"

    # No keys configured: fall back to a headless Claude Code session if one is available,
    # so the pipeline runs on a subscription with nothing to provision.
    from agents import claude_cli as _cli

    if _cli.is_available()[0]:
        return "claude_cli"

    raise RuntimeError(
        "No model provider configured. Open Settings in the app, or install Claude Code "
        "and sign in."
    )


def _require(provider: str) -> None:
    """The env a provider needs, named precisely when missing."""
    if provider == "claude_cli":
        from agents import claude_cli as _cli

        ok, reason = _cli.is_available()
        if not ok:
            raise RuntimeError(f"LLM_PROVIDER=claude_cli but {reason}")
    elif provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set")
    elif provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
    elif provider == "azure":
        missing = [k for k in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT") if not os.environ.get(k)]
        if missing:
            raise RuntimeError(f"LLM_PROVIDER=azure but missing env vars: {', '.join(missing)}")


def get_provider() -> str:
    """The current provider name (validates env on every call)."""
    return _detect_provider()


def resolve_model(provider: str, model: str | None = None) -> str:
    """The model an agent's request maps to for this provider."""
    if provider == "claude_cli":
        from agents import claude_cli as _cli

        return _cli.resolve_model(model)
    if provider == "anthropic":
        if model and model.startswith("claude"):
            return model
        return os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODELS["anthropic"]
    if provider == "openai":
        if model and not model.startswith("claude"):
            return model
        return os.environ.get("OPENAI_MODEL") or DEFAULT_MODELS["openai"]
    # azure: a deployment name. Claude model names from the agents map to it.
    if model and not model.startswith("claude") and "/" not in model:
        return model
    return os.environ.get("AZURE_OPENAI_DEPLOYMENT") or DEFAULT_MODELS["azure"]


# ---------------------------------------------------------------------------
# Clients, built once per process and dropped when Settings change
# ---------------------------------------------------------------------------

_clients: dict[str, object] = {}
_probes: dict[str, tuple[bool, str]] = {}


def reset() -> None:
    """Forget cached clients and probe results. Called after Settings are saved."""
    _clients.clear()
    _probes.clear()
    try:
        from agents.claude_cli import check_auth

        check_auth.cache_clear()
    except ImportError:
        pass


def _anthropic_client():
    if "anthropic" not in _clients:
        from anthropic import AsyncAnthropic

        # A whole paper goes in and thousands of tokens come out; ten minutes is the SDK
        # default and a long paper on a slow day can use most of it.
        _clients["anthropic"] = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=600.0)
    return _clients["anthropic"]


def _openai_client():
    if "openai" not in _clients:
        from openai import AsyncOpenAI

        _clients["openai"] = AsyncOpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
            timeout=600.0,
        )
    return _clients["openai"]


def _azure_client():
    if "azure" not in _clients:
        from openai import AsyncOpenAI

        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
        _clients["azure"] = AsyncOpenAI(
            base_url=f"{endpoint}/openai/v1/",
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            timeout=600.0,
        )
    return _clients["azure"]


# ---------------------------------------------------------------------------
# The calls
# ---------------------------------------------------------------------------

async def _call_anthropic(model: str, prompt: str, system_prompt: str, max_tokens: int) -> str:
    client = _anthropic_client()
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt
    # Opus 5 and Fable can decline a request on a safety classifier. With fallbacks the
    # API re-runs the same request on another model inside the same call instead of
    # handing back a refusal three minutes into a build. Thinking is adaptive by default
    # on these models, so no thinking parameter is sent.
    if model.startswith(("claude-opus-5", "claude-fable")):
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"

    # Streamed so a long reply cannot hit the HTTP timeout; only the final message is used.
    async with client.beta.messages.stream(**kwargs) as stream:
        message = await stream.get_final_message()

    if message.stop_reason == "refusal":
        why = getattr(getattr(message, "stop_details", None), "explanation", "") or ""
        raise RuntimeError(f"the model declined this request{': ' + why if why else ''}")
    if message.stop_reason == "max_tokens":
        logger.warning("[LLM] anthropic/%s hit max_tokens=%d; the reply is cut short", model, max_tokens)
    return "".join(block.text for block in message.content if block.type == "text")


def _chat_kwargs(model: str, prompt: str, system_prompt: str, max_tokens: int, native: bool) -> dict:
    """Chat Completions request. `native` is OpenAI or Azure itself, where GPT-5 takes
    max_completion_tokens and reasoning_effort; a compatible endpoint may reject both."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    kwargs: dict = {"model": model, "messages": messages}
    reasoning = native and (model.startswith("gpt-5") or model.startswith("o"))
    if reasoning:
        kwargs["max_completion_tokens"] = max_tokens + _REASONING_HEADROOM
        # minimal | low | medium | high — low keeps the pipeline fast/cheap
        kwargs["reasoning_effort"] = os.environ.get("OPENAI_REASONING_EFFORT") or os.environ.get(
            "AZURE_OPENAI_REASONING_EFFORT", "low"
        )
    else:
        kwargs["max_tokens"] = max_tokens
    return kwargs


async def _call_chat(client, model: str, prompt: str, system_prompt: str, max_tokens: int, native: bool) -> str:
    resp = await client.chat.completions.create(**_chat_kwargs(model, prompt, system_prompt, max_tokens, native))
    return resp.choices[0].message.content or ""


async def call_llm(
    prompt: str,
    model: str | None = None,
    system_prompt: str = "",
    max_tokens: int = 4096,
    name: str | None = None,
) -> str:
    """Async LLM call routed through the configured provider."""
    provider = get_provider()
    resolved = resolve_model(provider, model)
    input_words = len(prompt.split())
    t0 = time.monotonic()
    logger.info(f"[LLM] Calling {provider}/{resolved} ({input_words} input words)")
    try:
        if provider == "claude_cli":
            from agents import claude_cli as _cli

            output = await _cli.call(prompt, model=resolved, system_prompt=system_prompt, label=name or "call")
        elif provider == "anthropic":
            output = await _call_anthropic(resolved, prompt, system_prompt, max_tokens)
        elif provider == "openai":
            native = not os.environ.get("OPENAI_BASE_URL")
            output = await _call_chat(_openai_client(), resolved, prompt, system_prompt, max_tokens, native)
        else:
            output = await _call_chat(_azure_client(), resolved, prompt, system_prompt, max_tokens, True)
    except Exception as e:
        logger.error(
            f"[LLM] {provider}/{resolved} FAILED after {time.monotonic() - t0:.1f}s: "
            f"{type(e).__name__}: {e}"
        )
        raise
    logger.info(
        f"[LLM] {provider}/{resolved} responded in {time.monotonic() - t0:.1f}s "
        f"({len(output.split())} output words)"
    )
    return output


# ---------------------------------------------------------------------------
# Can it actually build? One tiny call, remembered per configuration.
# ---------------------------------------------------------------------------

def _config_key() -> str:
    """Changes whenever anything that affects a call changes, without holding a key."""
    import hashlib

    parts = [os.environ.get(k, "") for k in (
        "LLM_PROVIDER", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL",
        "OPENAI_BASE_URL", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT",
        "CLAUDE_CLI_MODEL",
    )]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


async def probe(force: bool = False) -> tuple[bool, str]:
    """Whether the configured provider answers. Cached per configuration.

    Being configured is not the same as working: a mistyped key, a model the account
    cannot see, or a signed-out CLI all look configured. Failure is fast when it fails,
    so the probe costs a few hundred tokens at most, once.
    """
    try:
        provider = get_provider()
    except RuntimeError as exc:
        return False, str(exc)

    key = _config_key()
    if not force and key in _probes:
        return _probes[key]

    if provider == "claude_cli":
        from agents.claude_cli import check_auth

        result = check_auth()
    else:
        result = await _probe_api(provider)
    _probes[key] = result
    return result


async def _probe_api(provider: str) -> tuple[bool, str]:
    model = resolve_model(provider)
    try:
        if provider == "anthropic":
            import anthropic

            try:
                client = _anthropic_client().with_options(max_retries=1, timeout=45.0)
                async with client.beta.messages.stream(
                    model=model, max_tokens=64,
                    messages=[{"role": "user", "content": "Reply with the single word OK."}],
                ) as stream:
                    await stream.get_final_message()
            except anthropic.AuthenticationError:
                return False, "the Anthropic API key was rejected"
            except anthropic.NotFoundError:
                return False, f"the Anthropic API has no model called {model} for this key"
            except anthropic.APIStatusError as exc:
                return False, f"the Anthropic API answered {exc.status_code}: {_short(exc)}"
            except anthropic.APIConnectionError:
                return False, "could not reach the Anthropic API"
        else:
            import openai

            client = _openai_client() if provider == "openai" else _azure_client()
            native = provider == "azure" or not os.environ.get("OPENAI_BASE_URL")
            where = {"openai": "OpenAI", "azure": "Azure OpenAI"}[provider]
            if provider == "openai" and os.environ.get("OPENAI_BASE_URL"):
                where = os.environ["OPENAI_BASE_URL"]
            try:
                kwargs = _chat_kwargs(model, "Reply with the single word OK.", "", 32, native)
                await client.with_options(max_retries=1, timeout=45.0).chat.completions.create(**kwargs)
            except openai.AuthenticationError:
                return False, f"{where} rejected the API key"
            except openai.NotFoundError:
                return False, f"{where} has no model called {model}"
            except openai.APIStatusError as exc:
                return False, f"{where} answered {exc.status_code}: {_short(exc)}"
            except openai.APIConnectionError:
                return False, f"could not reach {where}"
    except Exception as exc:  # a client that cannot even be built
        return False, f"{type(exc).__name__}: {exc}"
    return True, ""


def _short(exc: Exception) -> str:
    text = str(getattr(exc, "message", "") or exc)
    return text[:160]
