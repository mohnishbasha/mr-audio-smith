import sys
import types
from pathlib import Path

import httpx
import pytest
import respx

from audio_smith.config import Settings, load_settings
from audio_smith.errors import LLMError, UsageError
from audio_smith.llm import base, get_provider, parse_provider, provider_label
from audio_smith.llm.anthropic import AnthropicProvider
from audio_smith.llm.checks import llm_check
from audio_smith.llm.fake import FakeProvider, prompt_key
from audio_smith.llm.ollama import OllamaProvider
from audio_smith.llm.openai_compat import OpenAICompatProvider

HOST = "http://ollama.test:11434"
BASE = "http://oai.test/v1"
KW = {"temperature": 0.0, "seed": 7, "max_tokens": 50}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base.time, "sleep", lambda _s: None)


def _ollama(model: str = "qwen3:14b") -> OllamaProvider:
    return OllamaProvider(model, HOST)


@respx.mock
def test_llm_ollama_chat_request_shape() -> None:
    route = respx.post(f"{HOST}/api/chat").respond(json={"message": {"content": "<think>hmm</think>Hello"}})
    out = _ollama().complete("sys", "usr", **KW)  # type: ignore[arg-type]
    assert out == "Hello"
    import json

    body = json.loads(route.calls[0].request.content)
    assert body["model"] == "qwen3:14b"
    assert body["stream"] is False
    assert body["think"] is False
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["options"] == {"temperature": 0.0, "seed": 7, "num_predict": 50}


@respx.mock
def test_llm_seed_and_temperature_zero_passed_where_supported() -> None:
    import json

    r1 = respx.post(f"{HOST}/api/chat").respond(json={"message": {"content": "x"}})
    OllamaProvider("llama3", HOST).complete("s", "u", temperature=0.0, seed=None, max_tokens=5)
    body = json.loads(r1.calls[0].request.content)
    assert "think" not in body
    assert "seed" not in body["options"]
    assert body["options"]["temperature"] == 0.0
    r2 = respx.post(f"{BASE}/chat/completions").respond(json={"choices": [{"message": {"content": "y"}}]})
    OpenAICompatProvider(BASE, "m").complete("s", "u", temperature=0.0, seed=3, max_tokens=5)
    oai = json.loads(r2.calls[0].request.content)
    assert oai["seed"] == 3
    assert oai["temperature"] == 0.0


@respx.mock
def test_llm_ollama_retries_5xx_then_succeeds() -> None:
    route = respx.post(f"{HOST}/api/chat").mock(
        side_effect=[
            httpx.Response(503),
            httpx.ConnectError("boom"),
            httpx.Response(200, json={"message": {"content": "ok"}}),
        ]
    )
    assert _ollama().complete("s", "u", **KW) == "ok"  # type: ignore[arg-type]
    assert route.call_count == 3


@respx.mock
def test_llm_retries_exhausted_raises() -> None:
    respx.post(f"{HOST}/api/chat").respond(500)
    with pytest.raises(LLMError) as ei:
        _ollama().complete("s", "u", **KW)  # type: ignore[arg-type]
    assert ei.value.exit_code == 5
    assert ei.value.stage == "script"


@respx.mock
def test_llm_bad_replies_raise() -> None:
    p = _ollama()
    respx.post(f"{HOST}/api/chat").respond(400, text="bad")
    with pytest.raises(LLMError, match="HTTP 400"):
        p.complete("s", "u", **KW)  # type: ignore[arg-type]
    respx.post(f"{HOST}/api/chat").respond(200, text="not json")
    with pytest.raises(LLMError, match="JSON"):
        p.complete("s", "u", **KW)  # type: ignore[arg-type]
    respx.post(f"{HOST}/api/chat").respond(200, json={"nope": 1})
    with pytest.raises(LLMError, match="content"):
        p.complete("s", "u", **KW)  # type: ignore[arg-type]
    respx.post(f"{HOST}/api/chat").respond(200, json=[1])
    with pytest.raises(LLMError, match="JSON"):
        p.complete("s", "u", **KW)  # type: ignore[arg-type]


@respx.mock
def test_llm_ollama_preflight_ok_and_model_missing() -> None:
    respx.get(f"{HOST}/api/tags").respond(json={"models": [{"name": "qwen3:14b"}]})
    assert _ollama().preflight() == []
    issues = _ollama("other:1b").preflight()
    assert issues[0].code == "ollama.model_missing"
    assert issues[0].hint == "Run `ollama pull other:1b`."


