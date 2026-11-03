using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Microsoft.Win32;
using Forms = System.Windows.Forms;

internal sealed class InstallerWindow : Window
{
    private readonly InstallTarget target;
    private readonly StackPanel options;
    private readonly TextBlock pathLabel, status;
    private readonly Button install, close, details;
    private readonly ProgressBar progress;
    private bool busy, completed;

    public InstallerWindow(InstallTarget installTarget)
    {
        target = installTarget;
        Title = "GeneLoop Desktop 安装";
        Width = 548;
        SizeToContent = SizeToContent.Height;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        WindowStyle = WindowStyle.None;
        ResizeMode = ResizeMode.NoResize;
        Background = Brush("#FCFCFF");
        FontFamily = new FontFamily("Segoe UI, Microsoft YaHei UI");
        TextOptions.SetTextFormattingMode(this, TextFormattingMode.Display);
        Foreground = Brush("#192232");
        Closing += delegate(object sender, CancelEventArgs args) { args.Cancel = busy; };

        var shell = new StackPanel { Margin = new Thickness(24) };
        Content = new Border { Background = Background, BorderBrush = Brush("#DFE4EF"), BorderThickness = new Thickness(1), Child = shell };
        close = MakeButton("×", false);
        close.Width = 34;
        close.HorizontalAlignment = HorizontalAlignment.Right;
        AutomationPropertiesSetName(close, "关闭安装器");
        close.Click += delegate { Close(); };
        shell.Children.Add(close);
        var hero = new StackPanel { Margin = new Thickness(20, 18, 20, 20) };
        var gradient = new LinearGradientBrush(ColorFrom("#EDE9FF"), ColorFrom("#E3F7F5"), 28);
        shell.Children.Add(new Border { Background = gradient, CornerRadius = new CornerRadius(20), Child = hero });
        var logo = new BitmapImage();
        using (var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("GeneLoop.Brand"))
        {
            logo.BeginInit(); logo.StreamSource = resource; logo.CacheOption = BitmapCacheOption.OnLoad; logo.EndInit();
        }
        hero.Children.Add(new Image { Source = logo, Width = 64, Height = 64, HorizontalAlignment = HorizontalAlignment.Center });
        hero.Children.Add(Text("GeneLoop Desktop", 25, "#192232", true));
        hero.Children.Add(Text("让研究，向前一步。", 13, "#495B71", false));
        install = MakeButton("立即安装", true);
        install.Width = 222;
        install.Margin = new Thickness(0, 22, 0, 4);
        install.IsDefault = true;
        install.HorizontalAlignment = HorizontalAlignment.Center;
        install.Click += async delegate { await RunInstallation(); };
        shell.Children.Add(install);
        status = Text("", 12, "#526277", false);
        status.Margin = new Thickness(8, 8, 8, 4);
        shell.Children.Add(status);
        progress = new ProgressBar { Height = 4, Margin = new Thickness(32, 5, 32, 8), Foreground = Brush("#3265CB"), Visibility = Visibility.Collapsed };
        shell.Children.Add(progress);
        details = MakeButton("安装位置  ▾", false);
        details.HorizontalAlignment = HorizontalAlignment.Center;
        shell.Children.Add(details);
        options = new StackPanel { Margin = new Thickness(12), Visibility = Visibility.Collapsed };
        shell.Children.Add(new Border { Background = Brush("#F1F4FA"), CornerRadius = new CornerRadius(10), Child = options });
        pathLabel = Text(target.Path, 12, "#263850", false);
        pathLabel.TextAlignment = TextAlignment.Left;
        options.Children.Add(pathLabel);
        options.Children.Add(Text(target.Machine ? "为所有 Windows 用户安装" : "仅为当前 Windows 用户安装", 11, "#526277", false));
        var browse = MakeButton("更改位置…", false);
        browse.HorizontalAlignment = HorizontalAlignment.Left;
        browse.Click += delegate { ChooseFolder(); };
        options.Children.Add(browse);
        details.Click += delegate
        {
            bool open = options.Visibility != Visibility.Visible;
            options.Visibility = open ? Visibility.Visible : Visibility.Collapsed;
            details.Content = open ? "安装位置  ▴" : "安装位置  ▾";
        };
    }

