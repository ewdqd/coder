namespace pet.Engine;

/// <summary>
/// 程序员桌面宠物专属动作定义。
/// 扩展 pet 原有的 PetActionCatalog，
/// 为编程场景添加情境化动画和气泡消息。
/// </summary>
public static class CoderActionCatalog
{
    /// <summary>
    /// 根据 Agent 事件类型返回对应的宠物行为和气泡文案。
    /// 调用方通过 MainWindow 播放动画和显示气泡。
    /// </summary>
    public static CoderReaction? GetReaction(CoderEventType eventType)
    {
        var pool = _reactions.GetValueOrDefault(eventType);
        if (pool is not { Count: > 0 }) return null;
        return pool[Random.Shared.Next(pool.Count)];
    }

    /// <summary>
    /// 根据工具名返回反应。
    /// </summary>
    public static CoderReaction? GetToolReaction(string toolName)
    {
        var eventType = toolName switch
        {
            "Bash" => CoderEventType.RunningCommand,
            "ReadFile" => CoderEventType.ReadingCode,
            "WriteFile" or "EditFile" => CoderEventType.WritingCode,
            "Glob" or "Grep" => CoderEventType.SearchingCode,
            _ => CoderEventType.Thinking,
        };
        return GetReaction(eventType);
    }

    // ---- 反应池 ----

    private static readonly Dictionary<CoderEventType, List<CoderReaction>> _reactions = new()
    {
        [CoderEventType.Thinking] =
        [
            new("read", "让我想想… 🤔"),
            new("curious", "这个问题有意思~"),
            new("look_back", "正在分析…"),
            new("tiptoe", "思考中，请稍等…"),
        ],

        [CoderEventType.ReadingCode] =
        [
            new("read", "让我看看这段代码… 📖"),
            new("focus", "正在读代码…"),
            new("curious", "这里写的什么呀？"),
        ],

        [CoderEventType.WritingCode] =
        [
            new("focus", "正在写代码 ✍️"),
            new("music", "敲代码中…"),
            new("point", "这里改一下会更好！"),
        ],

        [CoderEventType.RunningCommand] =
        [
            new("tiptoe", "执行命令中 ⚡"),
            new("jump", "跑起来了！"),
            new("look_back", "等结果中…"),
        ],

        [CoderEventType.SearchingCode] =
        [
            new("curious", "搜一下… 🔍"),
            new("look_back", "找找看在哪里…"),
            new("wave", "正在搜索代码库…"),
        ],

        [CoderEventType.BuildSuccess] =
        [
            new("celebrate", "构建通过！🎉"),
            new("clap", "完美通过！"),
            new("heart", "太棒了！"),
            new("dance", "一切正常~"),
        ],

        [CoderEventType.BuildFailed] =
        [
            new("annoyed", "哎呀，出错了… 😣"),
            new("pout", "构建失败了…"),
            new("shy", "让我看看哪里不对…"),
            new("sad", "别急，我们一起修！"),
        ],

        [CoderEventType.BugFound] =
        [
            new("surprised", "找到一个 bug！🐛"),
            new("point", "这里可能有问题…"),
            new("annoyed", "啧，这里不太对…"),
        ],

        [CoderEventType.DeployStart] =
        [
            new("music", "部署启动！🚀"),
            new("jump", "起飞！"),
            new("wave", "正在部署…"),
        ],

        [CoderEventType.IdleCoding] =
        [
            new("read", "安静陪你写代码…"),
            new("drink", "☕ 喝杯咖啡吧？"),
            new("stretch", "坐久了，动一动？"),
            new("sitre", "默默守护中 💻"),
        ],

        [CoderEventType.GreetingMorning] =
        [
            new("wave", "早上好！今天写什么？☀️"),
            new("stretch", "新的一天，新的代码~"),
            new("delighted", "早安！准备好敲代码了吗？"),
        ],

        [CoderEventType.GreetingNight] =
        [
            new("sleepy", "夜深了，注意休息 🌙"),
            new("yawn", "还在写代码吗…别太累了"),
            new("drowsy", "该休息啦，明天再战~"),
        ],
    };
}

// ====================================================================
// 支持类型
// ====================================================================

/// <summary>
/// 程序员专属事件类型。
/// </summary>
public enum CoderEventType
{
    Thinking,
    ReadingCode,
    WritingCode,
    RunningCommand,
    SearchingCode,
    BuildSuccess,
    BuildFailed,
    BugFound,
    DeployStart,
    IdleCoding,
    GreetingMorning,
    GreetingNight,
}

/// <summary>
/// 反应定义：宠物动作 + 气泡消息。
/// </summary>
public sealed record CoderReaction(string ActionKey, string BubbleMessage);
