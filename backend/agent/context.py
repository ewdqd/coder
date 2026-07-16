"""上下文压缩 — 两层渐进式压缩，支持数小时连续会话不丢失上下文。

L1 (轻量压缩): 合并连续同角色消息，截断超长工具输出
L2 (深度压缩): LLM 驱动摘要，将历史压缩为结构化摘要
L3 (归档): 将极旧的对话归档为长期记忆

五层架构: 交互层 → 引擎层 (本模块) → 工具层 → 记忆层 → 安全层
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from core.conversation import ConversationManager, Message, estimate_tokens


# ---- 压缩配置 ----
@dataclass
class CompressionConfig:
    """上下文压缩配置。"""
    l1_max_tokens: int = 80000       # 超过此值触发 L1 压缩
    l2_max_tokens: int = 120000      # 超过此值触发 L2 压缩
    l3_max_tokens: int = 200000      # 超过此值触发 L3 归档
    l1_merge_consecutive: bool = True  # L1: 合并连续同角色消息
    l1_truncate_output: int = 2000     # L1: 工具输出截断长度
    l2_summary_target: int = 2000      # L2: 摘要目标 token 数
    l3_archive_limit: float = 0.3      # L3: 归档最旧 30% 的消息


class ContextCompressor:
    """两层渐进式上下文压缩器。"""

    def __init__(self, config: CompressionConfig | None = None):
        self.config = config or CompressionConfig()
        self.compression_count: int = 0

    def maybe_compress(self, conv: ConversationManager) -> str:
        """检查是否需要压缩，返回压缩日志（空字符串表示无需压缩）。"""
        tokens = conv.current_tokens()

        if tokens > self.config.l3_max_tokens:
            return self._compress_l3(conv)
        elif tokens > self.config.l2_max_tokens:
            return self._compress_l2(conv)
        elif tokens > self.config.l1_max_tokens:
            return self._compress_l1(conv)
        return ""

    def _compress_l1(self, conv: ConversationManager) -> str:
        """L1 轻量压缩: 合并连续用户消息 + 截断工具输出。"""
        if not conv.history:
            return ""

        compressed: list[Message] = []
        skipped = 0

        for msg in conv.history:
            # 截断超长工具结果
            if msg.tool_results:
                for tr in msg.tool_results:
                    if len(tr.content) > self.config.l1_truncate_output:
                        tr.content = (
                            tr.content[:self.config.l1_truncate_output]
                            + f"\n... [truncated, original {len(tr.content)} chars]"
                        )

            # 合并连续同角色纯文本消息
            if (
                self.config.l1_merge_consecutive
                and compressed
                and msg.role == compressed[-1].role
                and msg.role in ("user",)
                and not msg.tool_uses
                and not msg.tool_results
                and not compressed[-1].tool_uses
                and not compressed[-1].tool_results
            ):
                compressed[-1].content += "\n" + msg.content
                skipped += 1
            else:
                compressed.append(msg)

        conv.history = compressed
        self.compression_count += 1
        return f"[L1] Merged {skipped} messages, tokens: {conv.current_tokens()}"

    def _compress_l2(self, conv: ConversationManager) -> str:
        """L2 深度压缩: 将前半段历史标记为可摘要。

        实际 LLM 摘要由 engine 层调用 summarize() 完成。
        这里只做标记和准备。
        """
        if len(conv.history) < 4:
            return self._compress_l1(conv)

        # 保留最近 1/3 的消息不动，前面的标记为"待摘要"
        keep_count = max(2, len(conv.history) // 3)
        to_summarize = conv.history[:-keep_count]
        keep = conv.history[-keep_count:]

        summary_prompt = (
            "Summarize the following conversation history, preserving:\n"
            "1. Key decisions made\n"
            "2. Important code patterns or bugs found\n"
            "3. User preferences expressed\n"
            "4. Unfinished tasks\n\n"
        )
        for msg in to_summarize:
            role = msg.role
            content = msg.content[:500]
            if msg.tool_uses:
                content += f" [used tools: {', '.join(tu.tool_name for tu in msg.tool_uses)}]"
            if msg.tool_results:
                content += f" [tool results: {len(msg.tool_results)} items]"
            summary_prompt += f"[{role}] {content}\n"

        # 占位: 实际摘要需要 LLM 调用，这里标记
        conv.history = keep
        conv.history.insert(0, Message(
            role="user",
            content=(
                "<system-reminder>\n"
                "Previous conversation has been compressed. Key context:\n"
                + summary_prompt[:self.config.l2_summary_target]
                + "\n</system-reminder>"
            ),
        ))
        # 重置用量锚点
        conv.baseline_tokens = 0
        conv.anchor_count = 0

        self.compression_count += 1
        new_tokens = conv.current_tokens()
        return f"[L2] Compressed to {len(conv.history)} msgs, ~{new_tokens} tokens"

    def _compress_l3(self, conv: ConversationManager) -> str:
        """L3 归档: 将最旧的对话转为长期记忆存储。"""
        if len(conv.history) < 6:
            return self._compress_l2(conv)

        # 归档最旧 30%
        archive_count = max(1, int(len(conv.history) * self.config.l3_archive_limit))
        archived = conv.history[:archive_count]
        conv.history = conv.history[archive_count:]

        # 提取关键信息作为记忆注入
        key_points = []
        for msg in archived:
            if msg.role == "assistant" and msg.content:
                key_points.append(msg.content[:200])
        memory_note = (
            "<system-reminder>\n"
            "Archived conversation segment. Key exchanges:\n"
            + "\n".join(f"- {p}" for p in key_points[:10])
            + "\n</system-reminder>"
        )
        conv.history.insert(0, Message(role="user", content=memory_note))

        conv.baseline_tokens = 0
        conv.anchor_count = 0

        self.compression_count += 1
        return f"[L3] Archived {archive_count} msgs, tokens: {conv.current_tokens()}"
