"""安全层 — 路径沙箱、高危命令黑名单、权限分级。

五层架构: 交互层 → 引擎层 → 工具层 → 记忆层 → 安全层 (本模块)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# ---- 权限模式 ----
class PermissionMode(str, Enum):
    DEFAULT = "default"        # 只读自动放行，写入需确认
    ACCEPT_EDITS = "acceptEdits"  # 编辑自动放行
    PLAN = "plan"              # 只读+计划模式，禁止写入
    BYPASS = "bypass"          # 全部自动放行（仅受信场景）


# ---- 高危命令黑名单 ----
DANGEROUS_COMMANDS: list[str] = [
    r"\brm\s+-rf\b",
    r"\bdd\s+if=",
    r"\bmkfs\.",
    r"\bformat\s",
    r"\bdel\s+/[fF]\b",
    r"\brmdir\s+/[sS]\b",
    r"\bchmod\s+777\b",
    r"\bchown\s+-R\b",
    r">\s*/dev/sd",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bwget\s+.*\|\s*sh\b",
    r"\bcurl\s+.*\|\s*sh\b",
    r"\beval\s",
    r"\bgit\s+push\s+--force\b",
    r"\bdocker\s+rm\s+-f\b",
]


# ---- 路径沙箱 ----
@dataclass
class PathSandbox:
    """路径沙箱 — 限制工具操作在安全目录内。"""
    work_dir: str
    allowed_dirs: list[str] = field(default_factory=list)
    deny_absolute: bool = False

    def __post_init__(self):
        self._work = Path(self.work_dir).resolve()
        self._allowed = [self._work] + [
            Path(d).resolve() for d in self.allowed_dirs
        ]

    def is_allowed(self, target: str | Path) -> bool:
        """检查路径是否在沙箱允许范围内。"""
        try:
            resolved = Path(target).resolve()
        except (OSError, ValueError):
            return False
        return any(
            str(resolved).startswith(str(allowed))
            for allowed in self._allowed
        )

    def validate(self, target: str | Path) -> Path:
        """验证路径，不通过则抛出异常。"""
        if not self.is_allowed(target):
            raise PermissionError(
                f"PathSandbox: '{target}' is outside allowed directories"
            )
        return Path(target).resolve()


# ---- 高危命令检测 ----
class DangerousCommandDetector:
    """高危命令检测器 — 正则匹配拦截危险操作。"""

    def __init__(self, extra_patterns: list[str] | None = None):
        self._patterns = [
            re.compile(p, re.IGNORECASE)
            for p in DANGEROUS_COMMANDS + (extra_patterns or [])
        ]

    def is_dangerous(self, command: str) -> bool:
        return any(p.search(command) for p in self._patterns)

    def check(self, command: str) -> None:
        """检测命令，危险则抛出异常。"""
        for p in self._patterns:
            m = p.search(command)
            if m:
                raise PermissionError(
                    f"DangerousCommand: pattern '{p.pattern}' matched "
                    f"in command: {command[:100]}"
                )


# ---- 权限检查器 ----
@dataclass
class PermissionChecker:
    """统一权限检查 — 组合沙箱+黑名单+权限模式。"""
    sandbox: PathSandbox
    detector: DangerousCommandDetector
    mode: PermissionMode = PermissionMode.DEFAULT

    def check_read(self, path: str | Path) -> Path:
        return self.sandbox.validate(path)

    def check_write(self, path: str | Path) -> Path:
        if self.mode == PermissionMode.PLAN:
            raise PermissionError("Write blocked in plan mode")
        return self.sandbox.validate(path)

    def check_command(self, command: str) -> None:
        self.detector.check(command)

    def check_path_traversal(self, path: str) -> None:
        if ".." in Path(path).parts:
            raise PermissionError("Path traversal detected")