    private void ChooseFolder()
    {
        using (var dialog = new Forms.FolderBrowserDialog())
        {
            dialog.Description = "选择安装位置，GeneLoop Desktop 将放在独立文件夹中";
            if (Directory.Exists(target.Path)) dialog.SelectedPath = target.Path;
            if (dialog.ShowDialog() != Forms.DialogResult.OK) return;
            string root = Path.GetFullPath(dialog.SelectedPath).TrimEnd(Path.DirectorySeparatorChar);
            if (String.Equals(root, target.Path.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase))
                return;
            target.Path = String.Equals(Path.GetFileName(root), "GeneLoop Desktop", StringComparison.OrdinalIgnoreCase)
                ? root : Path.Combine(root + Path.DirectorySeparatorChar, "GeneLoop Desktop");
            pathLabel.Text = target.Path;
        }
    }

    internal void VerifyLocationControls()
    {
        details.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        if (options.Visibility != Visibility.Visible || pathLabel.Text != target.Path ||
            !(options.Children[options.Children.Count - 1] is Button) ||
            !Object.Equals(install.Content, "立即安装"))
            throw new InvalidOperationException("安装位置选项未能展开。");
    }

    private async Task RunInstallation()
    {
        if (completed) { Close(); return; }
        busy = true;
        install.IsEnabled = close.IsEnabled = details.IsEnabled = false;
        options.Visibility = Visibility.Collapsed;
        details.Content = "安装位置  ▾";
        install.Content = "正在安装…";
        status.Text = target.Machine ? "如果 Windows 请求管理员权限，请在系统提示中确认。" : "正在准备安装文件…";
        progress.Visibility = Visibility.Visible;
        progress.IsIndeterminate = true;
        try
        {
            int result = await Task.Run(() => InstallEngine.Run(target, null));
            if (result == 1618) throw new InvalidOperationException("GeneLoop Desktop 仍在运行，请从托盘退出后重试。");
            if (result != 0) throw new InvalidOperationException("安装未完成，错误代码 " + result + "。");
            var installed = Path.Combine(target.Path, "GeneLoop Desktop.exe");
            var expected = (AssemblyInformationalVersionAttribute)Attribute.GetCustomAttribute(
                Assembly.GetExecutingAssembly(), typeof(AssemblyInformationalVersionAttribute));
            if (!File.Exists(installed) || FileVersionInfo.GetVersionInfo(installed).FileVersion != expected.InformationalVersion)
                throw new InvalidOperationException("未能确认所选位置已安装此次版本。");
            completed = true;
            install.Content = "完成";
            status.Text = "GeneLoop Desktop 已安装。";
        }
        catch (Win32Exception error)
        {
            status.Text = error.NativeErrorCode == 1223 ? "已取消管理员授权，可以重新开始。" : "无法启动安装程序（" + error.NativeErrorCode + "）。";
        }
        catch (Exception error) { status.Text = error.Message; }
        finally
        {
            busy = false;
            progress.IsIndeterminate = false;
            progress.Visibility = Visibility.Collapsed;
            install.IsEnabled = close.IsEnabled = true;
            details.IsEnabled = !completed;
            if (!completed) install.Content = "重试";
        }
    }

    private static Color ColorFrom(string hex) { return (Color)ColorConverter.ConvertFromString(hex); }
    private static SolidColorBrush Brush(string hex) { return new SolidColorBrush(ColorFrom(hex)); }
    private static void AutomationPropertiesSetName(Button button, string name) { System.Windows.Automation.AutomationProperties.SetName(button, name); }
    private static TextBlock Text(string value, double size, string color, bool heading)
    {
        return new TextBlock { Text = value, FontSize = size, Foreground = Brush(color), TextWrapping = TextWrapping.Wrap,
            TextAlignment = TextAlignment.Center, FontWeight = heading ? FontWeights.SemiBold : FontWeights.Normal };
    }
    private static Button MakeButton(string label, bool primary)
    {
        var body = new FrameworkElementFactory(typeof(Border));
        body.SetValue(Border.CornerRadiusProperty, new CornerRadius(primary ? 20 : 8));
        body.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(Control.BackgroundProperty));
        var content = new FrameworkElementFactory(typeof(ContentPresenter));
        content.SetValue(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Center);
        content.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center);
        body.AppendChild(content);
        var template = new ControlTemplate(typeof(Button)) { VisualTree = body };
        var hover = new Trigger { Property = UIElement.IsMouseOverProperty, Value = true };
        hover.Setters.Add(new Setter(Control.BackgroundProperty, Brush(primary ? "#2254B5" : "#EBEFF8")));
        template.Triggers.Add(hover);
        var disabled = new Trigger { Property = UIElement.IsEnabledProperty, Value = false };
        disabled.Setters.Add(new Setter(UIElement.OpacityProperty, .58));
        template.Triggers.Add(disabled);
        return new Button { Content = label, Template = template, Height = primary ? 44 : 32, Cursor = System.Windows.Input.Cursors.Hand,
            Background = Brush(primary ? "#3265CB" : "#FCFCFF"), Foreground = Brush(primary ? "#FFFFFF" : "#31425D"),
            FontSize = primary ? 15 : 13 };
    }
}

