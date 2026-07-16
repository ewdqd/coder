"""对话管理器 — 直接从 Coder 核心模块导入，消除重复代码。"""

# 所有核心类型直接从 coder.conversation 导入
from core.conversation import (        # noqa: F401
    ConversationManager,
    Message,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    estimate_tokens,
)
