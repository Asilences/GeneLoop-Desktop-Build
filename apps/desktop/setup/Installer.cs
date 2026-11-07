using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Security.Principal;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Microsoft.Win32;
using Forms = System.Windows.Forms;

internal sealed class InstallerWindow : Window
{
    private readonly InstallTarget target;
    private readonly StackPanel options;
    private readonly TextBlock pathLabel, status;
    private readonly Button install, close, details, browse;
    private readonly CheckBox openApp;
    private readonly ProgressBar progress;
    private bool busy, completed;
    private readonly bool returnLaunchToParent;
    public bool LaunchRequested { get; private set; }
    private bool ShouldOpenApp { get { return completed && openApp.IsChecked == true; } }

    public InstallerWindow(InstallTarget installTarget, bool launchFromParent = false)
    {
        target = installTarget;
        returnLaunchToParent = launchFromParent;
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

        var shell = new StackPanel();
        Content = new Border { Background = Background, BorderBrush = Brush("#DFE4EF"), BorderThickness = new Thickness(1), Child = shell };
        close = MakeButton("×", false);
        close.Width = 34;
        close.Margin = new Thickness(0, 12, 18, 0);
        close.HorizontalAlignment = HorizontalAlignment.Right;
        AutomationPropertiesSetName(close, "关闭安装器");
        close.Click += delegate { Close(); };
        shell.Children.Add(close);
        var hero = new StackPanel { Margin = new Thickness(20, 18, 20, 20) };
        var gradient = new LinearGradientBrush(ColorFrom("#EDE9FF"), ColorFrom("#E3F7F5"), 28);
        shell.Children.Add(new Border { Margin = new Thickness(24, 0, 24, 0), Background = gradient, CornerRadius = new CornerRadius(20), Child = hero });
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
        openApp = new CheckBox { Content = "打开 GeneLoop Desktop", IsChecked = true, Visibility = Visibility.Collapsed,
            HorizontalAlignment = HorizontalAlignment.Center, Margin = new Thickness(0, 7, 0, 14), Foreground = Brush("#31425D") };
        shell.Children.Add(openApp);
        progress = new ProgressBar { Height = 4, Margin = new Thickness(32, 5, 32, 8), Foreground = Brush("#3265CB"), Visibility = Visibility.Collapsed };
        shell.Children.Add(progress);
        details = MakeButton("自定义设置  ▾", false);
        details.Width = 112;
        details.Margin = new Thickness(0, 0, 24, 9);
        details.HorizontalAlignment = HorizontalAlignment.Right;
        shell.Children.Add(details);
        options = new StackPanel { Visibility = Visibility.Collapsed };
        var settingsArea = new Border { Background = Brush("#F3F5FA"), BorderBrush = Brush("#E2E7F0"),
            BorderThickness = new Thickness(0, 1, 0, 0), Padding = new Thickness(30, 18, 30, 18), Child = options,
            Visibility = Visibility.Collapsed };
        shell.Children.Add(settingsArea);
        var location = new Grid();
        location.ColumnDefinitions.Add(new ColumnDefinition());
        location.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        options.Children.Add(location);
        pathLabel = Text(target.Path, 12, "#263850", false);
        pathLabel.TextAlignment = TextAlignment.Left;
        pathLabel.TextWrapping = TextWrapping.NoWrap;
        pathLabel.TextTrimming = TextTrimming.CharacterEllipsis;
        pathLabel.VerticalAlignment = VerticalAlignment.Center;
        pathLabel.ToolTip = target.Path;
        location.Children.Add(new Border { Background = Brush("#FFFFFF"), BorderBrush = Brush("#DCE3EF"),
            BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(16), Padding = new Thickness(12, 0, 12, 0), Child = pathLabel });
        browse = MakeButton("更改位置", false);
        browse.Width = 78;
        browse.Margin = new Thickness(8, 0, 0, 0);
        browse.Background = Brush("#F3F5FA");
        browse.Foreground = Brush("#285CB5");
        Grid.SetColumn(browse, 1);
        browse.Click += delegate { ChooseFolder(); };
        location.Children.Add(browse);
        RefreshLocation();
        details.Click += delegate
        {
            bool open = options.Visibility != Visibility.Visible;
            options.Visibility = open ? Visibility.Visible : Visibility.Collapsed;
            settingsArea.Visibility = options.Visibility;
            details.Content = open ? "自定义设置  ▴" : "自定义设置  ▾";
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
            RefreshLocation();
        }
    }