internal sealed class InstallTarget
{
    private const string RegistryKey = @"Software\df43dd29-397e-5d1c-b2f3-fe84b0ec1dc1";
    public string Path;
    public bool Machine;

    private static string ExistingPath(RegistryHive hive)
    {
        using (var root = RegistryKeyOpen(hive))
        using (var key = root.OpenSubKey(RegistryKey))
            return key == null ? null : key.GetValue("InstallLocation") as string;
    }
    private static Microsoft.Win32.RegistryKey RegistryKeyOpen(RegistryHive hive)
    {
        return Microsoft.Win32.RegistryKey.OpenBaseKey(hive, RegistryView.Registry64);
    }
    public static InstallTarget Detect()
    {
        var user = ExistingPath(RegistryHive.CurrentUser);
        if (!String.IsNullOrWhiteSpace(user)) return new InstallTarget { Path = user };
        var machine = ExistingPath(RegistryHive.LocalMachine);
        if (!String.IsNullOrWhiteSpace(machine)) return new InstallTarget { Machine = true, Path = machine };
        return new InstallTarget { Path = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "GeneLoop Desktop") };
    }
}

internal static class InstallEngine
{
    public static int Run(InstallTarget target, string arguments)
    {
        string directory = Path.Combine(Path.GetTempPath(), "GeneLoop-Setup-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        string engine = Path.Combine(directory, "GeneLoop-Engine.exe");
        try
        {
            using (var embedded = Assembly.GetExecutingAssembly().GetManifestResourceStream("GeneLoop.InstallEngine"))
            using (var output = new FileStream(engine, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                embedded.CopyTo(output);
            string flags = arguments ?? ("/S " + (target.Machine ? "/allusers" : "/currentuser") + " /D=" + target.Path);
            bool elevate = arguments == null ? target.Machine :
                flags.IndexOf("/allusers", StringComparison.OrdinalIgnoreCase) >= 0 ||
                (target.Machine && flags.IndexOf("/currentuser", StringComparison.OrdinalIgnoreCase) < 0);
            using (var lockFile = new FileStream(engine, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (var process = Process.Start(new ProcessStartInfo(engine, flags) { UseShellExecute = true, Verb = elevate ? "runas" : "" }))
            {
                process.WaitForExit();
                return process.ExitCode;
            }
        }
        finally
        {
            try { File.Delete(engine); Directory.Delete(directory); } catch (IOException) { } catch (UnauthorizedAccessException) { }
        }
    }

    [STAThread]
    public static int Main(string[] args)
    {
        try
        {
            var target = InstallTarget.Detect();
            if (args.Length <= 2 && args.Length > 0 && args[0] == "--check-ui")
            {
                var check = new InstallerWindow(target);
                check.VerifyLocationControls();
                var fresh = new InstallerWindow(new InstallTarget { Path = @"C:\Programs\GeneLoop Desktop" });
                fresh.VerifyLocationControls();
                fresh.Close();
                if (args.Length == 2)
                {
                    var content = (FrameworkElement)check.Content;
                    content.Measure(new Size(check.Width, Double.PositiveInfinity));
                    content.Arrange(new Rect(0, 0, check.Width, content.DesiredSize.Height));
                    var bitmap = new RenderTargetBitmap((int)Math.Ceiling(content.ActualWidth),
                        (int)Math.Ceiling(content.ActualHeight), 96, 96, PixelFormats.Pbgra32);
                    bitmap.Render(content);
                    var png = new PngBitmapEncoder();
                    png.Frames.Add(BitmapFrame.Create(bitmap));
                    using (var stream = File.Create(args[1])) png.Save(stream);
                }
                check.Close();
                return 0;
            }
            if (args.Length > 0)
            {
                string raw = Environment.CommandLine;
                int end = raw[0] == '"' ? raw.IndexOf('"', 1) + 1 : raw.IndexOf(' ');
                return Run(target, raw.Substring(end).TrimStart());
            }
            new Application().Run(new InstallerWindow(target));
            return 0;
        }
        catch (Win32Exception error) { return error.NativeErrorCode; }
        catch { return 1; }
    }
}
