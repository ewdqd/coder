using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using pet.Controls;
using pet.Models;

namespace pet.Services;

/// <summary>
/// 聊天消息渲染助手 — 解析 Markdown 代码块并将其渲染为 CodeBlockView 控件。
/// 用于升级 ChatWindow 支持程序员对话场景（代码高亮、工具调用卡片等）。
/// </summary>
public static class ChatRenderHelper
{
    private static readonly Regex CodeBlockRegex = new(
        @"```(\w*)\s*\n(.*?)```",
        RegexOptions.Singleline | RegexOptions.Compiled);

    private static readonly Regex InlineCodeRegex = new(
        @"`([^`\n]+)`",
        RegexOptions.Compiled);

    /// <summary>
    /// 将包含 Markdown 代码块的文本解析为 WPF Inline 元素列表。
    /// 代码块会被渲染为独立的 CodeBlockView 内嵌控件。
    /// </summary>
    public static List<UIElement> ParseMessage(string text, bool isPet)
    {
        var elements = new List<UIElement>();
        if (string.IsNullOrEmpty(text))
            return elements;

        var matches = CodeBlockRegex.Matches(text);
        var lastIndex = 0;
        var textColor = isPet ? ColorBrush("#222222") : ColorBrush("#333333");
        var codeBgColor = isPet
            ? Color.FromRgb(0x30, 0x30, 0x46)
            : Color.FromRgb(0x1E, 0x1E, 0x2E);

        foreach (Match match in matches)
        {
            // 代码块前的普通文本
            if (match.Index > lastIndex)
            {
                var beforeText = text[lastIndex..match.Index];
                if (!string.IsNullOrWhiteSpace(beforeText))
                {
                    elements.Add(CreateTextBlock(beforeText, textColor));
                }
            }

            // 代码块 → CodeBlockView
            var lang = match.Groups[1].Value.Trim();
            var code = match.Groups[2].Value.TrimEnd();
            var codeView = new CodeBlockView();
            codeView.SetCode(code, lang);
            elements.Add(codeView);

            lastIndex = match.Index + match.Length;
        }

        // 剩余文本
        if (lastIndex < text.Length)
        {
            var afterText = text[lastIndex..];
            if (!string.IsNullOrWhiteSpace(afterText))
            {
                elements.Add(CreateTextBlock(afterText, textColor));
            }
        }

        return elements;
    }

    /// <summary>
    /// 从文本中提取所有代码块（用于快速预览）。
    /// </summary>
    public static List<(string Language, string Code)> ExtractCodeBlocks(string text)
    {
        var blocks = new List<(string, string)>();
        var matches = CodeBlockRegex.Matches(text);
        foreach (Match match in matches)
        {
            blocks.Add((match.Groups[1].Value.Trim(), match.Groups[2].Value.TrimEnd()));
        }
        return blocks;
    }

    /// <summary>
    /// 为 ChatPanel 创建一个包含代码块的消息气泡容器。
    /// </summary>
    public static Border CreateMessageBubble(
        string senderName,
        string message,
        bool isPet,
        PetSettings settings)
    {
        var container = new StackPanel { Margin = new Thickness(0, 4, 0, 8) };

        // 发送者名字
        var nameLabel = new TextBlock
        {
            Text = senderName,
            FontSize = 11.5,
            Foreground = ColorBrush("#888888"),
            Margin = new Thickness(4, 0, 0, 3),
        };
        container.Children.Add(nameLabel);

        // 解析消息内容
        var hasCodeBlocks = CodeBlockRegex.IsMatch(message);
        if (!hasCodeBlocks)
        {
            // 无代码块 → 普通文本气泡
            container.Children.Add(new TextBlock
            {
                Text = message,
                FontSize = 13.5,
                Foreground = isPet ? ColorBrush("#222222") : ColorBrush("#333333"),
                TextWrapping = TextWrapping.Wrap,
                LineHeight = 20,
            });
        }
        else
        {
            // 有代码块 → 逐段解析
            var elements = ParseMessage(message, isPet);
            foreach (var el in elements)
                container.Children.Add(el);
        }

        // 气泡容器
        var bgColor = isPet ? "#FFEEF5" : "#F5F5F5";
        var bubble = new Border
        {
            Background = ColorBrush(bgColor),
            CornerRadius = new CornerRadius(10),
            Padding = new Thickness(12, 8, 12, 8),
            MaxWidth = 520,
            HorizontalAlignment = isPet ? HorizontalAlignment.Left : HorizontalAlignment.Right,
            Child = container,
        };

        return bubble;
    }

    /// <summary>
    /// 为 ChatPanel 创建工具调用记录行。
    /// </summary>
    public static ToolCallCard CreateToolCallCard(
        string toolName, string? output = null, bool isError = false)
    {
        var card = new ToolCallCard();
        card.SetTool(toolName);

        if (output != null)
            card.MarkCompleted(output, isError);
        else
            card.MarkRunning();

        return card;
    }

    // ---- 辅助方法 ----

    private static TextBlock CreateTextBlock(string text, System.Windows.Media.Brush color)
    {
        return new TextBlock
        {
            Text = text,
            FontSize = 13.5,
            Foreground = color,
            TextWrapping = TextWrapping.Wrap,
            LineHeight = 20,
        };
    }

    private static SolidColorBrush ColorBrush(string hex) =>
        (SolidColorBrush)new BrushConverter().ConvertFrom(hex)!;
}
