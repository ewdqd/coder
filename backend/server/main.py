"""CodePet Agent Server — FastAPI 入口

提供:
- GET  /health           健康检查
- POST /chat             一次性对话 (非流式)
- WS   /ws               流式对话 (WebSocket)
- POST /session/new      创建新会话
- POST /session/clear    清除会话
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

# 路径设置: agent 和 core 模块在上级目录
_THIS_DIR = Path(__file__).resolve().parent        # .../backend/server/
_SERVER_DIR = _THIS_DIR.parent                      # .../backend/
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

from agent.client import create_client
from agent.conversation import ConversationManager
from agent.loop import Agent
from agent.prompts import build_system_prompt, build_environment_context
from agent.tools import create_default_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("code-pet-server")

# ============================================================================
# 全局状态
# ============================================================================

# 存储活跃会话: session_id -> ConversationManager
_sessions: dict[str, ConversationManager] = {}
_agent: Agent | None = None
_registry = None
_server_config: dict[str, Any] = {}
_work_dir: str = "."


def _load_config() -> dict[str, Any]:
    """加载配置文件。"""
    config_path = _SERVER_DIR / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def _get_or_create_session(session_id: str) -> ConversationManager:
    """获取或创建会话。"""
    if session_id not in _sessions:
        conv = ConversationManager()
        env_ctx = build_environment_context(_work_dir)
        conv.inject_environment(env_ctx)
        _sessions[session_id] = conv
        log.info("Created session: %s", session_id)
    return _sessions[session_id]


def _init_agent() -> Agent:
    """初始化 Agent。"""
    global _agent, _registry, _work_dir

    config = _load_config()
    providers = config.get("providers", [])
    if not providers:
        raise RuntimeError("No providers configured in config.yaml")

    provider = providers[0]
    protocol = provider.get("protocol", "anthropic")
    model = provider.get("model", "claude-sonnet-4-20250514")
    api_key = provider.get("api_key", "")
    base_url = provider.get("base_url", "")
    thinking = provider.get("thinking", False)
    max_tokens = provider.get("max_output_tokens", 8192)

    # API key fallback: 配置文件 -> 环境变量
    if not api_key:
        # DeepSeek 优先用 DEEPSEEK_API_KEY
        if "deepseek" in base_url.lower():
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            env_map = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
                "openai-compat": "OPENAI_API_KEY",
            }
            env_var = env_map.get(protocol, "OPENAI_API_KEY")
            api_key = os.environ.get(env_var, "")

    _server_config = config.get("server", {})
    _work_dir = os.getcwd()

    client = create_client(
        protocol=protocol,
        model=model,
        api_key=api_key,
        base_url=base_url,
        thinking=thinking,
        max_output_tokens=max_tokens,
    )

    _registry = create_default_registry(_work_dir)

    def make_prompt() -> str:
        return build_system_prompt(work_dir=_work_dir)

    _agent = Agent(
        client=client,
        registry=_registry,
        work_dir=_work_dir,
        system_prompt_fn=make_prompt,
    )
    log.info("Agent initialized: protocol=%s model=%s", protocol, model)
    return _agent


# ============================================================================
# FastAPI App
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化 Agent，关闭时清理。"""
    log.info("CodePet Agent Server starting...")
    try:
        _init_agent()
        log.info("CodePet Agent Server ready on %s:%s",
                 _server_config.get("host", "127.0.0.1"),
                 _server_config.get("port", 9876))
    except Exception as e:
        log.error("Failed to initialize agent: %s", e)
    yield
    log.info("CodePet Agent Server shutting down...")
    _sessions.clear()


app = FastAPI(
    title="CodePet Agent Server",
    description="Programmer's Desktop Pet - Python Agent Backend",
    version="0.1.0",
    lifespan=lifespan,
)


# ============================================================================
# REST API
# ============================================================================

@app.get("/health")
async def health_check():
    """健康检查端点。"""
    return {
        "status": "ok",
        "agent_id": _agent.agent_id if _agent else None,
        "active_sessions": len(_sessions),
    }


@app.post("/session/new")
async def create_session():
    """创建新会话，返回 session_id。"""
    import uuid
    session_id = uuid.uuid4().hex[:16]
    _get_or_create_session(session_id)
    return {"session_id": session_id}


