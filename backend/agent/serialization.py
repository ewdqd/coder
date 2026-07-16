"""消息序列化 — 从 MewCode 核心模块导入，消除重复代码。"""

from core.serialization import (        # noqa: F401
    build_anthropic_messages,
    build_chat_completion_messages,
    build_openai_input,
)
