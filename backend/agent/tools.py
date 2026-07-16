"""工具定义 — 程序员桌面宠物需要的核心工具。

Tool/ToolResult 基类直接从 coder.tools.base 导入；
这里只定义具体的工具实现和轻量级 ToolRegistry。
"""

from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# 基类从 coder 导入，消除重复定义
from core.base import (             # noqa: F401
    MAX_OUTPUT_CHARS,
    SKIP_DIRS,
    Tool,
    ToolCategory,
    ToolResult,
)


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    def __init__(self, work_dir: str = ".") -> None:
        self._tools: dict[str, Tool] = {}
        self._disabled: set[str] = set()
        self.work_dir = work_dir

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def is_enabled(self, name: str) -> bool:
        return name not in self._disabled

    def disable(self, name: str) -> None:
        self._disabled.add(name)

    def enable(self, name: str) -> None:
        self._disabled.discard(name)

    def get_all_schemas(self) -> list[dict[str, Any]]:
        return [t.get_schema() for name, t in self._tools.items() if self.is_enabled(name)]

    def get_tool_names(self) -> list[str]:
        return [name for name in self._tools if self.is_enabled(name)]


# ============================================================================
# 具体工具实现
# ============================================================================

# --- Bash ---

class BashParams(BaseModel):
    command: str = Field(description="The shell command to execute")
    timeout: int = Field(default=120000, description="Timeout in milliseconds (max 600000)")
    description: str = Field(default="", description="Clear, concise description of what this command does")


class BashTool(Tool):
    name = "Bash"
    description = "Execute a shell command and return its output."
    params_model = BashParams
    category = "command"

    def __init__(self, work_dir: str = ".") -> None:
        self.work_dir = work_dir

    async def execute(self, params: BaseModel) -> ToolResult:
        p: BashParams = params  # type: ignore
        try:
            proc = await asyncio.create_subprocess_shell(
                p.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.work_dir,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=p.timeout / 1000.0,
            )
            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n[stderr]\n" + stderr.decode("utf-8", errors="replace")
            if not output.strip():
                output = "(no output)"
            if len(output) > MAX_OUTPUT_CHARS:
                output = output[:MAX_OUTPUT_CHARS] + "\n… (output truncated)"
            return ToolResult(output=output, is_error=proc.returncode != 0)
        except asyncio.TimeoutError:
            return ToolResult(output=f"Command timed out after {p.timeout}ms", is_error=True)
        except Exception as e:
            return ToolResult(output=f"Command error: {e}", is_error=True)


# --- ReadFile ---

class ReadFileParams(BaseModel):
    file_path: str = Field(description="Absolute path to the file to read")
    offset: int = Field(default=0, description="Line number to start reading from")
    limit: int = Field(default=0, description="Number of lines to read (0 = all)")


class ReadFileTool(Tool):
    name = "ReadFile"
    description = "Read the contents of a file from the filesystem."
    params_model = ReadFileParams
    category = "read"

    async def execute(self, params: BaseModel) -> ToolResult:
        p: ReadFileParams = params  # type: ignore
        path = Path(p.file_path)
        if not path.exists():
            return ToolResult(output=f"File not found: {p.file_path}", is_error=True)
        if path.is_dir():
            return ToolResult(output=f"Path is a directory: {p.file_path}", is_error=True)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = text.split("\n")
            if p.offset > 0:
                lines = lines[p.offset:]
            if p.limit > 0:
                lines = lines[:p.limit]
            output = "\n".join(lines)
            if len(output) > MAX_OUTPUT_CHARS:
                output = output[:MAX_OUTPUT_CHARS] + "\n… (output truncated)"
            return ToolResult(output=output)
        except Exception as e:
            return ToolResult(output=f"Read error: {e}", is_error=True)


# --- WriteFile ---

class WriteFileParams(BaseModel):
    file_path: str = Field(description="Absolute path to the file to write")
    content: str = Field(description="The content to write to the file")


