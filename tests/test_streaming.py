from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from genesis_core.adapters import ChatAdapter, ModelConfig
from genesis_core.agent import AgentRuntime, build_default_tool_executor
from genesis_core.state import StateStore


class FakeStreamResponse:
    def __init__(self, lines: list[str]):
        self.lines = [line.encode("utf-8") for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self.lines)


def test_ollama_adapter_yields_incremental_content():
    adapter = ChatAdapter(ModelConfig("ollama", "http://127.0.0.1:11434", "tiny"))
    response = FakeStreamResponse([
        json.dumps({"message": {"content": "Hello "}, "done": False}),
        json.dumps({"message": {"content": "GENESIS"}, "done": False}),
        json.dumps({"done": True}),
    ])
    with patch("genesis_core.adapters.urlopen", return_value=response):
        assert list(adapter.stream([{"role": "user", "content": "Hi"}])) == ["Hello ", "GENESIS"]


def test_openai_compatible_adapter_parses_sse_deltas():
    adapter = ChatAdapter(ModelConfig("llama_cpp", "http://127.0.0.1:8080", "tiny"))
    response = FakeStreamResponse([
        'data: {"choices":[{"delta":{"content":"A"}}]}',
        'data: {"choices":[{"delta":{"content":" streamed"}}]}',
        "data: [DONE]",
    ])
    with patch("genesis_core.adapters.urlopen", return_value=response):
        assert list(adapter.stream([{"role": "user", "content": "Hi"}])) == ["A", " streamed"]


class FakeStreamingAdapter:
    config = SimpleNamespace(provider="fake-local", model="stream-test")

    def stream(self, messages):
        yield '{"action":"final","message":"Hello '
        yield 'from GENESIS"}'

    def chat(self, messages):
        raise AssertionError("stream() should be used when a token callback is supplied")


def test_agent_streams_decoded_final_message_and_persists_reply(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    session = state.create_session()
    executor, _ = build_default_tool_executor(state)
    received = []
    runtime = AgentRuntime(store=state, adapter=FakeStreamingAdapter(), tool_executor=executor)

    reply = runtime.chat(session["id"], "Say hello", on_token=received.append)

    assert "".join(received) == "Hello from GENESIS"
    assert reply.assistant_message["content"] == "Hello from GENESIS"
    assert [message["role"] for message in state.list_messages(session["id"])] == [
        "user", "assistant"
    ]


def test_studio_stream_endpoint_sends_sse_delta_and_final_message(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from genesis_core import web

    state = StateStore(tmp_path / "studio-stream.db")
    session = state.create_session()
    monkeypatch.setattr(web, "store", state)

    class FakeAgent:
        def chat(self, session_id, content, on_token=None):
            user = state.add_message(session_id, "user", content)
            if on_token:
                on_token("Hello ")
                on_token("there")
            assistant = state.add_message(session_id, "assistant", "Hello there")
            return SimpleNamespace(
                user_message=user, assistant_message=assistant,
                provider="fake-local", model="sse-test", activity=[],
            )

    monkeypatch.setattr(web, "agent", FakeAgent())
    response = web.stream_message(session["id"], web.MessageInput(content="Hi"))
    import asyncio

    async def collect_frames():
        return [frame async for frame in response.body_iterator]

    body = "".join(asyncio.run(collect_frames()))

    assert response.media_type == "text/event-stream"
    assert '"type": "delta"' in body
    assert "Hello there" in body
    assert '"type": "done"' in body
