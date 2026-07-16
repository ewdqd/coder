# 🐰 pet — AI Desktop Companion

> **Windows 桌面 AI 宠物 | 五层 Agent 架构 | 多模态 | 多 Agent 协作 | 跨会话记忆**

A Windows desktop pet with a self-built AI Agent brain. Not a ChatGPT wrapper — a **five-layer Agent architecture** with multimodal vision, 8-role multi-agent collaboration, and cross-session memory inheritance.

---

## Architecture

```
C# WPF (Desktop Pet)          Python FastAPI (AI Backend)
┌─────────────────────┐       ┌──────────────────────────┐
│ 48-frame sprite     │  WS   │ [L1] Interaction Layer    │
│ Per-pixel alpha     │◄─────►│ [L2] ReAct Engine         │
│ Global hotkeys      │ 8     │ [L3] Tool Layer (6 tools) │
│ System tray         │ event │ [L4] Memory Layer         │
│ TTS / ASR           │ types │ [L5] Security Layer       │
│ Desktop capture     │       │                           │
│ 26 Service modules  │       │ Multimodal + Multi-Agent  │
└─────────────────────┘       └──────────────────────────┘
      77MB self-contained            3400+ lines Python
      .NET 8 WPF                     20 files
```

---

## Features

### Desktop Pet
- **Transparent overlay** — per-pixel alpha, empty areas auto-pass-through
- **48-frame sprite animations** — idle, walk, headpat, heart, kiss, dance...
- **Drag & drop** — drop files/folders for AI analysis
- **Click zones** — head / body / feet respond differently
- **System tray** — minimize to tray, right-click menu
- **Global hotkeys** — Ctrl+Shift+S (show/hide), Ctrl+Shift+C (chat)
- **Health reminders** — drink water, take breaks, 25-min focus timer
- **Multi-monitor** — boundary protection, fullscreen auto-hide
- **All local** — no account, no cloud sync

### AI Agent
- **ReAct Loop** — Observe → Think → Act → Observe, up to 50 iterations
- **8 WebSocket event types** — text, thinking, tool_use, tool_result, usage...
- **6 core tools** — Bash, Read, Write, Edit, Grep, Glob
- **MCP lazy loading** — 85% token reduction for 100+ tools
- **4-type memory** — preferences, corrections, project knowledge, references
- **Cross-session inheritance** — new sessions auto-load past context
- **L1/L2 context compression** — hours-long sessions without context loss

### Multimodal
- **Screenshot analysis** — "What does this error mean?"
- **UI review** — "How can I improve this layout?"
- **Chart understanding** — "Explain this architecture diagram"
- **Code diagnosis** — "How do I fix this warning?"
- Supports GPT-4o, Claude Vision, DeepSeek-VL2

### Multi-Agent Collaboration
- **8 specialized roles** — Architect, Developer, QA, Reviewer, DevOps, Analyst, Documenter, Debugger
- **Coordinator + DAG** — decompose → topological sort → parallel execution
- **Auto-retry** — failed tasks retry up to 2×, don't block others

### Security
- **Pydantic validation** — strong-typed parameter checking
- **Path sandbox** — all operations restricted to work_dir
- **15+ command blacklist** — `rm -rf`, `format`, `curl|sh` blocked
- **4 permission modes** — plan / default / acceptEdits / bypass

---

## Quick Start

### One-Click Launch
```
双击 一键启动.bat
```

The launcher automatically:
1. Checks Python 3.11+
2. Creates virtual environment
3. Installs dependencies (fastapi, uvicorn, anthropic, openai...)
4. Starts AI backend (127.0.0.1:9876)
5. Launches desktop pet

### Manual Start

```bash
# 1. Start AI backend
cd backend
pip install fastapi uvicorn pydantic pyyaml httpx anthropic openai pillow
python __main__.py

# 2. Start desktop pet (build first time)
cd pet-desktop
dotnet publish pet/pet.csproj -c Release -r win-x64 --self-contained -o publish
start publish/pet.exe
```

