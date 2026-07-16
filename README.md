# 🐰 pet — AI 桌面宠物

> **Windows 桌面 AI 宠物 | 五层 Agent 架构 | 多模态视觉 | 多 Agent 协作 | 跨会话记忆**

一款 Windows 桌面精灵宠物，搭载自研 AI Agent 大脑。不是 ChatGPT 套壳——**五层 Agent 架构**，支持多模态视觉理解、8 种专职子 Agent 协作、跨会话记忆继承。77MB 自包含 EXE，双击即用。

---

## 系统架构

```
C# WPF 前端 (桌面宠物)          Python FastAPI 后端 (AI 大脑)
┌─────────────────────┐       ┌──────────────────────────┐
│ 48帧精灵动画         │  WS   │ [L1] 交互层：FastAPI+WS   │
│ 像素级透明穿透        │◄─────►│ [L2] 引擎层：ReAct 推理   │
│ 全局热键 / 托盘       │ 8 种  │ [L3] 工具层：6大编程工具   │
│ 拖拽 / 点击分区       │ 事件  │ [L4] 记忆层：四类记忆     │
│ TTS语音 / 截图       │ 类型  │ [L5] 安全层：沙箱+黑名单  │
│ 26 个 Service 模块    │       │ 横向：多模态 + 多Agent    │
└─────────────────────┘       └──────────────────────────┘
   .NET 8 WPF 自包含              Python 3400+ 行 / 20 文件
   77MB 单文件 EXE                本地 WebSocket <1ms
```

---

## 功能特性

### 🦊 桌面宠物

- **透明置顶** — per-pixel alpha 像素级透明，角色空白区域自动穿透不遮挡桌面
- **48 帧精灵动画** — 待机、走路、摸头、比心、亲亲、跳舞、睡觉...
- **点击分区反馈** — 头/身体/脚底不同区域不同反应，连击彩蛋
- **拖拽交互** — 拖放文件/文件夹自动 AI 分析；按住拖动任意移动
- **系统托盘** — 最小化到托盘，右键菜单完整功能
- **全局热键** — `Ctrl+Shift+S` 显隐、`Ctrl+Shift+C` 聊天、`Ctrl+Shift+P` 穿透
- **健康提醒** — 喝水提醒、休息提醒、25 分钟专注计时
- **多显示器** — 自动边界保护，全屏应用自动隐藏
- **全本地存储** — 无需账号，无云同步，数据仅存本机

### 🧠 AI Agent 五层架构

| 层 | 职责 | 核心实现 |
|----|------|----------|
| 交互层 | 通信管理 | FastAPI + WebSocket，8 种流式事件 |
| 引擎层 | 推理控制 | ReAct Loop，并行工具调度，50 轮迭代 |
| 工具层 | 能力扩展 | 6 编程工具 + MCP 延迟加载 (Token-85%) |
| 记忆层 | 上下文记忆 | 四类记忆提取，跨会话继承，语义去重 |
| 安全层 | 风险管控 | 路径沙箱、15+ 命令黑名单、四级权限 |

### 👁️ 多模态视觉

- **截图分析** — "这段代码报错是什么原因？"
- **UI 审查** — "这个界面布局有什么改进建议？"
- **图表理解** — "解释这个架构图的要点"
- **代码诊断** — "这个 warning 怎么修复？"
- 支持 GPT-4o / Claude Vision / DeepSeek-VL2

### 🤖 多 Agent 协作

- **8 种专职角色** — 架构师、开发、测试、审查、运维、分析、文档、调试
- **Coordinator DAG 调度** — 任务分解 → 拓扑排序 → 并行执行 → 结果汇总
- **自动容错** — 失败重试最多 2 次，不阻塞其他任务

### 🛡️ 安全防护

- **Pydantic 参数强校验** — 类型/格式不匹配秒级拦截
- **PathSandbox 路径沙箱** — 所有文件操作限制在工作目录内
- **15+ 命令黑名单** — `rm -rf`、`format`、`curl|sh` 实时拦截
- **四级权限模式** — plan (禁写) / default (确认) / acceptEdits / bypass

---

## 快速开始

### 一键启动

双击 `一键启动.bat`，自动完成：
1. 检查 Python 3.11+
2. 创建虚拟环境
3. 安装依赖
4. 启动 AI 后端 (127.0.0.1:9876)
5. 启动桌面宠物

### 手动启动