    private void RefreshLocation()
    {
        pathLabel.Text = target.Path;
        pathLabel.ToolTip = target.Path;
    }

    internal void VerifyLocationControls()
    {
        details.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        if (options.Visibility != Visibility.Visible || pathLabel.Text != target.Path ||
            !(browse.Parent is Grid) || Grid.GetColumn(browse) != 1 ||
            !Object.Equals(install.Content, "立即安装"))
            throw new InvalidOperationException("安装位置选项未能展开。");
    }

    private void ShowCompletion()
    {
        if (options.Visibility == Visibility.Visible) details.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        completed = true;
        install.Content = "完成";
        status.Text = "GeneLoop Desktop 已安装。";
        openApp.Visibility = Visibility.Visible;
        details.Visibility = Visibility.Collapsed;
    }

    internal void VerifyCompletionControls(bool launch)
    {
        ShowCompletion();
        if (openApp.Visibility != Visibility.Visible || openApp.IsChecked != true ||
            !Object.Equals(install.Content, "完成"))
            throw new InvalidOperationException("安装完成选项未正确显示。");
        openApp.IsChecked = launch;
        if (ShouldOpenApp != launch) throw new InvalidOperationException("启动选项未正确生效。");
    }

    private async Task RunInstallation()
    {
        if (completed)
        {
            if (ShouldOpenApp)
            {
                if (returnLaunchToParent) LaunchRequested = true;
                else
                {
                    try { InstallEngine.OpenApp(target); }
                    catch { status.Text = "GeneLoop Desktop 已安装，请从开始菜单打开。"; openApp.IsChecked = false; return; }
                }
            }
            Close();
            return;
        }
        busy = true;
        install.IsEnabled = close.IsEnabled = details.IsEnabled = false;
        if (options.Visibility == Visibility.Visible) details.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        install.Content = "正在安装…";
        string phase = "正在准备安装文件";
        var elapsed = Stopwatch.StartNew();
        Action updateStatus = () =>
        {
            var seconds = (int)elapsed.Elapsed.TotalSeconds;
            status.Text = seconds < 60 ? phase + "…" :
                phase + " · 已用 " + (seconds / 60) + " 分 " + (seconds % 60) + " 秒";
        };
        var clock = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        clock.Tick += delegate { updateStatus(); };
        var phases = new Progress<string>(value =>
        {
            if (!busy || completed) return;
            phase = value;
            updateStatus();
        });
        updateStatus();
        clock.Start();
        progress.Visibility = Visibility.Visible;
        progress.IsIndeterminate = true;
        try
        {
            int result = await Task.Run(() => InstallEngine.Run(target, null, phases));
            if (result == 1618) throw new InvalidOperationException("GeneLoop Desktop 仍在运行，请从托盘退出后重试。");
            if (result != 0) throw new InvalidOperationException("安装未完成，错误代码 " + result + "。");
            var installed = Path.Combine(target.Path, "GeneLoop Desktop.exe");
            var expected = (AssemblyInformationalVersionAttribute)Attribute.GetCustomAttribute(
                Assembly.GetExecutingAssembly(), typeof(AssemblyInformationalVersionAttribute));
            if (!File.Exists(installed) || FileVersionInfo.GetVersionInfo(installed).FileVersion != expected.InformationalVersion)
                throw new InvalidOperationException("未能确认所选位置已安装此次版本。");
            ShowCompletion();
        }
        catch (Win32Exception error)
        {
            status.Text = error.NativeErrorCode == 1223 ? "已取消管理员授权，可以重新开始。" : "无法启动安装程序（" + error.NativeErrorCode + "）。";
        }
        catch (Exception error) { status.Text = error.Message; }
        finally
        {
            clock.Stop();
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
        var body = new FrameworkElementFactory(typeof(Border), "ButtonChrome");
        body.SetValue(Border.CornerRadiusProperty, new CornerRadius(primary ? 20 : 8));
        body.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(Control.BackgroundProperty));
        var content = new FrameworkElementFactory(typeof(ContentPresenter));
        content.SetValue(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Center);
        content.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center);
        body.AppendChild(content);
        var template = new ControlTemplate(typeof(Button)) { VisualTree = body };
        var hover = new Trigger { Property = UIElement.IsMouseOverProperty, Value = true };
        hover.Setters.Add(new Setter(Border.BackgroundProperty, Brush(primary ? "#2254B5" : "#EBEFF8"), "ButtonChrome"));
        template.Triggers.Add(hover);
        var disabled = new Trigger { Property = UIElement.IsEnabledProperty, Value = false };
        disabled.Setters.Add(new Setter(UIElement.OpacityProperty, .58));
        template.Triggers.Add(disabled);
        var focus = new Trigger { Property = UIElement.IsKeyboardFocusedProperty, Value = true };
        focus.Setters.Add(new Setter(Border.BackgroundProperty, Brush(primary ? "#2254B5" : "#E5ECFA"), "ButtonChrome"));
        template.Triggers.Add(focus);
        return new Button { Content = label, Template = template, FocusVisualStyle = null, Height = primary ? 44 : 32, Cursor = System.Windows.Input.Cursors.Hand,
            Background = Brush(primary ? "#3265CB" : "#FCFCFF"), Foreground = Brush(primary ? "#FFFFFF" : "#31425D"),
            FontSize = primary ? 15 : 13 };
    }
}

