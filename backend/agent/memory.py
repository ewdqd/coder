"""记忆层 — 跨会话记忆提取、持久化、继承。

每轮对话后异步提取四类记忆:
1. 用户偏好 (preferences)   - 如"用户喜欢用 pandas 处理数据"
2. 纠正反馈 (corrections)    - 如"上次说的那个 bug 是因为 xxx"
3. 项目知识 (project_knowledge) - 如"这个项目用 FastAPI + SQLAlchemy"
4. 参考信息 (references)     - 如"相关文档: https://xxx"

五层架构: 交互层 → 引擎层 → 工具层 → 记忆层 (本模块) → 安全层
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---- 记忆条目 ----
@dataclass
class MemoryEntry:
    """单条记忆。"""
    id: str                          # 内容哈希作为唯一 ID
    category: str                    # preference | correction | project | reference
    content: str                     # 记忆正文
    source_session: str = ""         # 产生该记忆的会话 ID
    importance: float = 0.5          # 0-1 重要性评分
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    superseded_by: str | None = None  # 被更新的记忆 ID


# ---- 记忆提取器 ----
class MemoryExtractor:
    """从对话中提取结构化记忆。

    使用启发式规则 + 关键词匹配进行提取。
    生产环境可替换为 LLM 驱动的提取器。
    """

    CATEGORY_PATTERNS = {
        "preference": [
            r"(?:我(?:喜欢|习惯|偏好|常用|倾向))(.+?)(?:[。.!！\n]|$)",
            r"(?:用|使用|习惯用)(.+?)(?:比较|更|最)(?:好|方便|快)",
            r"prefer\s+(.+?)(?:[.!]|$)",
        ],
        "correction": [
            r"(?:不对|错了|不是|纠正|更正)(?:\s*[:：])?(.+?)(?:[。.!！\n]|$)",
            r"(?:应该是|正确的是|实际上)(.+?)(?:[。.!！\n]|$)",
            r"(?:你(?:弄错|搞错|记错)了)(.+?)(?:[。.!！\n]|$)",
        ],
        "project_knowledge": [
            r"(?:项目|代码|仓库)(?:里|中|使用|采用|基于)(.+?)(?:[。.!！\n]|$)",
            r"(?:技术栈|架构|框架)(?:\s*[:：])?(.+?)(?:[。.!！\n]|$)",
            r"(?:依赖|需要|用到)(.+?)(?:库|包|框架|SDK)",
        ],
        "reference": [
            r"(?:https?://[^\s\n]+)",
            r"(?:参考|参见|文档|链接)(?:\s*[:：])?(.+?)(?:[。.!！\n]|$)",
            r"(?:文件|目录|路径)(?:\s*[:：])?([^\s\n]+?\.[a-zA-Z]{1,6})",
        ],
    }

    def extract(self, user_msg: str, assistant_msg: str) -> list[MemoryEntry]:
        """从一轮对话中提取记忆。"""
        entries: list[MemoryEntry] = []
        combined = f"{user_msg}\n{assistant_msg}"

        for category, patterns in self.CATEGORY_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, combined, re.IGNORECASE):
                    content = match.group(1).strip()
                    if len(content) >= 5 and len(content) <= 500:
                        entry_id = self._hash(content)
                        entries.append(MemoryEntry(
                            id=entry_id,
                            category=category,
                            content=content,
                            importance=0.6 if category in ("correction", "preference") else 0.4,
                        ))

        return entries

    @staticmethod
    def _hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# ---- 记忆存储 ----
class MemoryStore:
    """持久化记忆存储，支持语义去重和冲突解决。"""

    MAX_MEMORIES = 200
    MAX_PER_CATEGORY = 50

    def __init__(self, store_dir: str | Path):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "memories.json"
        self._memories: dict[str, MemoryEntry] = {}
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                self._memories = {
                    k: MemoryEntry(**v) for k, v in data.items()
                }
            except (json.JSONDecodeError, TypeError):
                self._memories = {}

    def _save(self):
        # 限制总数
        if len(self._memories) > self.MAX_MEMORIES:
            sorted_items = sorted(
                self._memories.values(),
                key=lambda m: (m.importance, m.access_count, m.created_at),
                reverse=True,
            )
            self._memories = {m.id: m for m in sorted_items[:self.MAX_MEMORIES]}

        data = {
            k: {
                "id": v.id, "category": v.category, "content": v.content,
                "source_session": v.source_session, "importance": v.importance,
                "created_at": v.created_at, "access_count": v.access_count,
                "superseded_by": v.superseded_by,
            }
            for k, v in self._memories.items()
        }
        self._file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, entry: MemoryEntry) -> bool:
        """添加记忆，自动去重。返回 True 表示新增。"""
        if entry.id in self._memories:
            existing = self._memories[entry.id]
            existing.access_count += 1
            return False

        # 同类别数量限制
        cat_count = sum(1 for m in self._memories.values() if m.category == entry.category)
        if cat_count >= self.MAX_PER_CATEGORY:
            # 替换最不重要的
            least = min(
                (m for m in self._memories.values() if m.category == entry.category),
                key=lambda m: (m.importance, m.access_count),
            )
            del self._memories[least.id]

        self._memories[entry.id] = entry
        self._save()
        return True

    def supersede(self, old_id: str, new_entry: MemoryEntry) -> None:
        """用新记忆取代旧记忆。"""
        if old_id in self._memories:
            self._memories[old_id].superseded_by = new_entry.id
        self._memories[new_entry.id] = new_entry
        self._save()

    def query(self, category: str | None = None, limit: int = 20) -> list[MemoryEntry]:
        """查询记忆，按重要性+访问次数排序。"""
        memories = list(self._memories.values())
        memories = [m for m in memories if m.superseded_by is None]
        if category:
            memories = [m for m in memories if m.category == category]
        return sorted(
            memories, key=lambda m: (m.importance, m.access_count), reverse=True
        )[:limit]

    def get_context_prompt(self, max_tokens: int = 500) -> str:
        """生成注入新会话的上下文提示。"""
        top = self.query(limit=20)
        if not top:
            return ""

        by_cat: dict[str, list[str]] = {}
        for m in top:
            by_cat.setdefault(m.category, []).append(f"- {m.content}")

        parts = []
        cat_labels = {
            "preference": "## 用户偏好", "correction": "## 历史纠正",
            "project_knowledge": "## 项目知识", "reference": "## 参考资料",
        }
        for cat, label in cat_labels.items():
            if cat in by_cat:
                items = by_cat[cat]
                total = sum(len(i) for i in items)
                if total > max_tokens:
                    items = items[: max(1, max_tokens // max(len(i) for i in items))]
                parts.append(f"{label}\n" + "\n".join(items))

        return "\n\n".join(parts)


# ---- 异步记忆管理器 ----
class MemoryManager:
    """异步记忆管理器 — 每轮对话后自动提取+持久化。"""

    def __init__(self, store_dir: str | Path = ".pet_memory"):
        self.store = MemoryStore(store_dir)
        self.extractor = MemoryExtractor()
        self._lock = threading.Lock()
        self._pending: list[tuple[str, str, str]] = []  # (session_id, user_msg, assistant)

    def record_turn(self, session_id: str, user_msg: str, assistant: str):
        """记录一轮对话，异步提取记忆。"""
        with self._lock:
            self._pending.append((session_id, user_msg, assistant))

        # 同步提取（可在子线程中运行）
        self._extract_and_save(session_id, user_msg, assistant)

    def _extract_and_save(self, session_id: str, user_msg: str, assistant: str):
        """提取记忆并持久化。"""
        entries = self.extractor.extract(user_msg, assistant)
        for entry in entries:
            entry.source_session = session_id

        # 避免快速重复
        for entry in entries:
            self.store.add(entry)

    def get_inheritance_prompt(self) -> str:
        """获取跨会话继承的上下文提示。"""
        return self.store.get_context_prompt()

    def get_memories(self, category: str | None = None) -> list[MemoryEntry]:
        return self.store.query(category)