class WriteFileTool(Tool):
    name = "WriteFile"
    description = "Write content to a file, overwriting if it exists."
    params_model = WriteFileParams
    category = "write"

    async def execute(self, params: BaseModel) -> ToolResult:
        p: WriteFileParams = params  # type: ignore
        path = Path(p.file_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(p.content, encoding="utf-8")
            return ToolResult(output=f"File written: {p.file_path}")
        except Exception as e:
            return ToolResult(output=f"Write error: {e}", is_error=True)


# --- EditFile ---

class EditFileParams(BaseModel):
    file_path: str = Field(description="Absolute path to the file to edit")
    old_string: str = Field(description="The exact text to replace")
    new_string: str = Field(description="The text to replace it with")
    replace_all: bool = Field(default=False, description="Replace all occurrences")


class EditFileTool(Tool):
    name = "EditFile"
    description = "Perform exact string replacement in an existing file."
    params_model = EditFileParams
    category = "write"

    async def execute(self, params: BaseModel) -> ToolResult:
        p: EditFileParams = params  # type: ignore
        path = Path(p.file_path)
        if not path.exists():
            return ToolResult(output=f"File not found: {p.file_path}", is_error=True)
        try:
            text = path.read_text(encoding="utf-8")
            if p.old_string not in text:
                return ToolResult(
                    output=f"Edit failed: old_string not found in {p.file_path}. "
                           f"The file may have changed since it was last read.",
                    is_error=True,
                )
            if p.replace_all:
                new_text = text.replace(p.old_string, p.new_string)
            else:
                new_text = text.replace(p.old_string, p.new_string, 1)
            path.write_text(new_text, encoding="utf-8")
            return ToolResult(output=f"File edited: {p.file_path}")
        except Exception as e:
            return ToolResult(output=f"Edit error: {e}", is_error=True)


# --- Glob ---

class GlobParams(BaseModel):
    pattern: str = Field(description="Glob pattern, e.g. '**/*.py' or 'src/**/*.ts'")


class GlobTool(Tool):
    name = "Glob"
    description = "Find files matching a glob pattern."
    params_model = GlobParams
    category = "read"
    is_concurrency_safe = True

    def __init__(self, work_dir: str = ".") -> None:
        self.work_dir = work_dir

    async def execute(self, params: BaseModel) -> ToolResult:
        p: GlobParams = params  # type: ignore
        try:
            base = Path(self.work_dir)
            matches = sorted(base.glob(p.pattern))
            # 过滤掉常见的跳过目录
            filtered = [m for m in matches if not any(s in m.parts for s in SKIP_DIRS)]
            if not filtered:
                return ToolResult(output=f"No files matched pattern: {p.pattern}")
            # 转为相对路径
            lines = [str(m.relative_to(base)) for m in filtered]
            output = "\n".join(lines[:200])
            if len(lines) > 200:
                output += f"\n… ({len(lines) - 200} more files)"
            return ToolResult(output=output)
        except Exception as e:
            return ToolResult(output=f"Glob error: {e}", is_error=True)


# --- Grep ---

class GrepParams(BaseModel):
    pattern: str = Field(description="Regular expression pattern to search for")
    path: str = Field(default=".", description="File or directory to search in")
    glob: str = Field(default="", description="Glob pattern to filter files, e.g. '*.py'")
    output_mode: str = Field(default="files_with_matches", description="Output mode: 'content', 'files_with_matches', or 'count'")
    head_limit: int = Field(default=250, description="Max output lines")
    case_insensitive: bool = Field(default=False, description="Case insensitive search (-i)")


class GrepTool(Tool):
    name = "Grep"
    description = "Search file contents using regex patterns (uses ripgrep)."
    params_model = GrepParams
    category = "read"
    is_concurrency_safe = True

    async def execute(self, params: BaseModel) -> ToolResult:
        p: GrepParams = params  # type: ignore
        try:
            cmd = ["rg", "--no-heading", "--with-filename", "--line-number"]
            if p.case_insensitive:
                cmd.append("-i")
            if p.glob:
                cmd.extend(["--glob", p.glob])
            if p.output_mode == "files_with_matches":
                cmd.append("-l")
            elif p.output_mode == "count":
                cmd.append("-c")
            cmd.append(p.pattern)
            cmd.append(p.path)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=Path(p.path).parent if Path(p.path).is_file() else p.path,
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n" + stderr.decode("utf-8", errors="replace")
            if not output.strip():
                return ToolResult(output=f"No matches for: {p.pattern}")
            lines = output.split("\n")
            if len(lines) > p.head_limit:
                output = "\n".join(lines[:p.head_limit]) + f"\n… ({len(lines) - p.head_limit} more matches)"
            if len(output) > MAX_OUTPUT_CHARS * 2:
                output = output[:MAX_OUTPUT_CHARS * 2] + "\n… (output truncated)"
            return ToolResult(output=output)
        except FileNotFoundError:
            # rg 不可用时降级为 Python 内置搜索
            return await self._fallback_search(p)
        except Exception as e:
            return ToolResult(output=f"Grep error: {e}", is_error=True)

    async def _fallback_search(self, p: GrepParams) -> ToolResult:
        try:
            base = Path(p.path)
            pattern = re.compile(p.pattern, re.IGNORECASE if p.case_insensitive else 0)
            results: list[str] = []
            files = list(base.rglob("*")) if base.is_dir() else [base]
            for f in files:
                if not f.is_file():
                    continue
                if any(s in f.parts for s in SKIP_DIRS):
                    continue
                if p.glob and not f.match(p.glob):
                    continue
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                    for i, line in enumerate(text.split("\n"), 1):
                        if pattern.search(line):
                            if p.output_mode == "files_with_matches":
                                results.append(str(f))
                                break
                            elif p.output_mode == "count":
                                pass  # handled below
                            else:
                                results.append(f"{f}:{i}:{line}")
                except Exception:
                    continue
                if len(results) >= p.head_limit:
                    break
            if not results:
                return ToolResult(output=f"No matches for: {p.pattern}")
            if p.output_mode == "count":
                return ToolResult(output=f"{len(results)} files matched")
            return ToolResult(output="\n".join(results[:p.head_limit]))
        except Exception as e:
            return ToolResult(output=f"Search error: {e}", is_error=True)


# ============================================================================
# 创建默认 ToolRegistry
# ============================================================================

def create_default_registry(work_dir: str = ".") -> ToolRegistry:
    registry = ToolRegistry(work_dir=work_dir)
    registry.register(BashTool(work_dir=work_dir))
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(EditFileTool())
    registry.register(GlobTool(work_dir=work_dir))
    registry.register(GrepTool())
    return registry
