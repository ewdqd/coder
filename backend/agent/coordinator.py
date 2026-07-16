"""多 Agent 协作 — Coordinator 任务拆分 + DAG 并行调度。

专职 Agent 池:
- Architect:   系统架构设计、技术选型
- Developer:   代码实现、功能开发
- QA:          测试用例、边界条件
- Reviewer:    代码审查、安全审计
- DevOps:      部署脚本、CI/CD 配置
- Analyst:     需求分析、数据建模
- Documenter:  文档生成、API 说明
- Debugger:    错误排查、性能分析

五层架构: 交互层 → 引擎层 → 工具层 → 记忆层 → 安全层
          └── Coordinator 横跨引擎层+工具层
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

log = logging.getLogger(__name__)


# ---- Agent 类型 ----
class AgentRole(str, Enum):
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    QA = "qa"
    REVIEWER = "reviewer"
    DEVOPS = "devops"
    ANALYST = "analyst"
    DOCUMENTER = "documenter"
    DEBUGGER = "debugger"


# 每个角色的系统提示词前缀
ROLE_PROMPTS: dict[AgentRole, str] = {
    AgentRole.ARCHITECT: (
        "You are a senior software architect. Your role is to design system "
        "architecture, choose technologies, and create high-level plans. "
        "Output structured design documents with trade-off analysis."
    ),
    AgentRole.DEVELOPER: (
        "You are an expert developer. Implement features according to the "
        "architecture spec. Write clean, tested, production-ready code. "
        "Follow the project's existing patterns and conventions."
    ),
    AgentRole.QA: (
        "You are a QA engineer. Write comprehensive test cases covering "
        "happy paths, edge cases, error conditions, and performance tests. "
        "Think adversarially — find the bugs before users do."
    ),
    AgentRole.REVIEWER: (
        "You are a code reviewer. Audit code for correctness, security, "
        "performance, and maintainability. Flag issues with severity levels. "
        "Suggest concrete improvements, not vague criticisms."
    ),
    AgentRole.DEVOPS: (
        "You are a DevOps engineer. Create deployment configurations, "
        "CI/CD pipelines, Docker files, and infrastructure-as-code. "
        "Ensure zero-downtime deployments and proper monitoring."
    ),
    AgentRole.ANALYST: (
        "You are a business analyst. Analyze requirements, model data, "
        "identify stakeholders, and define success metrics. "
        "Bridge the gap between business needs and technical implementation."
    ),
    AgentRole.DOCUMENTER: (
        "You are a technical writer. Generate clear API docs, READMEs, "
        "architecture decision records, and user guides. "
        "Write for both developers and non-technical stakeholders."
    ),
    AgentRole.DEBUGGER: (
        "You are a debugging specialist. Analyze error logs, stack traces, "
        "and system behavior to find root causes. "
        "Methodically eliminate hypotheses until the bug is isolated."
    ),
}


# ---- DAG 任务模型 ----
@dataclass
class SubTask:
    """子任务 — DAG 中的一个节点。"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str = ""
    description: str = ""
    role: AgentRole = AgentRole.DEVELOPER
    dependencies: list[str] = field(default_factory=list)  # 依赖的任务 ID
    status: str = "pending"  # pending | running | done | failed
    result: str = ""
    assigned_agent: str = ""  # agent_id


@dataclass
class TaskDAG:
    """任务 DAG — Coordinator 分解复杂任务的结果。"""
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    description: str = ""
    nodes: list[SubTask] = field(default_factory=list)
    status: str = "pending"

    def get_ready_tasks(self) -> list[SubTask]:
        """获取所有依赖已满足的待执行任务。"""
        done_ids = {n.id for n in self.nodes if n.status == "done"}
        ready = []
        for node in self.nodes:
            if node.status != "pending":
                continue
            if all(dep in done_ids for dep in node.dependencies):
                ready.append(node)
        return ready

    def is_complete(self) -> bool:
        return all(n.status in ("done", "failed") for n in self.nodes)

    def get_result_summary(self) -> str:
        """汇总所有子任务结果。"""
        parts = [f"## Task: {self.title}\n"]
        for node in self.nodes:
            status_icon = {"done": "OK", "failed": "FAIL", "pending": "...", "running": ">"}
            icon = status_icon.get(node.status, "?")
            parts.append(f"- [{icon}] **{node.role.value}**: {node.title}")
            if node.result:
                parts.append(f"  {node.result[:300]}")
        return "\n".join(parts)


