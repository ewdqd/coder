using System.Windows;
using System.Windows.Controls;

namespace pet.Controls;

/// <summary>
/// 工具调用卡片 — 可展开查看工具输入/输出。
/// </summary>
public partial class ToolCallCard : System.Windows.Controls.UserControl
{
    private string _output = "";
    private bool _expanded;

    public ToolCallCard()
    {
        InitializeComponent();
    }

    /// <summary>
    /// 设置工具名称和状态图标。
    /// </summary>
    public void SetTool(string toolName)
    {
        ToolNameLabel.Text = toolName;
        ToolIcon.Text = toolName switch
        {
            "Bash" => "⚡",
            "ReadFile" => "📖",
            "WriteFile" => "📝",
            "EditFile" => "✏️",
            "Glob" => "🔍",
            "Grep" => "🔎",
            _ => "🔧",
        };
    }

    /// <summary>
    /// 标记为运行中。
    /// </summary>
    public void MarkRunning()
    {
        StatusLabel.Text = "⏳ Running...";
        StatusLabel.Foreground = new System.Windows.Media.SolidColorBrush(
            System.Windows.Media.Color.FromRgb(0xFF, 0xCC, 0x66));
    }

    /// <summary>
    /// 标记为完成并设置输出内容。
    /// </summary>
    public void MarkCompleted(string output, bool isError)
    {
        _output = output ?? "";
        if (isError)
        {
            StatusLabel.Text = "❌ Error";
            StatusLabel.Foreground = new System.Windows.Media.SolidColorBrush(
                System.Windows.Media.Color.FromRgb(0xFF, 0x66, 0x66));
        }
        else
        {
            StatusLabel.Text = "✅ Done";
            StatusLabel.Foreground = new System.Windows.Media.SolidColorBrush(
                System.Windows.Media.Color.FromRgb(0x66, 0xCC, 0x88));
        }

        OutputText.Text = _output.Length > 2000
            ? _output[..2000] + "\n… (truncated)"
            : _output;

        if (!string.IsNullOrWhiteSpace(_output))
            ExpandButton.Visibility = Visibility.Visible;
    }

    private void ExpandButton_Click(object sender, RoutedEventArgs e)
    {
        _expanded = !_expanded;
        OutputPanel.Visibility = _expanded ? Visibility.Visible : Visibility.Collapsed;
        ExpandButton.Content = _expanded ? "▲" : "▼";
    }
}
