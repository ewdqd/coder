"""Agent 主循环 — 从 Coder 的 ReAct loop 精简而来。

去掉了: Worktree, Teams, MCP, Hooks, Permissions (6层), Plan mode
保留了: 流式 LLM 调用, 工具执行, 上下文管理, 对话历史
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

from pydantic import ValidationError

from .client import LLMClient, StreamEvent, TextDelta, ToolCallComplete, StreamEnd
from .conversation import (
    ConversationManager,
    Message,
    ToolResultBlock,
    ToolUseBlock,
)
from .tools import ToolRegistry, ToolResult, MAX_OUTPUT_CHARS

log = logging.getLogger(__name__)

MAX_ITERATIONS = 50

# ============================================================================
# Agent 事件 (通过 WebSocket 发送给前端)
# ============================================================================


@dataclass
class AgentStreamText:
    text: str


@dataclass
class AgentThinkingText:
    text: str


@dataclass
class AgentToolUse:
    tool_name: str
    tool_id: str
    arguments: dict[str, Any]


@dataclass
class AgentToolResult:
    tool_id: str
    tool_name: str
    output: str
    is_error: bool
    elapsed: float


@dataclass
class AgentTurnComplete:
    turn: int


@dataclass
class AgentLoopComplete:
    total_turns: int


@dataclass
class AgentError:
    message: str


@dataclass
class AgentUsage:
    input_tokens: int
    output_tokens: int


AgentEvent = (
    AgentStreamText | AgentThinkingText | AgentToolUse
    | AgentToolResult | AgentTurnComplete | AgentLoopComplete
    | AgentError | AgentUsage
)


# ============================================================================
# LLM 响应收集器
# ============================================================================

@dataclass
class ThinkingBlock:
    thinking: str
    signature: str


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCallComplete] = field(default_factory=list)
    thinking_blocks: list[ThinkingBlock] = field(default_factory=list)
    stop_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_creation: int = 0


class StreamCollector:
    def __init__(self) -> None:
        self.response = LLMResponse()

    async def consume(
        self, stream: AsyncIterator[StreamEvent]
    ) -> AsyncIterator[AgentEvent]:
        async for event in stream:
            if isinstance(event, TextDelta):
                self.response.text += event.text
                yield AgentStreamText(text=event.text)
            elif isinstance(event, ToolCallComplete):
                self.response.tool_calls.append(event)
                yield AgentToolUse(
                    tool_name=event.tool_name,
                    tool_id=event.tool_id,
                    arguments=event.arguments,
                )
            elif isinstance(event, StreamEnd):
                self.response.stop_reason = event.stop_reason
                self.response.input_tokens = event.input_tokens
                self.response.output_tokens = event.output_tokens
                self.response.cache_read = event.cache_read
                self.response.cache_creation = event.cache_creation


# ============================================================================
# Agent
# ============================================================================

class Agent:
    """精简版 Agent 引擎。

    去掉了 Coder 中与桌面宠物场景无关的功能:
    - Worktree 隔离
    - Agent Teams 协作
    - MCP 协议
    - Hooks 事件系统
    - 6 层权限检查
    - Plan Mode
    - 云端部署/Gitee
    """

    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry,
        work_dir: str = ".",
        max_iterations: int = MAX_ITERATIONS,
        system_prompt_fn: Callable[[], str] | None = None,
    ) -> None:
        self.client = client
        self.registry = registry
        self.work_dir = work_dir
        self.max_iterations = max_iterations
        self._system_prompt_fn = system_prompt_fn
        self.agent_id: str = uuid.uuid4().hex[:12]
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def _build_system_prompt(self) -> str:
        if self._system_prompt_fn:
            return self._system_prompt_fn()
        return "You are CodePet, a helpful programmer's desktop companion."

    async def run(
        self, conversation: ConversationManager
    ) -> AsyncIterator[AgentEvent]:
        """流式执行 Agent 对话循环。

        遍历每一轮: LLM 流式调用 -> 工具执行 -> 结果注入 -> 下一轮。
        直到 LLM 不再返回 tool_calls 或达到最大轮次。
        """
        tools = self.registry.get_all_schemas()
        system = self._build_system_prompt()

        for iteration in range(1, self.max_iterations + 1):
            # 流式调用 LLM
            collector = StreamCollector()
            llm_stream = self.client.stream(conversation, system=system, tools=tools)
            async for event in collector.consume(llm_stream):
                yield event

            response = collector.response

            # Token 统计
            self.total_input_tokens += response.input_tokens
            self.total_output_tokens += response.output_tokens
            yield AgentUsage(
                input_tokens=self.total_input_tokens,
                output_tokens=self.total_output_tokens,
            )

            # 构建 assistant 消息的 thinking blocks
            conv_thinking = [
                ThinkingBlock(thinking=tb.thinking, signature=tb.signature)
                for tb in response.thinking_blocks
            ]

            # 没有 tool_calls -> 对话结束
            if not response.tool_calls:
                conversation.add_assistant_message(
                    response.text,
                    thinking_blocks=[  # type: ignore
                        type(conv_thinking[0])(  # type: ignore
                            thinking=tb.thinking, signature=tb.signature
                        ) for tb in conv_thinking
                    ] if conv_thinking else [],
                )
                yield AgentLoopComplete(total_turns=iteration)
                return

            # 有 tool_calls -> 添加到历史
            tool_uses = [
                ToolUseBlock(
                    tool_use_id=tc.tool_id,
                    tool_name=tc.tool_name,
                    arguments=tc.arguments,
                )
                for tc in response.tool_calls
            ]
            conversation.add_assistant_message(
                response.text, tool_uses
            )
            conversation.record_usage_anchor(
                response.input_tokens,
                response.output_tokens,
                response.cache_read,
                response.cache_creation,
            )

            # 执行工具并收集结果
            tool_results: list[ToolResultBlock] = []
            for tc in response.tool_calls:
                start = time.monotonic()
                result = await self._execute_tool(tc)
                elapsed = time.monotonic() - start

                content = self._truncate(tc.tool_id, result.output)
                tool_results.append(
                    ToolResultBlock(
                        tool_use_id=tc.tool_id,
                        content=content,
                        is_error=result.is_error,
                    )
                )
                yield AgentToolResult(
                    tool_id=tc.tool_id,
                    tool_name=tc.tool_name,
                    output=result.output,
                    is_error=result.is_error,
                    elapsed=elapsed,
                )

            conversation.add_tool_results_message(tool_results)
            yield AgentTurnComplete(turn=iteration)

        yield AgentError(message=f"Reached maximum iterations ({self.max_iterations})")

    async def _execute_tool(self, tc: ToolCallComplete) -> ToolResult:
        tool = self.registry.get(tc.tool_name)

        if tool is None:
            return ToolResult(
                output=f"Error: unknown tool '{tc.tool_name}'", is_error=True
            )

        if not self.registry.is_enabled(tc.tool_name):
            return ToolResult(
                output=f"Error: tool '{tc.tool_name}' is disabled", is_error=True
            )

        try:
            params = tool.params_model.model_validate(tc.arguments)
            result = await tool.execute(params)
        except ValidationError as e:
            result = ToolResult(
                output=f"Parameter validation error: {e}", is_error=True
            )
        except Exception as e:
            result = ToolResult(
                output=f"Tool execution error: {e}", is_error=True
            )

        return result

    def _truncate(self, tool_use_id: str, text: str) -> str:
        if len(text) > MAX_OUTPUT_CHARS:
            return text[:MAX_OUTPUT_CHARS] + "\n… (output truncated)"
        return text