```bash
# 1. 启动 AI 后端
cd backend
pip install fastapi uvicorn pydantic pyyaml httpx anthropic openai pillow
python __main__.py

# 2. 启动桌面宠物（首次需构建）
cd pet-desktop
dotnet publish pet/pet.csproj -c Release -r win-x64 --self-contained -o publish
start publish/pet.exe
```

### 配置 API Key

编辑 `backend/config.yaml`：

```yaml
providers:
  - name: deepseek
    protocol: openai-compat
    base_url: https://api.deepseek.com/v1
    model: deepseek-chat
    api_key: "sk-你的API密钥"
```

支持 DeepSeek、OpenAI、Anthropic 及任何 OpenAI 兼容接口。

---

## 项目结构

```
pet/
├── 一键启动.bat                  # 一键启动脚本
├── launcher.py                   # Python 启动器（进程管理）
├── README.md
│
├── backend/                      # Python AI Agent 后端
│   ├── __main__.py               # 入口：uvicorn 服务启动
│   ├── setup.py                  # 依赖自动检查安装
│   ├── config.yaml               # LLM API Key 配置
│   ├── server/main.py            # [L1] FastAPI + WebSocket
│   ├── agent/
│   │   ├── loop.py               # [L2] ReAct 推理引擎
│   │   ├── context.py            # [L2] 上下文压缩 (L1/L2)
│   │   ├── coordinator.py        # 多 Agent DAG 调度
│   │   ├── multimodal.py         # 多模态视觉理解管线
│   │   ├── memory.py             # [L4] 四类记忆提取继承
│   │   ├── mcp.py                # [L3] MCP 延迟加载
│   │   ├── client.py             # 多协议 LLM 客户端
│   │   ├── prompts.py            # 系统提示词构建器
│   │   └── tools.py              # [L3] 6 大编程工具
│   └── core/
│       ├── base.py               # Tool / ToolResult 基类
│       ├── conversation.py       # ConversationManager
│       ├── serialization.py      # 三协议消息序列化
│       └── security.py           # [L5] 沙箱 + 黑名单 + 权限
│
└── pet-desktop/                  # C# WPF 桌面宠物前端
    ├── pet.sln                   # Visual Studio 解决方案
    ├── pet/                      # .NET 8 WPF 项目源码
    │   ├── MainWindow.xaml/.cs   # 透明桌宠主窗口
    │   ├── ChatWindow.xaml/.cs   # AI 流式聊天窗口
    │   ├── SettingsWindow.xaml   # 个性化设置
    │   ├── Controls/             # CodeBlockView / ToolCallCard
    │   ├── Services/             # 26 个服务模块
    │   │   ├── AgentBridge.cs    # WebSocket 桥接 + 进程管理
    │   │   ├── AiAgentService.cs # AI 对话服务
    │   │   ├── VoiceService.cs   # TTS + ASR 语音
    │   │   ├── HotkeyService.cs  # 全局热键
    │   │   └── ... (22 个服务)
    │   ├── Engine/               # 宠物动作引擎
    │   ├── Models/PetSettings.cs # 配置模型
    │   └── Assets/Sprites/       # 48 张精灵 PNG
    ├── Artwork/                  # 角色设计稿 + 演示截图
    └── tools/                    # 辅助工具脚本
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 桌面 GUI | C# WPF .NET 8（77MB 自包含） |
| AI 后端 | Python FastAPI + uvicorn |
| LLM 客户端 | anthropic + openai SDK（多协议） |
| 参数校验 | Pydantic 2.0+ |
| 视觉处理 | Pillow + GPT-4o / Claude Vision |
| 通信协议 | WebSocket (IETF 6455)，本地 <1ms |
| 记忆存储 | JSON 本地文件 |
| 安全 | PathSandbox + 15 正则黑名单 + 4 级权限 |
| 语音 | Windows SAPI |
| 热键 | RegisterHotKey (user32.dll) |
| 打包 | .NET Publish Self-Contained Single File |

---

## 交互方式

| 操作 | 效果 |
|------|------|
| 单击头/身体/脚底 | 分区不同反应 |
| 双击 | 比心 + 亲亲动画 |
| 中键点击 | 打开 AI 聊天窗口 |
| 右键点击 | 完整功能菜单 |
| 拖放文件 | AI 自动分析文件内容 |
| 按住拖动 | 任意移动位置 |
| Ctrl+Shift+S | 显示 / 隐藏 |
| Ctrl+Shift+C | 打开聊天 |
| Ctrl+Shift+P | 切换鼠标穿透 |

---

## License

MIT