@app.post("/session/{session_id}/clear")
async def clear_session(session_id: str):
    """清除指定会话的历史。"""
    if session_id in _sessions:
        conv = _sessions[session_id]
        conv.replace_history([])
        env_ctx = build_environment_context(_work_dir)
        conv.inject_environment(env_ctx)
        return {"status": "cleared", "session_id": session_id}
    return JSONResponse(status_code=404, content={"error": "Session not found"})


# ============================================================================
# WebSocket — 流式对话
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 端点 — 接收消息并流式返回 Agent 响应。"""
    await ws.accept()
    session_id: str | None = None

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)

            msg_type = data.get("type", "chat")

            if msg_type == "init":
                # 客户端初始化
                session_id = data.get("session_id", "")
                if not session_id:
                    import uuid
                    session_id = uuid.uuid4().hex[:16]
                conv = _get_or_create_session(session_id)
                # 如果客户端提供了 work_dir, 更新
                wd = data.get("work_dir", "")
                if wd and os.path.isdir(wd):
                    global _work_dir
                    _work_dir = wd
                await ws.send_json({
                    "type": "init_ack",
                    "session_id": session_id,
                    "agent_id": _agent.agent_id if _agent else "",
                })
                continue

            if msg_type == "clear":
                # 清除会话
                if session_id and session_id in _sessions:
                    conv = _sessions[session_id]
                    conv.replace_history([])
                    env_ctx = build_environment_context(_work_dir)
                    conv.inject_environment(env_ctx)
                await ws.send_json({"type": "cleared"})
                continue

            if msg_type == "chat":
                if not session_id:
                    import uuid
                    session_id = uuid.uuid4().hex[:16]
                conv = _get_or_create_session(session_id)
                message = data.get("message", "")

                if not message.strip():
                    await ws.send_json({
                        "type": "error",
                        "message": "Empty message",
                    })
                    continue

                # 添加用户消息
                conv.add_user_message(message)

                # 流式执行 Agent 并实时推送事件
                if _agent is None:
                    await ws.send_json({
                        "type": "error",
                        "message": "Agent not initialized. Check API key configuration.",
                    })
                    continue

                try:
                    async for event in _agent.run(conv):
                        await ws.send_json(_event_to_dict(event))
                except Exception as e:
                    log.exception("Agent error during chat")
                    await ws.send_json({
                        "type": "error",
                        "message": str(e),
                    })

                continue

            # 未知消息类型
            await ws.send_json({
                "type": "error",
                "message": f"Unknown message type: {msg_type}",
            })

    except WebSocketDisconnect:
        log.info("WebSocket disconnected: session=%s", session_id)
    except Exception as e:
        log.exception("WebSocket error")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


def _event_to_dict(event: Any) -> dict[str, Any]:
    """将 AgentEvent 转为 JSON 字典。"""
    from agent.loop import (
        AgentStreamText, AgentThinkingText, AgentToolUse,
        AgentToolResult, AgentTurnComplete, AgentLoopComplete,
        AgentError, AgentUsage,
    )

    if isinstance(event, AgentStreamText):
        return {"type": "text", "text": event.text}
    elif isinstance(event, AgentThinkingText):
        return {"type": "thinking", "text": event.text}
    elif isinstance(event, AgentToolUse):
        return {
            "type": "tool_use",
            "toolName": event.tool_name,
            "toolId": event.tool_id,
            "args": event.arguments,
        }
    elif isinstance(event, AgentToolResult):
        return {
            "type": "tool_result",
            "toolId": event.tool_id,
            "toolName": event.tool_name,
            "output": event.output[:1000],  # 截断输出避免撑爆 WebSocket
            "isError": event.is_error,
            "elapsed": round(event.elapsed, 2),
        }
    elif isinstance(event, AgentTurnComplete):
        return {"type": "turn_complete", "turn": event.turn}
    elif isinstance(event, AgentLoopComplete):
        return {"type": "loop_complete", "totalTurns": event.total_turns}
    elif isinstance(event, AgentError):
        return {"type": "error", "message": event.message}
    elif isinstance(event, AgentUsage):
        return {
            "type": "usage",
            "usage": {
                "inputTokens": event.input_tokens,
                "outputTokens": event.output_tokens,
            },
        }
    return {"type": "unknown"}
