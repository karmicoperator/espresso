"""LLM provider backed by a headless Claude Code session.

Runs the pipeline on a Claude subscription instead of metered API credits. Each call is
one `claude -p` invocation: prompt on stdin, JSON envelope on stdout.

Three things this has to do that the API providers do not:

* **Strip the harness.** `--system-prompt` replaces Claude Code's own system prompt, MCP
  servers are dropped, and built-in tools are disabled. Left in, they add roughly 34k
  tokens of irrelevant context to every call and invite the model to go and read files
  instead of answering. Stripped, the floor is about 18.5k, and it is cache-read.
* **Allow more than one turn.** A long reply spans turns internally and the CLI exits with
  `error_max_turns`. Four is enough and still stops a runaway; tools are disabled, so there
  is nothing for extra turns to do but finish the answer.
* **Read stdout on failure.** The CLI reports most errors as a JSON envelope on stdout, not
  on stderr. Reading only stderr yields "exit 1: no output" for a failure whose full
  diagnosis was sitting in the other stream.

There is no prompt caching we control, so the paper text is re-sent on every call. That is
latency rather than billing on a subscription, but it makes extraction on a long paper run
into minutes. Size timeouts accordingly.
"""

from __future__ import annotations

import asyncio
import getpass
import json
import logging
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache

logger = logging.getLogger(__name__)

#: This is a text task, and a model that can reach for Bash will.
DISALLOWED_TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch", "Task", "TodoWrite", "NotebookEdit", "BashOutput", "KillShell", "SlashCommand", "Skill", "Artifact"]

#: One turn is not enough for a long structured reply.
MAX_TURNS = "4"

#: Non-zero exits are usually transient, so give the CLI a few goes.
EXIT_RETRIES = 3

DEFAULT_MODEL = "claude-opus-5"

_FRIENDLY = {
    "error_max_turns": "the reply needed more turns than allowed",
    "error_during_execution": "the CLI failed mid-run",
    "refusal": "the model declined the request",
}


class ClaudeCLIError(RuntimeError):
    """The CLI could not produce a reply."""


def is_available() -> tuple[bool, str]:
    """Whether `claude` is installed. Says nothing about whether it can log in."""
    if not shutil.which("claude"):
        return False, "The `claude` CLI is not on PATH. Install Claude Code, or set another provider."
    return True, ""