@respx.mock
def test_llm_ollama_unreachable_preflight_hint() -> None:
    respx.get(f"{HOST}/api/tags").mock(side_effect=httpx.ConnectError("down"))
    issues = _ollama().preflight()
    assert issues[0].severity == "error"
    assert issues[0].code == "ollama.unreachable"
    assert "ollama serve" in (issues[0].hint or "")


@respx.mock
def test_llm_ollama_tags_malformed_means_model_missing() -> None:
    respx.get(f"{HOST}/api/tags").respond(json={"models": "x"})
    assert _ollama().preflight()[0].code == "ollama.model_missing"


@respx.mock
def test_llm_openai_compat_base_url_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    route = respx.post(f"{BASE}/chat/completions").respond(json={"choices": [{"message": {"content": "hi"}}]})
    assert OpenAICompatProvider(BASE + "/", "m").complete("s", "u", **KW) == "hi"  # type: ignore[arg-type]
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-test"


@respx.mock
def test_llm_openai_compat_no_key_no_header_and_bad_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    route = respx.post(f"{BASE}/chat/completions").respond(json={"choices": []})
    with pytest.raises(LLMError):
        OpenAICompatProvider(BASE, "m").complete("s", "u", **KW)  # type: ignore[arg-type]
    assert "authorization" not in route.calls[0].request.headers


@respx.mock
def test_llm_openai_compat_preflight_cloud_and_unreachable() -> None:
    respx.get(f"{BASE}/models").respond(json={"data": []})
    codes = [i.code for i in OpenAICompatProvider(BASE, "m").preflight()]
    assert codes == ["llm.cloud_active"]
    respx.get("http://127.0.0.1:9/v1/models").mock(side_effect=httpx.ConnectError("x"))
    issues = OpenAICompatProvider("http://127.0.0.1:9/v1", "m").preflight()
    assert [i.code for i in issues] == ["openai_compat.unreachable"]


def _stub_anthropic(monkeypatch: pytest.MonkeyPatch, captured: dict[str, object]) -> None:
    class Client:
        def __init__(self, api_key: str) -> None:
            captured["api_key"] = api_key
            self.messages = self

        def create(self, **kwargs: object) -> object:
            captured.update(kwargs)
            block = types.SimpleNamespace(type="text", text="<think>x</think>Claude says hi")
            return types.SimpleNamespace(content=[block])

    mod = types.ModuleType("anthropic")
    mod.Anthropic = Client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", mod)


