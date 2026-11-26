"""First useful GENESIS agent loop: receive, remember, infer, respond."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from genesis_core.adapters import ChatAdapter, ModelError, create_chat_adapter
from genesis_core.state import StateStore

SYSTEM_PROMPT = """You are GENESIS, a general-purpose local-first AI agent.
You are not limited to programming. Help with research, learning, analysis,
planning, writing and technical work. Be clear about uncertainty and never
claim to have used a tool or changed a file unless that action actually happened.
You currently have no tool execution in this runtime: do not pretend otherwise.
Respect the user's instructions and keep answers practical.
"""


@dataclass
class AgentReply:
    session_id: str
    user_message: dict[str, Any]
    assistant_message: dict[str, Any]
    provider: str
    model: str


class AgentRuntime:
    """Coordinates shared conversation state and a selected chat adapter."""

    def __init__(
        self,
        store: StateStore | None = None,
        adapter: ChatAdapter | None = None,
        history_limit: int = 24,
    ) -> None:
        self.store = store or StateStore()
        self.adapter = adapter
        self.history_limit = max(2, history_limit)

    def _adapter(self) -> ChatAdapter:
        if self.adapter is None:
            self.adapter = create_chat_adapter()
        return self.adapter

    def chat(self, session_id: str, content: str) -> AgentReply:
        if not self.store.get_session(session_id):
            raise KeyError(session_id)
        if not content.strip():
            raise ValueError("Message content cannot be empty")

        adapter = self._adapter()
        user_message = self.store.add_message(session_id, "user", content)
        history = self.store.list_messages(session_id)[-self.history_limit:]
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(
            {"role": item["role"], "content": item["content"]}
            for item in history
            if item["role"] in {"user", "assistant"}
        )
        answer = adapter.chat(messages)
        assistant_message = self.store.add_message(session_id, "assistant", answer)
        return AgentReply(
            session_id=session_id,
            user_message=user_message,
            assistant_message=assistant_message,
            provider=adapter.config.provider,
            model=adapter.config.model,
        )


__all__ = ["AgentReply", "AgentRuntime", "ModelError"]