### Configure API Key

Edit `backend/config.yaml`:
```yaml
providers:
  - name: deepseek
    protocol: openai-compat
    base_url: https://api.deepseek.com/v1
    model: deepseek-chat
    api_key: "sk-your-api-key"
```

Supported: DeepSeek, OpenAI, Anthropic, or any OpenAI-compatible API.

---

## Project Structure

```
pet/
├── 一键启动.bat              # One-click launcher
├── launcher.py               # Python process manager
├── README.md
│
├── backend/                  # Python AI Agent (20 files, 3400+ lines)
│   ├── __main__.py           # Entry: uvicorn server
│   ├── setup.py              # Dependency installer
│   ├── config.yaml           # LLM API key config
│   ├── server/main.py        # [L1] FastAPI + WebSocket (8 events)
│   ├── agent/
│   │   ├── loop.py           # [L2] ReAct engine (50 iterations)
│   │   ├── context.py        # [L2] L1/L2 context compression
│   │   ├── coordinator.py    # Multi-Agent DAG scheduler
│   │   ├── multimodal.py     # Vision understanding pipeline
│   │   ├── memory.py         # [L4] 4-type memory extraction
│   │   ├── mcp.py            # [L3] MCP lazy loading (85% savings)
│   │   ├── client.py         # Multi-protocol LLM client
│   │   ├── prompts.py        # System prompt builder
│   │   └── tools.py          # [L3] 6 programming tools
│   └── core/
│       ├── base.py           # Tool / ToolResult / StreamEvent
│       ├── conversation.py   # ConversationManager / Message
│       ├── serialization.py  # 3-format message adapter
│       └── security.py       # [L5] Sandbox + blacklist + permissions
│
└── pet-desktop/              # C# WPF Desktop Pet
    ├── pet.sln               # Visual Studio solution
    ├── pet/                  # .NET 8 WPF project
    │   ├── MainWindow.xaml   # Transparent pet window
    │   ├── ChatWindow.xaml   # AI chat window
    │   ├── SettingsWindow.xaml
    │   ├── Controls/         # CodeBlockView, ToolCallCard
    │   ├── Services/         # 26 service modules
    │   │   ├── AgentBridge.cs       # WebSocket bridge
    │   │   ├── AiAgentService.cs    # AI conversation
    │   │   ├── VoiceService.cs      # TTS + ASR
    │   │   ├── HotkeyService.cs     # Global hotkeys
    │   │   ├── DesktopCaptureService.cs
    │   │   └── ... (21 more)
    │   ├── Engine/           # Pet action engine
    │   ├── Models/           # PetSettings
    │   └── Assets/Sprites/   # 48 sprite PNGs
    ├── Artwork/              # Character sheets + screenshots
    └── publish/              # 77MB self-contained EXE
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Desktop GUI | C# WPF .NET 8 (self-contained 77MB) |
| AI Backend | Python FastAPI + uvicorn |
| LLM | anthropic + openai SDK (multi-protocol) |
| Validation | Pydantic 2.0+ |
| Vision | Pillow + GPT-4o / Claude Vision |
| Communication | WebSocket (IETF 6455), <1ms local |
| Memory | JSON local persistent storage |
| Security | PathSandbox + 15-rule blacklist + 4-level permissions |
| Voice | Windows SAPI |
| Hotkeys | RegisterHotKey (user32.dll) |

---

## Interaction

| Action | Result |
|--------|--------|
| Click head/body/feet | Zone-specific reactions |
| Double-click | Heart + kiss animation |
| Middle-click | Open AI chat window |
| Right-click | Full context menu |
| Drag & drop file | AI analyzes the file |
| Hold & drag pet | Move anywhere on desktop |
| Ctrl+Shift+S | Show / hide |
| Ctrl+Shift+C | Open chat |
| Ctrl+Shift+P | Toggle click passthrough |

---

## License

MIT