def test_llm_anthropic_provider_passes_model_and_system(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _stub_anthropic(monkeypatch, captured)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    out = AnthropicProvider("claude-x").complete("SYS", "USR", **KW)  # type: ignore[arg-type]
    assert out == "Claude says hi"
    assert captured["model"] == "claude-x"
    assert captured["system"] == "SYS"
    assert captured["max_tokens"] == 50
    assert captured["temperature"] == 0.0
    assert "seed" not in captured
    assert captured["messages"] == [{"role": "user", "content": "USR"}]


def test_llm_anthropic_preflight_states(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _stub_anthropic(monkeypatch, captured)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert [i.code for i in AnthropicProvider("m").preflight()] == ["llm.cloud_active"]
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    codes = [i.code for i in AnthropicProvider("m").preflight()]
    assert codes == ["llm.cloud_active", "anthropic.key_missing"]
    with pytest.raises(LLMError, match="not set"):
        AnthropicProvider("m").complete("s", "u", **KW)  # type: ignore[arg-type]


def test_llm_anthropic_missing_sdk_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "anthropic", None)
    issues = AnthropicProvider("m").preflight()
    assert issues[0].code == "anthropic.sdk_missing"
    assert issues[0].hint == 'uv tool install "mr-audio-smith[cloud]"'
    with pytest.raises(LLMError, match="not installed"):
        AnthropicProvider("m").complete("s", "u", **KW)  # type: ignore[arg-type]
    mod = types.ModuleType("anthropic")

    class Boom:
        def __init__(self, api_key: str) -> None:
            raise RuntimeError("secret detail")

    mod.Anthropic = Boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    with pytest.raises(LLMError, match="RuntimeError") as ei:
        AnthropicProvider("m").complete("s", "u", **KW)  # type: ignore[arg-type]
    assert "secret detail" not in str(ei.value)


def test_llm_fake_provider_replays_by_prompt_hash(tmp_path: Path) -> None:
    (tmp_path / f"{prompt_key('s', 'u')}.txt").write_text("recorded", encoding="utf-8")
    p = FakeProvider(tmp_path)
    assert p.complete("s", "u", **KW) == "recorded"  # type: ignore[arg-type]
    assert p.calls == [("s", "u")]
    assert p.preflight() == []
    assert len(prompt_key("s", "u")) == 16


def test_llm_fake_provider_unknown_hash_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(LLMError) as ei:
        FakeProvider(tmp_path).complete("s", "u", **KW)  # type: ignore[arg-type]
    assert prompt_key("s", "u") in ei.value.message
    assert "make record-llm" in (ei.value.hint or "")
    assert str(tmp_path) in (ei.value.hint or "")


def test_llm_fake_provider_queue_mode() -> None:
    p = FakeProvider(responses=["a", "b"])
    assert [p.complete("s", "u", **KW) for _ in range(2)] == ["a", "b"]  # type: ignore[arg-type]
    with pytest.raises(LLMError, match="empty"):
        p.complete("s", "u", **KW)  # type: ignore[arg-type]


def test_llm_provider_string_parsing_all_three_formats() -> None:
    o = parse_provider("ollama:qwen3:14b")
    assert (o.kind, o.model) == ("ollama", "qwen3:14b")
    a = parse_provider("anthropic:claude-sonnet-5-5")
    assert (a.kind, a.model) == ("anthropic", "claude-sonnet-5-5")
    c = parse_provider("openai_compat:http://127.0.0.1:8001/v1#qwen3-14b")
    assert (c.kind, c.base_url, c.model) == ("openai_compat", "http://127.0.0.1:8001/v1", "qwen3-14b")
    assert parse_provider("fake").kind == "fake"
    assert parse_provider("fake:some/dir").model == "some/dir"


@pytest.mark.parametrize("bad", ["gpt:4", "ollama:", "openai_compat:http://x/v1", "openai_compat:#m", ""])
def test_llm_parse_provider_rejects_invalid(bad: str) -> None:
    with pytest.raises(UsageError):
        parse_provider(bad)


def test_llm_unknown_provider_lists_known_kinds() -> None:
    with pytest.raises(UsageError, match="ollama, anthropic, openai_compat, fake"):
        parse_provider("bogus:x")


def test_llm_provider_label_drops_base_url() -> None:
    assert provider_label("openai_compat:https://user:pw@h/v1#m") == "openai_compat/m"
    assert provider_label("ollama:qwen3:14b") == "ollama/qwen3:14b"
    assert provider_label("fake") == "fake"


def test_llm_get_provider_factory(tmp_path: Path) -> None:
    s = Settings()
    assert isinstance(get_provider("ollama:m", s), OllamaProvider)
    assert isinstance(get_provider("anthropic:m", s), AnthropicProvider)
    assert isinstance(get_provider(f"openai_compat:{BASE}#m", s), OpenAICompatProvider)
    fake = get_provider(f"fake:{tmp_path}", s)
    assert isinstance(fake, FakeProvider)
    assert fake.fixture_dir == tmp_path
    assert isinstance(get_provider("fake", s), FakeProvider)


def test_llm_strip_think_and_locality() -> None:
    assert base.strip_think("<think>a\nb</think>\n\nText") == "Text"
    assert base.is_local_host("http://192.168.1.5/v1")
    assert not base.is_local_host("https://api.openai.com/v1")


def test_llm_check_states(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = llm_check(load_settings({"llm": "fake"}) if False else Settings(llm="fake"))
    assert ok.ok
    bad = llm_check(Settings(llm="nope:x"))
    assert not bad.ok
    with respx.mock:
        respx.get(f"{HOST}/api/tags").mock(side_effect=httpx.ConnectError("x"))
        down = llm_check(Settings(llm="ollama:m", ollama_host=HOST))
    assert not down.ok
    assert down.hint
    mod = types.ModuleType("anthropic")
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    warn = llm_check(Settings(llm="anthropic:m"))
    assert warn.ok
    assert "cloud provider active" in warn.detail