@lru_cache(maxsize=1)
def check_auth() -> tuple[bool, str]:
    """Whether the CLI can actually authenticate, asked once per process.

    Being on PATH is not the same as being usable. A server started without USER in its
    environment finds the binary, reports itself healthy, and then fails every build with
    "Not logged in" several minutes in, which is a long way from the cause.

    Failure is fast when it fails, so this costs little: the CLI returns "Not logged in" in
    about a tenth of a second. A working call takes a few seconds, and only the first
    caller pays it.
    """
    ok, why = is_available()
    if not ok:
        return False, why
    try:
        proc = subprocess.run(
            [
                "claude", "-p", "--output-format", "json", "--max-turns", "2",
                "--strict-mcp-config", "--mcp-config", _empty_mcp_config(),
                "--disallowed-tools", *DISALLOWED_TOOLS,
            ],
            input="hi",
            capture_output=True,
            text=True,
            timeout=45,
            env=_child_env(),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"the `claude` CLI did not answer ({type(exc).__name__})"

    blob = f"{proc.stdout}\n{proc.stderr}"
    if "Not logged in" in blob or "/login" in blob:
        return False, "the `claude` CLI is installed but not logged in. Run `claude` in a terminal and sign in."
    if proc.returncode != 0:
        return False, f"the `claude` CLI exited {proc.returncode}"
    return True, ""


def _child_env() -> dict[str, str]:
    """The environment the CLI is given.

    USER is load-bearing: without it the CLI cannot reach its stored credentials and
    reports "Not logged in", even though the credentials are there. A GUI launch or a
    stripped service environment is exactly where it goes missing.
    """
    env = dict(os.environ)
    if not env.get("USER"):
        env["USER"] = env.get("LOGNAME") or getpass.getuser()
    env.setdefault("LOGNAME", env["USER"])
    if not env.get("HOME"):
        env["HOME"] = os.path.expanduser("~")
    return env


@lru_cache(maxsize=1)
def _empty_mcp_config() -> str:
    """A config with no servers, so --strict-mcp-config drops every MCP tool.

    The file has to outlive this function -- the CLI reads it on every call -- so it is
    written once and kept for the life of the process.
    """
    fd, path = tempfile.mkstemp(suffix="-empty-mcp.json", text=True)
    with os.fdopen(fd, "w") as handle:
        json.dump({"mcpServers": {}}, handle)
    return path


def resolve_model(model: str | None) -> str:
    return model or os.environ.get("CLAUDE_CLI_MODEL", DEFAULT_MODEL)


def _argv(model: str, system_prompt: str) -> list[str]:
    return [
        "claude",
        "-p",
        "--system-prompt", system_prompt or "You are a precise assistant. Answer directly.",
        "--output-format", "json",
        "--model", model,
        "--max-turns", MAX_TURNS,
        "--exclude-dynamic-system-prompt-sections",
        "--strict-mcp-config",
        "--mcp-config", _empty_mcp_config(),
        "--disallowed-tools", *DISALLOWED_TOOLS,
    ]


def _explain(stdout: str, stderr: str) -> str:
    """A one-line reason from the CLI's failure envelope, not 600 characters of JSON."""
    for blob in (stdout, stderr):
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        subtype = data.get("subtype") or data.get("terminal_reason") or ""
        errors = data.get("errors") or []
        friendly = _FRIENDLY.get(subtype)
        if friendly or errors:
            joined = "; ".join(str(e) for e in errors[:2])
            return f"{friendly or subtype}{f' ({joined})' if joined else ''}"
    return (stderr or stdout or "no output")[-300:]


def _parse(stdout: bytes, stderr: bytes, returncode: int, label: str) -> str:
    if returncode != 0:
        out = (stdout or b"").decode("utf-8", "replace").strip()
        err = (stderr or b"").decode("utf-8", "replace").strip()
        raise ClaudeCLIError(f"{label}: claude exited {returncode}: {_explain(out, err)}")

    raw = (stdout or b"").decode("utf-8", "replace").strip()
    if not raw:
        raise ClaudeCLIError(f"{label}: claude returned nothing")
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ClaudeCLIError(f"{label}: unparsable CLI output: {raw[:200]}") from exc

    if envelope.get("is_error"):
        raise ClaudeCLIError(f"{label}: {envelope.get('result') or 'the CLI reported an error'}")

    result = envelope.get("result")
    if not isinstance(result, str) or not result.strip():
        raise ClaudeCLIError(f"{label}: empty result")

    usage = envelope.get("usage") or {}
    logger.info(
        "[LLM] claude-cli/%s responded (out=%s tokens, cached=%s)",
        envelope.get("model") or "?",
        usage.get("output_tokens"),
        usage.get("cache_read_input_tokens"),
    )
    return result.strip()


async def call(
    prompt: str,
    model: str | None = None,
    system_prompt: str = "",
    timeout: float = 1200.0,
    label: str = "call",
) -> str:
    """One headless call, retried on a transient non-zero exit."""
    resolved = resolve_model(model)
    delay = 4.0

    for attempt in range(1, EXIT_RETRIES + 1):
        try:
            proc = await asyncio.create_subprocess_exec(
                *_argv(resolved, system_prompt),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_child_env(),
            )
        except OSError as exc:
            raise ClaudeCLIError(f"{label}: could not start claude ({exc})") from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8")), timeout=timeout
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise ClaudeCLIError(f"{label}: claude exceeded {timeout:.0f}s") from None

        try:
            return _parse(stdout, stderr, proc.returncode, label)
        except ClaudeCLIError as exc:
            if "exited" not in str(exc) or attempt == EXIT_RETRIES:
                raise
            logger.warning("%s: %s — retrying in %.0fs", label, str(exc)[-120:], delay)
            await asyncio.sleep(delay)
            delay *= 2

    raise ClaudeCLIError(f"{label}: exhausted CLI retries")


def call_sync(
    prompt: str,
    model: str | None = None,
    system_prompt: str = "",
    timeout: float = 1200.0,
    label: str = "call",
) -> str:
    """Blocking variant, for the sync agent paths."""
    resolved = resolve_model(model)
    try:
        proc = subprocess.run(
            _argv(resolved, system_prompt),
            input=prompt.encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            check=False,
            env=_child_env(),
        )
    except subprocess.TimeoutExpired:
        raise ClaudeCLIError(f"{label}: claude exceeded {timeout:.0f}s") from None
    except OSError as exc:
        raise ClaudeCLIError(f"{label}: could not start claude ({exc})") from exc

    return _parse(proc.stdout, proc.stderr, proc.returncode, label)
