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
using System.Windows.Threading;
using Forms = System.Windows.Forms;

// Native WPF composition, inspired by Fluent/ModernWpf and WixSharp's managed
// bootstrapper separation. No extra UI runtime or webview is installed.
internal sealed class InstallerWindow : Window
{
    private readonly InstallTarget target;
    private readonly StackPanel options;
    private readonly TextBlock pathLabel, status, heading;
    private readonly Button install, close, details, browse;
    private readonly CheckBox openApp, shortcut;
    private readonly ProgressBar progress;
    private readonly Border optionsArea;
    private bool busy, completed;
    private readonly bool returnLaunchToParent;
    public bool LaunchRequested { get; private set; }
    private bool ShouldOpenApp { get { return completed && openApp.IsChecked == true; } }

    public InstallerWindow(InstallTarget installTarget, bool launchFromParent = false)
    {
        target = installTarget; returnLaunchToParent = launchFromParent;
        Title = "GeneLoop Desktop 安装"; Width = 540; Height = 360;
        SizeToContent = SizeToContent.Manual;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        WindowStyle = WindowStyle.None; ResizeMode = ResizeMode.NoResize;
        Background = Brushes.White; Foreground = Brush("#252D3D");
        FontFamily = new FontFamily("Segoe UI, Microsoft YaHei UI");
        UseLayoutRounding = true; SnapsToDevicePixels = true;
        TextOptions.SetTextFormattingMode(this, TextFormattingMode.Display);
        Closing += delegate(object sender, CancelEventArgs args) { args.Cancel = busy; };
        var root = new Grid(); root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(40) });
        root.RowDefinitions.Add(new RowDefinition()); root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(30) });
        Content = new Border { Background = Background, BorderBrush = Brush("#E4EAF3"), BorderThickness = new Thickness(1), Child = root };
        var title = new Grid { Margin = new Thickness(24, 0, 10, 0) };
        title.MouseLeftButtonDown += delegate { try { DragMove(); } catch (InvalidOperationException) { } };
        root.Children.Add(title);
        var brand = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
        brand.Children.Add(Logo(18, 25)); brand.Children.Add(Label("GeneLoop Desktop", 12, "#596477", true, new Thickness(9, 0, 0, 0)));
        title.Children.Add(brand);
        var controls = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
        var minimize = MakeButton("—", false); minimize.Width = 32; minimize.Height = 30; minimize.Click += delegate { WindowState = WindowState.Minimized; };
        close = MakeButton("×", false); close.Width = 32; close.Height = 30; close.FontSize = 18; close.Click += delegate { Close(); };
        System.Windows.Automation.AutomationProperties.SetName(close, "关闭安装器");
        controls.Children.Add(minimize); controls.Children.Add(close); title.Children.Add(controls);

        var panel = new StackPanel { Margin = new Thickness(28, 12, 28, 0) }; Grid.SetRow(panel, 1); root.Children.Add(panel);
        heading = Label("让研究，向前一步。", 24, "#283345", true, new Thickness(0, 0, 0, 18)); panel.Children.Add(heading);
        panel.Children.Add(Label("安装位置", 11, "#808B9D", false, new Thickness(0, 0, 0, 9)));
        var location = new Grid(); location.ColumnDefinitions.Add(new ColumnDefinition()); location.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        pathLabel = Label(target.Path, 11, "#61718B", false, new Thickness(0)); pathLabel.TextWrapping = TextWrapping.NoWrap; pathLabel.TextTrimming = TextTrimming.CharacterEllipsis; pathLabel.VerticalAlignment = VerticalAlignment.Center;
        location.Children.Add(new Border { Background = Brush("#F2F5FA"), CornerRadius = new CornerRadius(11), Padding = new Thickness(12, 11, 12, 11), Child = pathLabel });
        browse = MakeButton("更改", false); browse.Width = 42; browse.Margin = new Thickness(5, 0, 0, 0); browse.Foreground = Brush("#6887BE"); browse.Click += delegate { ChooseFolder(); }; Grid.SetColumn(browse, 1); location.Children.Add(browse); panel.Children.Add(location);
        install = MakeButton("立即安装", true); install.Margin = new Thickness(0, 18, 0, 0); install.Height = 44; install.IsDefault = true; install.Click += async delegate { await RunInstallation(); }; panel.Children.Add(install);
        status = Label("", 11, "#99A2B2", false, new Thickness(0, 12, 0, 0)); status.LineHeight = 18; status.Visibility = Visibility.Collapsed; panel.Children.Add(status);
        progress = new ProgressBar { Height = 3, Foreground = Brush("#7195D6"), Background = Brush("#EEF2F8"), BorderThickness = new Thickness(0), Margin = new Thickness(0, 13, 0, 0), Visibility = Visibility.Collapsed }; panel.Children.Add(progress);
        openApp = Check("打开 GeneLoop Desktop", true); openApp.Visibility = Visibility.Collapsed; openApp.Margin = new Thickness(0, 12, 0, 0); panel.Children.Add(openApp);
        details = MakeButton("自定义设置  ⌄", false); details.Height = 26; details.HorizontalAlignment = HorizontalAlignment.Left; details.Margin = new Thickness(-9, 10, 0, 0); panel.Children.Add(details);
        options = new StackPanel(); shortcut = Check("创建桌面快捷方式", true); shortcut.Checked += delegate { target.DesktopShortcut = true; }; shortcut.Unchecked += delegate { target.DesktopShortcut = false; }; options.Children.Add(shortcut);
        options.Children.Add(Label(target.Machine ? "安装范围：此电脑的所有用户" : "安装范围：当前用户", 10, "#9CA4B3", false, new Thickness(0, 8, 0, 0)));
        optionsArea = new Border { Padding = new Thickness(0, 8, 0, 0), Margin = new Thickness(0, 4, 0, 0), Child = options, Visibility = Visibility.Collapsed }; panel.Children.Add(optionsArea);
        details.Click += delegate { bool shown = optionsArea.Visibility != Visibility.Visible; optionsArea.Visibility = shown ? Visibility.Visible : Visibility.Collapsed; options.Visibility = optionsArea.Visibility; details.Content = shown ? "自定义设置  ⌃" : "自定义设置  ⌄"; };
        options.Visibility = Visibility.Collapsed;
        var footer = new Grid { Margin = new Thickness(28, 0, 28, 0) }; Grid.SetRow(footer, 2); root.Children.Add(footer);
        var version = (AssemblyInformationalVersionAttribute)Attribute.GetCustomAttribute(Assembly.GetExecutingAssembly(), typeof(AssemblyInformationalVersionAttribute));
        footer.Children.Add(Label(version == null ? "Preview" : version.InformationalVersion, 10, "#A2AAB9", false, new Thickness(0)));
        RefreshLocation();
    }

    private static Image Logo(double width, double height)
    {
        var image = new BitmapImage(); using (var data = Assembly.GetExecutingAssembly().GetManifestResourceStream("GeneLoop.Brand")) { image.BeginInit(); image.StreamSource = data; image.CacheOption = BitmapCacheOption.OnLoad; image.EndInit(); }
        return new Image { Source = image, Width = width, Height = height, Stretch = Stretch.Uniform };
    }
    private void ChooseFolder()
    {
        using (var dialog = new Forms.FolderBrowserDialog()) { dialog.Description = "选择 GeneLoop Desktop 的安装位置"; if (Directory.Exists(target.Path)) dialog.SelectedPath = target.Path; if (dialog.ShowDialog() != Forms.DialogResult.OK) return; string root = System.IO.Path.GetFullPath(dialog.SelectedPath).TrimEnd(System.IO.Path.DirectorySeparatorChar); target.Path = String.Equals(System.IO.Path.GetFileName(root), "GeneLoop Desktop", StringComparison.OrdinalIgnoreCase) ? root : System.IO.Path.Combine(root + System.IO.Path.DirectorySeparatorChar, "GeneLoop Desktop"); RefreshLocation(); }
    }
    private void RefreshLocation() { pathLabel.Text = target.Path; pathLabel.ToolTip = target.Path; }
    internal void VerifyLocationControls()
    {
        double width = Width, height = Height;
        details.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        if (options.Visibility != Visibility.Visible || pathLabel.Text != target.Path || !(browse.Parent is Grid) || Grid.GetColumn(browse) != 1 || !Object.Equals(install.Content, "立即安装") || Width != width || Height != height)
            throw new InvalidOperationException("安装选项未正确显示或改变了窗口尺寸");
        details.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        if (options.Visibility != Visibility.Collapsed || Width != width || Height != height || status.Visibility != Visibility.Collapsed)
            throw new InvalidOperationException("收起安装选项后窗口尺寸或文案异常");
    }
    private void ShowCompletion() { if (optionsArea.Visibility == Visibility.Visible) details.RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); completed = true; heading.Text = "安装完成"; install.Content = "完成"; status.Text = ""; status.Visibility = Visibility.Collapsed; openApp.Visibility = Visibility.Visible; details.Visibility = Visibility.Collapsed; browse.IsEnabled = false; progress.Visibility = Visibility.Collapsed; }
    internal void VerifyCompletionControls(bool launch) { double width = Width, height = Height; ShowCompletion(); if (openApp.Visibility != Visibility.Visible || openApp.IsChecked != true || !Object.Equals(install.Content, "完成") || Width != width || Height != height) throw new InvalidOperationException("安装完成选项未显示或窗口尺寸改变"); openApp.IsChecked = launch; if (ShouldOpenApp != launch) throw new InvalidOperationException("启动选项无效"); }
    internal void Preview(string view) { if (view == "options") details.RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); else if (view == "complete") ShowCompletion(); else if (view == "installing") { install.Content = "正在安装…"; install.IsEnabled = details.IsEnabled = browse.IsEnabled = false; details.Visibility = Visibility.Collapsed; status.Visibility = Visibility.Visible; progress.Visibility = Visibility.Visible; progress.IsIndeterminate = true; status.Text = "正在写入文件…"; } }
    private void UpdatePhase(string value)
    {
        int separator = value.IndexOf('|');
        string message = separator < 0 ? value : value.Substring(separator + 1);
        status.Visibility = Visibility.Visible; status.Text = message + "…";
    }
    private async Task RunInstallation()
    {
        if (completed) { if (ShouldOpenApp) { if (returnLaunchToParent) LaunchRequested = true; else { try { InstallEngine.OpenApp(target); } catch { status.Visibility = Visibility.Visible; status.Text = "请从开始菜单打开 GeneLoop Desktop。"; openApp.IsChecked = false; return; } } } Close(); return; }
        if (optionsArea.Visibility == Visibility.Visible) details.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        busy = true; install.IsEnabled = close.IsEnabled = details.IsEnabled = browse.IsEnabled = false;
        details.Visibility = Visibility.Collapsed; status.Visibility = Visibility.Visible;
        install.Content = "正在安装…"; string phase = "正在检查安装位置"; var elapsed = Stopwatch.StartNew();
        Action update = () => { int seconds = (int)elapsed.Elapsed.TotalSeconds; status.Text = phase + (seconds < 60 ? "…" : " · 已用 " + seconds / 60 + " 分 " + seconds % 60 + " 秒"); };
        var clock = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) }; clock.Tick += delegate { update(); }; clock.Start();
        var phases = new Progress<string>(value => { if (!busy || completed) return; UpdatePhase(value); int separator = value.IndexOf('|'); phase = separator < 0 ? value : value.Substring(separator + 1); update(); }); update(); progress.Visibility = Visibility.Visible; progress.IsIndeterminate = true;
        try { int result = await Task.Run(() => InstallEngine.Run(target, null, phases)); if (result == 1618) throw new InvalidOperationException("GeneLoop Desktop 仍在运行，请从托盘退出后重试。"); if (result != 0) throw new InvalidOperationException("安装未完成，错误代码 " + result + "。"); var expected = (AssemblyInformationalVersionAttribute)Attribute.GetCustomAttribute(Assembly.GetExecutingAssembly(), typeof(AssemblyInformationalVersionAttribute)); string file = System.IO.Path.Combine(target.Path, "GeneLoop Desktop.exe"); if (!File.Exists(file) || FileVersionInfo.GetVersionInfo(file).FileVersion != expected.InformationalVersion) throw new InvalidOperationException("未能确认所选位置安装的版本。"); ShowCompletion(); }
        catch (Win32Exception e) { status.Text = e.NativeErrorCode == 1223 ? "已取消管理员授权，可以重试。" : "无法启动安装程序（" + e.NativeErrorCode + "）。"; }
        catch (Exception e) { status.Text = e.Message; }
        finally { clock.Stop(); busy = false; progress.IsIndeterminate = false; progress.Visibility = Visibility.Collapsed; install.IsEnabled = close.IsEnabled = true; details.IsEnabled = browse.IsEnabled = !completed; if (!completed) { install.Content = "重试"; details.Visibility = Visibility.Visible; } }
    }
    private static SolidColorBrush Brush(string hex) { return new SolidColorBrush((Color)ColorConverter.ConvertFromString(hex)); }
    private static TextBlock Label(string value, double size, string color, bool bold, Thickness margin) { return new TextBlock { Text = value, FontSize = size, Foreground = Brush(color), FontWeight = bold ? FontWeights.SemiBold : FontWeights.Normal, Margin = margin, TextWrapping = TextWrapping.Wrap, VerticalAlignment = VerticalAlignment.Center }; }
    private static CheckBox Check(string text, bool value)
    {
        var grid = new FrameworkElementFactory(typeof(Grid));
        var box = new FrameworkElementFactory(typeof(Border), "Box"); box.SetValue(FrameworkElement.WidthProperty, 15.0); box.SetValue(FrameworkElement.HeightProperty, 15.0);
        box.SetValue(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Left); box.SetValue(Border.CornerRadiusProperty, new CornerRadius(4)); box.SetValue(Border.BorderBrushProperty, Brush("#CFD7E6")); box.SetValue(Border.BorderThicknessProperty, new Thickness(1)); box.SetValue(Border.BackgroundProperty, Brushes.White);
        var tick = new FrameworkElementFactory(typeof(TextBlock), "Tick"); tick.SetValue(TextBlock.TextProperty, "✓"); tick.SetValue(TextBlock.FontSizeProperty, 10.0); tick.SetValue(TextBlock.ForegroundProperty, Brushes.White); tick.SetValue(TextBlock.TextAlignmentProperty, TextAlignment.Center); tick.SetValue(UIElement.VisibilityProperty, Visibility.Hidden); box.AppendChild(tick); grid.AppendChild(box);
        var content = new FrameworkElementFactory(typeof(ContentPresenter)); content.SetValue(FrameworkElement.MarginProperty, new Thickness(23, 0, 0, 0)); content.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center); grid.AppendChild(content);
        var template = new ControlTemplate(typeof(CheckBox)) { VisualTree = grid };
        var selected = new Trigger { Property = System.Windows.Controls.Primitives.ToggleButton.IsCheckedProperty, Value = true }; selected.Setters.Add(new Setter(Border.BackgroundProperty, Brush("#527DCC"), "Box")); selected.Setters.Add(new Setter(Border.BorderBrushProperty, Brush("#527DCC"), "Box")); selected.Setters.Add(new Setter(UIElement.VisibilityProperty, Visibility.Visible, "Tick")); template.Triggers.Add(selected);
        var focus = new Trigger { Property = UIElement.IsKeyboardFocusedProperty, Value = true }; focus.Setters.Add(new Setter(Border.BorderBrushProperty, Brush("#2656AC"), "Box")); template.Triggers.Add(focus);
        return new CheckBox { Content = text, IsChecked = value, Template = template, MinHeight = 18, FontSize = 11, Foreground = Brush("#69768C"), VerticalContentAlignment = VerticalAlignment.Center, Cursor = System.Windows.Input.Cursors.Hand };
    }
    private static Button MakeButton(string text, bool primary)
    {
        var border = new FrameworkElementFactory(typeof(Border), "Chrome"); border.SetValue(Border.CornerRadiusProperty, new CornerRadius(primary ? 12 : 8)); border.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(Control.BackgroundProperty));
        var content = new FrameworkElementFactory(typeof(ContentPresenter)); content.SetValue(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Center); content.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center); border.AppendChild(content);
        var template = new ControlTemplate(typeof(Button)) { VisualTree = border }; var hover = new Trigger { Property = UIElement.IsMouseOverProperty, Value = true }; hover.Setters.Add(new Setter(Border.BackgroundProperty, Brush(primary ? "#3565BE" : "#F0F3FA"), "Chrome")); template.Triggers.Add(hover);
        var focus = new Trigger { Property = UIElement.IsKeyboardFocusedProperty, Value = true }; focus.Setters.Add(new Setter(Border.BackgroundProperty, Brush(primary ? "#3565BE" : "#E9EFFB"), "Chrome")); template.Triggers.Add(focus);
        var disabled = new Trigger { Property = UIElement.IsEnabledProperty, Value = false }; disabled.Setters.Add(new Setter(UIElement.OpacityProperty, .55)); template.Triggers.Add(disabled);
        return new Button { Content = text, Template = template, Background = Brush(primary ? "#4776CD" : "#00FFFFFF"), Foreground = primary ? Brushes.White : Brush("#9AA4B5"), FontSize = primary ? 13 : 11, Height = 32, MinWidth = 28, Padding = new Thickness(9, 0, 9, 0), BorderThickness = new Thickness(0), Cursor = System.Windows.Input.Cursors.Hand };
    }
}
