"""Settings round-trip through .env, key masking, the loopback guard, and provider wiring."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

import settings
from agents import base


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    monkeypatch.setattr(settings, "ENV_PATH", path)
    for k in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "OPENAI_API_KEY",
              "OPENAI_MODEL", "OPENAI_BASE_URL", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"):
        monkeypatch.delenv(k, raising=False)
    return path


def test_save_writes_env_and_makes_it_live_without_exposing_the_key(env_file):
    out = settings.save("openai", model="gpt-5", api_key="sk-test-1234567890abcd", base_url="")
    text = env_file.read_text()
    assert "LLM_PROVIDER='openai'" in text and "OPENAI_API_KEY='sk-test-1234567890abcd'" in text
    assert os.environ["OPENAI_API_KEY"] == "sk-test-1234567890abcd"
    assert base.get_provider() == "openai"
    view = out["providers"]["openai"]
    assert view["key_set"] is True and view["key_hint"] == "abcd"
    assert "sk-test" not in str(out)


def test_empty_key_keeps_the_old_one_and_model_can_be_cleared(env_file):
    settings.save("anthropic", model="claude-opus-5", api_key="sk-ant-abcdefghijkl")
    settings.save("anthropic", model="", api_key="")
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-abcdefghijkl"
    assert "ANTHROPIC_MODEL" not in os.environ
    assert base.resolve_model("anthropic") == "claude-opus-5"


def test_unknown_provider_is_refused(env_file):
    with pytest.raises(ValueError):
        settings.save("bard")


def test_settings_routes_refuse_other_machines(env_file):
    from main import app

    local = TestClient(app)  # testclient's client address is "testclient"
    assert local.get("/api/settings").status_code == 403
    assert local.post("/api/settings", json={"provider": "openai"}).status_code == 403
    assert local.post("/api/settings/test").status_code == 403


def test_settings_routes_work_from_loopback(env_file):
    from main import app

    local = TestClient(app, client=("127.0.0.1", 50000))
    r = local.post("/api/settings", json={"provider": "openai", "model": "gpt-5", "api_key": "sk-abcdefghijklmnop"})
    assert r.status_code == 200 and r.json()["provider"] == "openai"
    r = local.get("/api/settings")
    assert r.json()["providers"]["openai"]["key_hint"] == "mnop"


async def test_anthropic_request_shape_is_accepted_by_the_sdk(env_file, monkeypatch):
    """The kwargs sent to the SDK are valid for the installed version. A refused connection
    proves the request left the client; a TypeError would mean a parameter it rejects."""
    import anthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:9")
    base.reset()
    client = anthropic.AsyncAnthropic(api_key="x", base_url="http://127.0.0.1:9", max_retries=0, timeout=2.0)
    base._clients["anthropic"] = client
    with pytest.raises(anthropic.APIConnectionError):
        await base._call_anthropic("claude-opus-5", "hi", "system", 64)
    ok, why = await base._probe_api("anthropic")
    assert ok is False and "could not reach" in why
    base.reset()


def test_openai_compatible_endpoints_get_plain_parameters():
    native = base._chat_kwargs("gpt-5", "p", "s", 100, native=True)
    assert native["max_completion_tokens"] == 100 + base._REASONING_HEADROOM and "reasoning_effort" in native
    compat = base._chat_kwargs("llama3", "p", "s", 100, native=False)
    assert compat == {"model": "llama3", "max_tokens": 100,
                      "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "p"}]}


def test_the_chinese_providers_are_rows_with_key_model_and_address(monkeypatch):
    from agents import base

    for name in ("deepseek", "kimi", "qwen", "glm"):
        assert name in base.PROVIDERS
        spec = base.COMPATIBLE[name]
        monkeypatch.setenv(spec["key_env"], "k")
        monkeypatch.delenv(spec["model_env"], raising=False)
        assert base.resolve_model(name, "claude-opus-5") == spec["default_model"]
        assert base.resolve_model(name, "custom-model") == "custom-model"
    assert base.output_cap("deepseek", 16000) == 8192
    assert base.output_cap("kimi", 16000) == 16000
    assert base.output_cap("anthropic", 16000) == 16000
    view = settings.current()
    assert view["providers"]["qwen"]["default_base_url"].startswith("https://dashscope")
    assert "contact_email" not in view
