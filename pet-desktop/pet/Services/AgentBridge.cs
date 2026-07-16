using System.Diagnostics;
using System.Net.Http;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;

namespace pet.Services;

/// <summary>
/// Python Agent Server 桥接器。
/// 负责：启动/停止 Python 进程、WebSocket 流式通信、HTTP 健康检查。
/// </summary>
public sealed class AgentBridge : IDisposable
{
    // ---- 配置 ----
    public const int DefaultPort = 9876;
    public const string DefaultHost = "127.0.0.1";

    // ---- 状态 ----
    private Process? _pythonProcess;
    private ClientWebSocket? _ws;
    private CancellationTokenSource? _wsCts;
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(5) };
    private string _sessionId = "";
    private bool _started;

    // ---- 公开属性 ----
    public string Host { get; set; } = DefaultHost;
    public int Port { get; set; } = DefaultPort;
    public string PythonPath { get; set; } = "python";
    public string ServerDir { get; set; } = "";
    public string WorkDir { get; set; } = "";
    public bool Connected => _ws?.State == WebSocketState.Open;
    public string SessionId => _sessionId;
    public event Action<string>? OnLog;

    private string BaseUrl => $"http://{Host}:{Port}";
    private string WsUrl => $"ws://{Host}:{Port}/ws";

    // ====================================================================
    // 进程管理
    // ====================================================================

    /// <summary>
    /// 启动 Python Agent Server 进程。
    /// 如果已经运行则跳过。
    /// </summary>
    public async Task<bool> StartServerAsync()
    {
        if (_pythonProcess is { HasExited: false })
        {
            Log("Python server already running.");
            return true;
        }

        var serverDir = string.IsNullOrEmpty(ServerDir)
            ? AppDomain.CurrentDomain.BaseDirectory
            : ServerDir;

        var startInfo = new ProcessStartInfo
        {
            FileName = PythonPath,
            Arguments = $"__main__.py --host {Host} --port {Port}",
            WorkingDirectory = serverDir,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };

        // 传递 API Key 环境变量
        if (!startInfo.EnvironmentVariables.ContainsKey("ANTHROPIC_API_KEY"))
        {
            var envKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY");
            if (!string.IsNullOrEmpty(envKey))
                startInfo.EnvironmentVariables["ANTHROPIC_API_KEY"] = envKey;
        }

        try
        {
            _pythonProcess = Process.Start(startInfo);
            if (_pythonProcess == null)
            {
                Log("Failed to start Python process.");
                return false;
            }

            _pythonProcess.OutputDataReceived += (_, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data)) Log($"[Python] {e.Data}");
            };
            _pythonProcess.ErrorDataReceived += (_, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data)) Log($"[Python:err] {e.Data}");
            };
            _pythonProcess.BeginOutputReadLine();
            _pythonProcess.BeginErrorReadLine();

            // 等待服务器就绪
            for (int i = 0; i < 30; i++)
            {
                await Task.Delay(500);
                if (await HealthCheckAsync())
                {
                    _started = true;
                    Log("Python server started successfully.");
                    return true;
                }
            }

            Log("Python server did not start in time.");
            return false;
        }
        catch (Exception ex)
        {
            Log($"Failed to start Python server: {ex.Message}");
            return false;
        }
    }

    /// <summary>
    /// 停止 Python 进程。
    /// </summary>
    public void StopServer()
    {
        try
        {
            _pythonProcess?.Kill(entireProcessTree: true);
            _pythonProcess?.Dispose();
            _pythonProcess = null;
        }
        catch (Exception ex)
        {
            Log($"Error stopping server: {ex.Message}");
        }
        _started = false;
    }

    // ====================================================================
    // 健康检查
    // ====================================================================

    /// <summary>
    /// 检查 Agent Server 是否在线。
    /// </summary>
    public async Task<bool> HealthCheckAsync()
    {
        try
        {
            var response = await _http.GetAsync($"{BaseUrl}/health");
            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    // ====================================================================
    // WebSocket 通信
    // ====================================================================

    /// <summary>
    /// 建立 WebSocket 连接并初始化会话。
    /// </summary>
    public async Task<bool> ConnectAsync(string? workDir = null)
    {
        if (_ws?.State == WebSocketState.Open)
            return true;

        _wsCts?.Cancel();
        _wsCts = new CancellationTokenSource();
        _ws = new ClientWebSocket();

        try
        {
            await _ws.ConnectAsync(new Uri(WsUrl), _wsCts.Token);

            // 发送初始化消息
            var workDirStr = workDir ?? WorkDir;
            if (string.IsNullOrEmpty(workDirStr))
                workDirStr = Environment.CurrentDirectory;

            var initMsg = new
            {
                type = "init",
                work_dir = workDirStr,
                session_id = _sessionId,
            };
            await SendJsonAsync(initMsg);

            // 接收 init_ack
            var ackJson = await ReceiveTextAsync(TimeSpan.FromSeconds(10));
            if (ackJson != null)
            {
                var ack = JsonSerializer.Deserialize<JsonElement>(ackJson);
                if (ack.TryGetProperty("session_id", out var sid))
                    _sessionId = sid.GetString() ?? "";
                Log($"Connected. Session: {_sessionId}");
            }

            return true;
        }
        catch (Exception ex)
        {
            Log($"WebSocket connection failed: {ex.Message}");
            _ws?.Dispose();
            _ws = null;
            return false;
        }
    }

    /// <summary>
    /// 发送流式对话请求，通过回调接收每个事件。
    /// </summary>
    public async Task<AgentChatResult> ChatAsync(
        string message,
        Action<AgentEvent>? onEvent = null,
        CancellationToken cancellationToken = default)
    {
        var result = new AgentChatResult();

        if (_ws?.State != WebSocketState.Open)
        {
            result.Error = "WebSocket not connected.";
            return result;
        }

        try
        {
            // 发送消息
            var chatMsg = new
            {
                type = "chat",
                message,
                session_id = _sessionId,
            };
            await SendJsonAsync(chatMsg);

            // 循环接收事件直到 loop_complete 或 error
            var buffer = new byte[65536];
            var sb = new StringBuilder();

            while (_ws.State == WebSocketState.Open && !cancellationToken.IsCancellationRequested)
            {
                var receiveResult = await _ws.ReceiveAsync(
                    new ArraySegment<byte>(buffer), cancellationToken);

                sb.Append(Encoding.UTF8.GetString(buffer, 0, receiveResult.Count));

                if (receiveResult.EndOfMessage)
                {
                    var json = sb.ToString();
                    sb.Clear();

                    try
                    {
                        var evt = ParseEvent(json);
                        onEvent?.Invoke(evt);

                        switch (evt.Type)
                        {
                            case "text":
                                result.Text += evt.Text;
                                break;
                            case "tool_use":
                                result.ToolCalls.Add(new ToolCallRecord(
                                    evt.ToolName ?? "", evt.ToolId ?? ""));
                                break;
                            case "tool_result":
                                if (result.ToolCalls.Count > 0)
                                {
                                    var last = result.ToolCalls[^1];
                                    last.Output = (evt.Output ?? "")[..Math.Min(evt.Output?.Length ?? 0, 500)];
                                    last.IsError = evt.IsError;
                                }
                                break;
                            case "error":
                                result.Error = evt.ErrorMessage;
                                return result;
                            case "loop_complete":
                                return result;
                            case "usage":
                                result.InputTokens = evt.InputTokens;
                                result.OutputTokens = evt.OutputTokens;
                                break;
                        }
                    }
                    catch (JsonException)
                    {
                        // 忽略解析错误的帧
                    }
                }
            }
        }
        catch (OperationCanceledException)
        {
            result.Error = "Cancelled.";
        }
        catch (WebSocketException ex)
        {
            result.Error = $"WebSocket error: {ex.Message}";
        }
        catch (Exception ex)
        {
            result.Error = $"Chat error: {ex.Message}";
        }

        return result;
    }

    /// <summary>
    /// 清除会话历史。
    /// </summary>
    public async Task ClearSessionAsync()
    {
        if (_ws?.State == WebSocketState.Open)
        {
            var clearMsg = new { type = "clear" };
            await SendJsonAsync(clearMsg);
        }
    }

    /// <summary>
    /// 断开 WebSocket。
    /// </summary>
    public async Task DisconnectAsync()
    {
        _wsCts?.Cancel();
        if (_ws?.State == WebSocketState.Open)
        {
            try
            {
                await _ws.CloseAsync(
                    WebSocketCloseStatus.NormalClosure, "Goodbye", CancellationToken.None);
            }
            catch { /* ignore */ }
        }
        _ws?.Dispose();
        _ws = null;
        _sessionId = "";
    }

    // ====================================================================
    // 内部辅助
    // ====================================================================

    private async Task SendJsonAsync(object obj)
    {
        if (_ws?.State != WebSocketState.Open) return;
        var json = JsonSerializer.Serialize(obj);
        var bytes = Encoding.UTF8.GetBytes(json);
        await _ws.SendAsync(
            new ArraySegment<byte>(bytes), WebSocketMessageType.Text,
            endOfMessage: true, _wsCts?.Token ?? CancellationToken.None);
    }

    private async Task<string?> ReceiveTextAsync(TimeSpan timeout)
    {
        if (_ws?.State != WebSocketState.Open) return null;
        var buffer = new byte[65536];
        var sb = new StringBuilder();

        using var cts = new CancellationTokenSource(timeout);
        try
        {
            while (true)
            {
                var result = await _ws.ReceiveAsync(
                    new ArraySegment<byte>(buffer), cts.Token);
                sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                if (result.EndOfMessage) break;
            }
            return sb.ToString();
        }
        catch
        {
            return null;
        }
    }

    private static AgentEvent ParseEvent(string json)
    {
        var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        var evt = new AgentEvent();
        if (root.TryGetProperty("type", out var typeProp))
            evt.Type = typeProp.GetString() ?? "";

        if (root.TryGetProperty("text", out var textProp))
            evt.Text = textProp.GetString();
        if (root.TryGetProperty("toolName", out var tnProp))
            evt.ToolName = tnProp.GetString();
        if (root.TryGetProperty("toolId", out var tiProp))
            evt.ToolId = tiProp.GetString();
        if (root.TryGetProperty("output", out var outProp))
            evt.Output = outProp.GetString();
        if (root.TryGetProperty("isError", out var ieProp))
            evt.IsError = ieProp.GetBoolean();
        if (root.TryGetProperty("message", out var msgProp))
            evt.ErrorMessage = msgProp.GetString();
        if (root.TryGetProperty("usage", out var usageProp))
        {
            if (usageProp.TryGetProperty("inputTokens", out var itProp))
                evt.InputTokens = itProp.GetInt32();
            if (usageProp.TryGetProperty("outputTokens", out var otProp))
                evt.OutputTokens = otProp.GetInt32();
        }

        return evt;
    }

    private void Log(string msg) => OnLog?.Invoke(msg);

    public void Dispose()
    {
        _wsCts?.Cancel();
        _ws?.Dispose();
        _http.Dispose();
        StopServer();
    }
}

// ====================================================================
// 支持类型
// ====================================================================

/// <summary>
/// WebSocket 事件（来自 Python Agent Server 的流式推送）。
/// </summary>
public sealed class AgentEvent
{
    public string Type { get; set; } = "";
    public string? Text { get; set; }
    public string? ToolName { get; set; }
    public string? ToolId { get; set; }
    public string? Output { get; set; }
    public bool IsError { get; set; }
    public string? ErrorMessage { get; set; }
    public int InputTokens { get; set; }
    public int OutputTokens { get; set; }
}

/// <summary>
/// 工具调用记录。
/// </summary>
public sealed class ToolCallRecord
{
    public string ToolName { get; set; }
    public string ToolId { get; set; }
    public string? Output { get; set; }
    public bool IsError { get; set; }

    public ToolCallRecord(string name, string id)
    {
        ToolName = name;
        ToolId = id;
    }
}

/// <summary>
/// 一次对话的结果。
/// </summary>
public sealed class AgentChatResult
{
    public string Text { get; set; } = "";
    public string? Error { get; set; }
    public List<ToolCallRecord> ToolCalls { get; set; } = [];
    public int InputTokens { get; set; }
    public int OutputTokens { get; set; }
}
