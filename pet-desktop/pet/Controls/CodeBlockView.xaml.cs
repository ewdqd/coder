using System.Windows;
using System.Windows.Controls;

namespace pet.Controls;

/// <summary>
/// 代码块展示控件 — 深色背景 + 语法高亮占位 + 一键复制。
/// </summary>
public partial class CodeBlockView : System.Windows.Controls.UserControl
{
    private string _rawCode = "";

    public CodeBlockView()
    {
        InitializeComponent();
    }

    /// <summary>
    /// 设置代码内容和语言标签。
    /// </summary>
    public void SetCode(string code, string language = "")
    {
        _rawCode = code;
        LanguageLabel.Text = string.IsNullOrWhiteSpace(language) ? "code" : language;
        CodeText.Text = code;
    }

    /// <summary>
    /// 设置不带语言标签的代码（自动检测常见语言）。
    /// </summary>
    public void SetCodeAuto(string code)
    {
        _rawCode = code;
        var lang = DetectLanguage(code);
        LanguageLabel.Text = lang;
        CodeText.Text = code;
    }

    private void CopyButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            Clipboard.SetText(_rawCode);
            CopyButton.Content = "✓ Copied!";
            _ = Task.Delay(2000).ContinueWith(_ =>
            {
                Dispatcher.Invoke(() => CopyButton.Content = "📋 Copy");
            });
        }
        catch
        {
            CopyButton.Content = "✗ Failed";
        }
    }

    private static string DetectLanguage(string code)
    {
        var trimmed = code.TrimStart();
        if (trimmed.StartsWith("using ") || trimmed.StartsWith("namespace ") || trimmed.Contains("class "))
            return "C#";
        if (trimmed.StartsWith("import ") || trimmed.StartsWith("from ") || trimmed.StartsWith("def "))
            return "Python";
        if (trimmed.StartsWith("import ") && (trimmed.Contains("java.") || trimmed.Contains("public class")))
            return "Java";
        if (trimmed.StartsWith("package ") || trimmed.StartsWith("func ") || trimmed.StartsWith("type "))
            return "Go";
        if (trimmed.StartsWith("import ") || trimmed.StartsWith("const ") || trimmed.StartsWith("export "))
            return "TypeScript";
        if (trimmed.StartsWith("<?xml") || trimmed.StartsWith("<html") || trimmed.StartsWith("<!DOCTYPE"))
            return "HTML/XML";
        if (trimmed.StartsWith("{") && trimmed.Contains("\""))
            return "JSON";
        if (trimmed.StartsWith("SELECT ") || trimmed.StartsWith("CREATE ") || trimmed.StartsWith("ALTER "))
            return "SQL";
        if (trimmed.StartsWith("#") || trimmed.StartsWith("#!/bin/"))
            return "Shell";
        return "code";
    }
}
