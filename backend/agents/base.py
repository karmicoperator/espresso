"""Model provider resolution and the two call helpers every agent uses.

Two providers:

* ``claude_cli`` (default): a headless Claude Code session. No API key, no metered
  billing. See `claude_cli.py` for what it takes to run one cleanly.
* ``azure``: Azure OpenAI through the OpenAI SDK, for a machine without Claude Code.
"""

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


def _azure_deployment() -> str:
    """The Azure *deployment name*, which defaults to the model name (e.g. "gpt-5")."""
    return os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5")


# GPT-5 reasoning tokens count against max_completion_tokens. Agents size
# max_tokens for the *visible* answer, so give the model extra room to think
# or it can return an empty message after exhausting the cap on reasoning.
_AZURE_REASONING_HEADROOM = 4096


def _detect_provider() -> str:
    """Resolve the LLM provider from env: LLM_PROVIDER wins, else auto-detect."""
    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower().replace("-", "_")
    aliases = {"cli": "claude_cli", "claude": "claude_cli", "claudecode": "claude_cli",
               "claude_code": "claude_cli", "subscription": "claude_cli"}
    explicit = aliases.get(explicit, explicit)

    if explicit == "azure":
        _require_azure_env()
        return "azure"
    if explicit == "claude_cli":
        _require_claude_cli()
        return "claude_cli"
    if explicit:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER={explicit!r}. Use 'claude_cli' or 'azure'."
        )

    if os.environ.get("AZURE_OPENAI_API_KEY") and os.environ.get("AZURE_OPENAI_ENDPOINT"):
        return "azure"

    # No keys configured: fall back to a headless Claude Code session if one is available,
    # so the pipeline runs on a subscription with nothing to provision.
    from agents import claude_cli as _cli

    if _cli.is_available()[0]:
        return "claude_cli"

    raise RuntimeError(
        "No LLM provider configured. Install Claude Code (LLM_PROVIDER=claude_cli), or set "
        "AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT."
    )


def _require_claude_cli() -> None:
    from agents import claude_cli as _cli

    ok, reason = _cli.is_available()
    if not ok:
        raise RuntimeError(f"LLM_PROVIDER=claude_cli but {reason}")


def _require_azure_env() -> None:
    missing = [
        k for k in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT")
        if not os.environ.get(k)
    ]
    if missing:
        raise RuntimeError(f"LLM_PROVIDER=azure but missing env vars: {', '.join(missing)}")


def get_provider() -> str:
    """Get the current provider name (validates env on every call)."""
    return _detect_provider()


# ---------------------------------------------------------------------------
# Azure OpenAI (GPT-5 family)
# ---------------------------------------------------------------------------

_azure_async_client = None
_azure_sync_client = None


def _azure_base_url() -> str:
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    return f"{endpoint}/openai/v1/"


def _get_azure_client():
    global _azure_async_client  # noqa: PLW0603 — lazy singleton cache
    if _azure_async_client is None:
        from openai import AsyncOpenAI

        _azure_async_client = AsyncOpenAI(
            base_url=_azure_base_url(),
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            timeout=300.0,  # 5 min — large paper summarization needs headroom
        )
    return _azure_async_client


def _get_azure_sync_client():
    global _azure_sync_client  # noqa: PLW0603 — lazy singleton cache
    if _azure_sync_client is None:
        from openai import OpenAI

        _azure_sync_client = OpenAI(
            base_url=_azure_base_url(),
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            timeout=300.0,
        )
    return _azure_sync_client


def _azure_model(model: str | None) -> str:
    """Map a requested model to an Azure deployment name.

    Claude model names map to the configured deployment; explicit gpt-* names pass through.
    """
    if not model or model.startswith("claude") or "/" in model:
        return _azure_deployment()
    return model


def _azure_request_kwargs(
    model: str, prompt: str, system_prompt: str, max_tokens: int
) -> dict:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_tokens + _AZURE_REASONING_HEADROOM,
    }
    # minimal | low | medium | high — low keeps the pipeline fast/cheap
    kwargs["reasoning_effort"] = os.environ.get("AZURE_OPENAI_REASONING_EFFORT", "low")
    return kwargs


# ---------------------------------------------------------------------------
# Call helpers
# ---------------------------------------------------------------------------

async def call_llm(
    prompt: str,
    model: str | None = None,
    system_prompt: str = "",
    max_tokens: int = 4096,
    name: str | None = None,
) -> str:
    """Async LLM call routed through the configured provider."""
    provider = get_provider()
    input_words = len(prompt.split())
    t0 = time.monotonic()

    if provider == "claude_cli":
        from agents import claude_cli as _cli

        resolved = _cli.resolve_model(model)
        logger.info(f"[LLM] Calling claude-cli/{resolved} ({input_words} input words)")
        try:
            output = await _cli.call(
                prompt, model=resolved, system_prompt=system_prompt, label=name or "call"
            )
            logger.info(
                f"[LLM] claude-cli/{resolved} responded in {time.monotonic() - t0:.1f}s "
                f"({len(output.split())} output words)"
            )
            return output
        except Exception as e:
            logger.error(
                f"[LLM] claude-cli/{resolved} FAILED after {time.monotonic() - t0:.1f}s: "
                f"{type(e).__name__}: {e}"
            )
            raise

    resolved = _azure_model(model)
    logger.info(f"[LLM] Calling azure/{resolved} ({input_words} input words, max_tokens={max_tokens})")
    try:
        client = _get_azure_client()
        resp = await client.chat.completions.create(
            **_azure_request_kwargs(resolved, prompt, system_prompt, max_tokens)
        )
        output = resp.choices[0].message.content or ""
        elapsed = time.monotonic() - t0
        logger.info(f"[LLM] azure/{resolved} responded in {elapsed:.1f}s ({len(output.split())} output words)")
        return output
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.error(f"[LLM] azure/{resolved} FAILED after {elapsed:.1f}s: {type(e).__name__}: {e}")
        raise


def call_llm_sync(
    prompt: str,
    model: str | None = None,
    system_prompt: str = "",
    max_tokens: int = 4096,
    name: str | None = None,
) -> str:
    """Synchronous LLM call routed through the configured provider."""
    provider = get_provider()

    if provider == "claude_cli":
        from agents import claude_cli as _cli

        return _cli.call_sync(
            prompt, model=model, system_prompt=system_prompt, label=name or "call"
        )

    resolved = _azure_model(model)
    client = _get_azure_sync_client()
    resp = client.chat.completions.create(
        **_azure_request_kwargs(resolved, prompt, system_prompt, max_tokens)
    )
    return resp.choices[0].message.content or ""