internal sealed class InstallTarget
{
    private const string RegistryKey = @"Software\df43dd29-397e-5d1c-b2f3-fe84b0ec1dc1";
    public string Path;
    public string OriginalPath;
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
    public static InstallTarget Detect(bool machineOnly = false)
    {
        var user = machineOnly ? null : ExistingPath(RegistryHive.CurrentUser);
        if (!String.IsNullOrWhiteSpace(user)) return new InstallTarget { Path = user, OriginalPath = user };
        var machine = ExistingPath(RegistryHive.LocalMachine);
        if (!String.IsNullOrWhiteSpace(machine)) return new InstallTarget { Machine = true, Path = machine, OriginalPath = machine };
        if (machineOnly) throw new InvalidOperationException("找不到原有的所有用户安装。");
        return new InstallTarget { Path = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "GeneLoop Desktop") };
    }
}

internal static class InstallEngine
{
    private const int LaunchAfterInstall = 42;

    private static bool IsElevated()
    {
        using (var identity = WindowsIdentity.GetCurrent())
            return new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator);
    }

    internal static void OpenApp(InstallTarget target)
    {
        var path = Path.Combine(target.Path, "GeneLoop Desktop.exe");
        if (!IsElevated())
        {
            Process.Start(new ProcessStartInfo(path) { UseShellExecute = true, WorkingDirectory = target.Path });
            return;
        }
        // Use the existing desktop shell so the app does not inherit the setup token.
        dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("Shell.Application"));
        object location = 0, empty = null;
        int handle;
        dynamic desktop = shell.Windows().FindWindowSW(ref location, ref empty, 8, out handle, 1);
        desktop.Document.Application.ShellExecute(path, "", target.Path, "open", 1);
    }

    public static int Run(InstallTarget target, string arguments, IProgress<string> phases = null)
    {
        string flags = arguments ?? ("/S " + (target.Machine ? "/allusers" : "/currentuser") + " /D=" + target.Path);
        bool elevate = flags.IndexOf("/allusers", StringComparison.OrdinalIgnoreCase) >= 0 ||
            (target.Machine && flags.IndexOf("/currentuser", StringComparison.OrdinalIgnoreCase) < 0);
        if (elevate && !IsElevated())
        {
            using (var elevated = Process.Start(new ProcessStartInfo(Assembly.GetExecutingAssembly().Location, flags) { UseShellExecute = true, Verb = "runas" }))
            { elevated.WaitForExit(); return elevated.ExitCode; }
        }
        // Both the UI and silent entry points share the same update lock.
        using (var installLock = new System.Threading.Mutex(false, @"Local\GeneLoop-Desktop-Install-df43dd29"))
        {
            bool acquired = false;
            try
            {
                try { acquired = installLock.WaitOne(0); }
                catch (System.Threading.AbandonedMutexException) { acquired = true; }
                if (!acquired) throw new IOException("另一个 GeneLoop 安装器正在运行。");
                return RunLocked(target, flags, phases);
            }
            finally { if (acquired) installLock.ReleaseMutex(); }
        }
    }

    private static int RunLocked(InstallTarget target, string arguments, IProgress<string> phases)
    {
        string flags = arguments ?? ("/S " + (target.Machine ? "/allusers" : "/currentuser") + " /D=" + target.Path);
        bool elevate = flags.IndexOf("/allusers", StringComparison.OrdinalIgnoreCase) >= 0 ||
            (target.Machine && flags.IndexOf("/currentuser", StringComparison.OrdinalIgnoreCase) < 0);
        int destination = flags.IndexOf("/D=", StringComparison.OrdinalIgnoreCase);
        if (destination >= 0) target.Path = Path.GetFullPath(flags.Substring(destination + 3).Trim().Trim('"'));
        string stageName = ".GeneLoop-Setup-" + Guid.NewGuid().ToString("N");
        string stageParent = Path.GetDirectoryName(Path.GetFullPath(String.IsNullOrWhiteSpace(target.OriginalPath) ? target.Path : target.OriginalPath));
        // NSIS un.atomicRMDir moves old files into its own PLUGINSDIR for
        // rollback. Putting TEMP on C: when the old install is on D: turns
        // every Rename into a cross-volume copy followed by deletion.
        string directory = Path.Combine(stageParent, stageName);
        Directory.CreateDirectory(directory);
        InstallTransaction.SecureStage(directory);
        if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0) throw new IOException("安装临时目录包含链接");
        string stageMarker = Path.Combine(directory, ".geneloop-install-stage");
        using (var marker = new FileStream(stageMarker, FileMode.CreateNew, FileAccess.Write, FileShare.None)) { }
        string engine = Path.Combine(directory, "GeneLoop-Engine.exe");
        string trace = Path.Combine(Path.GetTempPath(), "GeneLoop-install-" + Guid.NewGuid().ToString("N") + ".jsonl");
        string previousTrace = Environment.GetEnvironmentVariable("GENELOOP_INSTALL_TRACE");
        string previousReuse = Environment.GetEnvironmentVariable("GENELOOP_INSTALL_PREVIOUS"), previousJournal = Environment.GetEnvironmentVariable("GENELOOP_INSTALL_REUSE_JOURNAL");
        string previousTemp = Environment.GetEnvironmentVariable("TEMP"), previousTmp = Environment.GetEnvironmentVariable("TMP");
        var timing = Stopwatch.StartNew();
        Action<string> record = phase => { try { File.AppendAllText(trace, "{\"phase\":\"" + phase + "\",\"parent_elapsed_ms\":" + timing.ElapsedMilliseconds + "}\n"); } catch { } };
        InstallTransaction transaction = null;
        try
        {
            record("installer_start");
            Environment.SetEnvironmentVariable("TEMP", directory);
            Environment.SetEnvironmentVariable("TMP", directory);
            record("same_volume_staging");
            using (var embedded = Assembly.GetExecutingAssembly().GetManifestResourceStream("GeneLoop.InstallEngine"))
            using (var output = new FileStream(engine, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                embedded.CopyTo(output);
            record("engine_released");
            Environment.SetEnvironmentVariable("GENELOOP_INSTALL_TRACE", trace);
            Environment.SetEnvironmentVariable("GENELOOP_INSTALL_PREVIOUS", null);
            Environment.SetEnvironmentVariable("GENELOOP_INSTALL_REUSE_JOURNAL", null);
            if (!String.IsNullOrWhiteSpace(target.OriginalPath))
            {
                transaction = new InstallTransaction(target.OriginalPath, target.Path, directory, record);
                transaction.Prepare(true, elevate);
                Environment.SetEnvironmentVariable("GENELOOP_INSTALL_PREVIOUS", transaction.PreviousDirectory);
                Environment.SetEnvironmentVariable("GENELOOP_INSTALL_REUSE_JOURNAL", transaction.ReuseJournal);
            }
            using (var lockFile = new FileStream(engine, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (var process = Process.Start(new ProcessStartInfo(engine, flags) { UseShellExecute = true, Verb = elevate && !IsElevated() ? "runas" : "" }))
            {
                if (phases != null) phases.Report("正在解压并写入安装目录");
                process.WaitForExit();
                record("engine_finished");
                if (process.ExitCode == 0)
                {
                    var expected = (AssemblyInformationalVersionAttribute)Attribute.GetCustomAttribute(Assembly.GetExecutingAssembly(), typeof(AssemblyInformationalVersionAttribute));
                    var installed = Path.Combine(target.Path, "GeneLoop Desktop.exe");
                    if (!File.Exists(installed) || FileVersionInfo.GetVersionInfo(installed).FileVersion != expected.InformationalVersion)
                        throw new IOException("新版本完整性确认失败，正在恢复旧版本。");
                    if (transaction != null) transaction.Commit();
                }
                return process.ExitCode;
            }
        }
        finally
        {
            Environment.SetEnvironmentVariable("GENELOOP_INSTALL_TRACE", previousTrace);
            Environment.SetEnvironmentVariable("GENELOOP_INSTALL_PREVIOUS", previousReuse);
            Environment.SetEnvironmentVariable("GENELOOP_INSTALL_REUSE_JOURNAL", previousJournal);
            Environment.SetEnvironmentVariable("TEMP", previousTemp);
            Environment.SetEnvironmentVariable("TMP", previousTmp);
            try { if (transaction != null) transaction.Dispose(); }
            catch { record("rollback_requires_recovery"); }
            try {
                if (Path.GetDirectoryName(Path.GetFullPath(directory)) == stageParent && Path.GetFileName(directory) == stageName &&
                    File.Exists(stageMarker) && (File.GetAttributes(directory) & FileAttributes.ReparsePoint) == 0 &&
                    (transaction == null || !transaction.RecoveryRequired))
                    Directory.Delete(directory, true);
            } catch (IOException) { } catch (UnauthorizedAccessException) { }
            record("installer_cleanup_complete");
        }
    }

    [STAThread]
    public static int Main(string[] args)
    {
        try
        {
            bool elevatedUi = args.Length == 1 && args[0] == "--elevated-ui";
            if (elevatedUi && !IsElevated()) return 740;
            var target = InstallTarget.Detect(elevatedUi);
            if (args.Length <= 2 && args.Length > 0 && args[0] == "--check-ui")
            {
                var check = new InstallerWindow(target, true);
                check.VerifyLocationControls();
                var fresh = new InstallerWindow(new InstallTarget { Path = @"C:\Programs\GeneLoop Desktop" }, true);
                fresh.VerifyLocationControls();
                check.VerifyCompletionControls(true);
                fresh.VerifyCompletionControls(false);
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
                fresh.Close();
                return 0;
            }
            if (args.Length > 0 && !elevatedUi)
            {
                string raw = Environment.CommandLine;
                int end = raw[0] == '"' ? raw.IndexOf('"', 1) + 1 : raw.IndexOf(' ');
                return Run(target, raw.Substring(end).TrimStart());
            }
            if (target.Machine && !IsElevated())
            {
                var setup = Assembly.GetExecutingAssembly().Location;
                using (var elevated = Process.Start(new ProcessStartInfo(setup, "--elevated-ui") { UseShellExecute = true, Verb = "runas" }))
                {
                    elevated.WaitForExit();
                    if (elevated.ExitCode != LaunchAfterInstall) return elevated.ExitCode;
                    try { OpenApp(InstallTarget.Detect(true)); }
                    catch { MessageBox.Show("GeneLoop Desktop 已安装，请从开始菜单打开。", "GeneLoop Desktop"); }
                    return 0;
                }
            }
            var window = new InstallerWindow(target, elevatedUi);
            new Application().Run(window);
            return window.LaunchRequested ? LaunchAfterInstall : 0;
        }
        catch (Win32Exception error) { return error.NativeErrorCode; }
        catch { return 1; }
    }
}