# ---- Coordinator Agent ----
class CoordinatorAgent:
    """Coordinator Agent — 任务分解 + DAG 调度 + 结果汇总。

    工作流程:
    1. 接收用户复杂需求
    2. LLM 分解为 DAG (多个 SubTask)
    3. 拓扑排序 → 并行执行无依赖任务
    4. 失败重试/降级/人工兜底
    5. 汇总所有结果返回用户
    """

    MAX_PARALLEL = 5           # 最大并行 Agent 数
    MAX_RETRIES = 2            # 单个子任务最大重试次数
    DEFAULT_TIMEOUT = 300      # 单个子任务超时 (秒)

    def __init__(
        self,
        agent_factory: Callable[[AgentRole], Any],  # 创建 Agent 实例的工厂函数
        llm_client: Any = None,                      # 用于分解任务的 LLM
    ):
        self._factory = agent_factory
        self._llm = llm_client
        self._running: dict[str, asyncio.Task] = {}

    async def execute(
        self,
        user_request: str,
        context: str = "",
        on_progress: Callable[[str], None] | None = None,
    ) -> str:
        """执行复杂任务的主入口。

        Args:
            user_request: 用户的需求描述
            context: 项目上下文（文件列表、现有架构等）
            on_progress: 进度回调

        Returns:
            汇总的执行结果
        """
        # Step 1: 分解任务
        if on_progress:
            on_progress("[Coordinator] Analyzing and decomposing task...")
        dag = await self._decompose(user_request, context)
        if not dag.nodes:
            return "[Coordinator] Failed to decompose task."

        if on_progress:
            on_progress(
                f"[Coordinator] Decomposed into {len(dag.nodes)} subtasks: "
                + ", ".join(f"{n.role.value}({n.title})" for n in dag.nodes)
            )

        # Step 2: 拓扑排序 + 并行执行
        if on_progress:
            on_progress("[Coordinator] Executing DAG...")

        retry_counts: dict[str, int] = {}

        while not dag.is_complete():
            ready = dag.get_ready_tasks()

            if not ready:
                # 检查是否有死锁（没有 ready 但不 complete）
                running = [n for n in dag.nodes if n.status == "running"]
                if not running:
                    pending = [n for n in dag.nodes if n.status == "pending"]
                    if pending:
                        # 有 pending 但不 ready = 依赖循环或依赖失败
                        stuck = [n.id for n in pending]
                        if on_progress:
                            on_progress(f"[Coordinator] WARNING: Stuck tasks: {stuck}")
                        for n in pending:
                            n.status = "failed"
                            n.result = "Dependency not satisfied"
                        break
                await asyncio.sleep(0.5)
                continue

            # 并行执行所有就绪任务
            batch = ready[:self.MAX_PARALLEL]
            if on_progress:
                on_progress(
                    f"[Coordinator] Running: "
                    + ", ".join(f"{n.role.value}:{n.title}" for n in batch)
                )

            tasks = [self._execute_subtask(node) for node in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for node, result in zip(batch, results):
                if isinstance(result, Exception):
                    retry_counts[node.id] = retry_counts.get(node.id, 0) + 1
                    if retry_counts[node.id] <= self.MAX_RETRIES:
                        node.status = "pending"  # 重试
                        if on_progress:
                            on_progress(
                                f"[Coordinator] {node.role.value}:{node.title} "
                                f"failed, retrying ({retry_counts[node.id]}/{self.MAX_RETRIES})"
                            )
                    else:
                        node.status = "failed"
                        node.result = f"Failed after {self.MAX_RETRIES} retries: {result}"
                        if on_progress:
                            on_progress(
                                f"[Coordinator] {node.role.value}:{node.title} FAILED"
                            )
                else:
                    node.status = "done"
                    node.result = result
                    if on_progress:
                        on_progress(
                            f"[Coordinator] {node.role.value}:{node.title} DONE"
                        )

        # Step 3: 汇总结果
        if on_progress:
            on_progress("[Coordinator] Aggregating results...")

        return dag.get_result_summary()

    async def _decompose(self, request: str, context: str) -> TaskDAG:
        """使用 LLM 将用户需求分解为 DAG。"""
        # 启发式分解（生产环境用 LLM 驱动）
        dag = TaskDAG(title=request[:80], description=request)

        # 根据需求关键词选择合适的 Agent 角色
        roles_needed: list[AgentRole] = self._analyze_required_roles(request)

        # 为每个角色创建一个子任务
        prev_id: str | None = None
        for i, role in enumerate(roles_needed):
            node = SubTask(
                title=self._role_task_title(role, request),
                description=request,
                role=role,
                dependencies=[prev_id] if prev_id else [],
            )
            dag.nodes.append(node)
            if i == 0:
                prev_id = node.id  # 链式依赖: A → D → Q → R → O
            # 最后几个角色可以并行
            if i >= len(roles_needed) - 3:
                node.dependencies = [dag.nodes[0].id] if dag.nodes else []

        return dag

    def _analyze_required_roles(self, request: str) -> list[AgentRole]:
        """分析需求中需要哪些 Agent 角色。"""
        req_lower = request.lower()
        roles: list[AgentRole] = []

        # 关键词 → 角色映射
        keyword_map = [
            (["架构", "设计", "architecture", "design", "技术选型"],
             AgentRole.ARCHITECT),
            (["实现", "开发", "写代码", "implement", "develop", "code", "build"],
             AgentRole.DEVELOPER),
            (["测试", "test", "qa", "质量", "quality", "用例"],
             AgentRole.QA),
            (["审查", "review", "审计", "audit", "检查", "安全"],
             AgentRole.REVIEWER),
            (["部署", "deploy", "ci/cd", "docker", "k8s", "上线", "发布"],
             AgentRole.DEVOPS),
            (["分析", "analysis", "需求", "requirement", "数据"],
             AgentRole.ANALYST),
            (["文档", "doc", "readme", "说明", "api"],
             AgentRole.DOCUMENTER),
            (["调试", "debug", "bug", "错误", "error", "fix", "修复"],
             AgentRole.DEBUGGER),
        ]

        for keywords, role in keyword_map:
            if any(kw in req_lower for kw in keywords):
                if role not in roles:
                    roles.append(role)

        # 默认至少包含 Developer + Reviewer
        if not roles:
            roles = [
                AgentRole.ARCHITECT, AgentRole.DEVELOPER,
                AgentRole.QA, AgentRole.REVIEWER,
            ]

        return roles

    @staticmethod
    def _role_task_title(role: AgentRole, request: str) -> str:
        """生成角色的任务标题。"""
        titles = {
            AgentRole.ARCHITECT: f"Design architecture for: {request[:40]}",
            AgentRole.DEVELOPER: f"Implement: {request[:40]}",
            AgentRole.QA: f"Test: {request[:40]}",
            AgentRole.REVIEWER: f"Review: {request[:40]}",
            AgentRole.DEVOPS: f"Deploy config for: {request[:40]}",
            AgentRole.ANALYST: f"Analyze requirements: {request[:40]}",
            AgentRole.DOCUMENTER: f"Document: {request[:40]}",
            AgentRole.DEBUGGER: f"Debug: {request[:40]}",
        }
        return titles.get(role, request[:40])

    async def _execute_subtask(self, node: SubTask) -> str:
        """执行单个子任务。"""
        try:
            agent = self._factory(node.role)
            node.status = "running"
            result = await asyncio.wait_for(
                agent(node.description),
                timeout=self.DEFAULT_TIMEOUT,
            )
            return str(result)
        except asyncio.TimeoutError:
            return f"Timeout after {self.DEFAULT_TIMEOUT}s"
        except Exception as e:
            raise  # 让外层处理重试


# ---- 简单任务分发器 ----
class SimpleTaskDispatcher:
    """简化版任务分发器 — 不依赖完整 DAG 的快速多 Agent 调用。

    用法:
        dispatcher = SimpleTaskDispatcher()
        results = await dispatcher.dispatch(
            "设计秒杀系统",
            roles=[AgentRole.ARCHITECT, AgentRole.DEVELOPER],
        )
    """

    def __init__(self, agent_fn: Callable[[AgentRole, str], Coroutine] | None = None):
        self._agent_fn = agent_fn

    async def dispatch(
        self, task: str, roles: list[AgentRole],
        parallel: bool = True,
    ) -> dict[AgentRole, str]:
        """分发任务到多个 Agent。

        Args:
            task: 任务描述
            roles: 参与的 Agent 角色列表
            parallel: True=并行执行, False=顺序执行

        Returns:
            {role: result} 字典
        """
        results: dict[AgentRole, str] = {}

        if parallel:
            async def run_one(role: AgentRole):
                if self._agent_fn:
                    return role, await self._agent_fn(role, task)
                return role, f"[{role.value}] Task: {task[:50]}..."
            coros = [run_one(r) for r in roles]
            done = await asyncio.gather(*coros, return_exceptions=True)
            for item in done:
                if isinstance(item, Exception):
                    continue
                role, result = item
                results[role] = result
        else:
            for role in roles:
                if self._agent_fn:
                    results[role] = await self._agent_fn(role, task)
                else:
                    results[role] = f"[{role.value}] Task: {task[:50]}..."

        return results
