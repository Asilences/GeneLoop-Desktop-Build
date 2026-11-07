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
using System.Windows.Shapes;
using System.Windows.Threading;
using Forms = System.Windows.Forms;

// Native WPF composition, inspired by Fluent/ModernWpf and WixSharp's managed
// bootstrapper separation. No extra UI runtime or webview is installed.
internal sealed class InstallerWindow : Window
{
    private readonly InstallTarget target;
    private readonly StackPanel options;
    private readonly TextBlock pathLabel, status, heading, subtitle;
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
        Title = "GeneLoop Desktop 安装"; Width = 744; Height = 504;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        WindowStyle = WindowStyle.None; ResizeMode = ResizeMode.NoResize;
        Background = Brush("#FAFBFE"); Foreground = Brush("#252D3D");
        FontFamily = new FontFamily("Segoe UI, Microsoft YaHei UI");
        UseLayoutRounding = true; SnapsToDevicePixels = true;
        TextOptions.SetTextFormattingMode(this, TextFormattingMode.Display);
        Closing += delegate(object sender, CancelEventArgs args) { args.Cancel = busy; };
        var root = new Grid(); root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(48) });
        root.RowDefinitions.Add(new RowDefinition()); root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(48) });
        Content = new Border { Background = Background, BorderBrush = Brush("#E3E7F0"), BorderThickness = new Thickness(1), Child = root };
        var title = new Grid { Margin = new Thickness(24, 0, 10, 0) };
        title.MouseLeftButtonDown += delegate { try { DragMove(); } catch (InvalidOperationException) { } };
        root.Children.Add(title);
        var brand = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
        brand.Children.Add(Logo(18, 25)); brand.Children.Add(Label("GeneLoop", 12, "#596477", true, new Thickness(9, 0, 0, 0)));
        title.Children.Add(brand);
        var controls = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
        var minimize = MakeButton("—", false); minimize.Width = 32; minimize.Height = 30; minimize.Click += delegate { WindowState = WindowState.Minimized; };
        close = MakeButton("×", false); close.Width = 32; close.Height = 30; close.FontSize = 18; close.Click += delegate { Close(); };
        System.Windows.Automation.AutomationProperties.SetName(close, "关闭安装器");
        controls.Children.Add(minimize); controls.Children.Add(close); title.Children.Add(controls);

        var main = new Grid { Margin = new Thickness(28, 5, 28, 0) }; Grid.SetRow(main, 1); root.Children.Add(main);
        main.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(300) }); main.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(22) }); main.ColumnDefinitions.Add(new ColumnDefinition());
        var story = new Grid { ClipToBounds = true };
        story.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); story.RowDefinitions.Add(new RowDefinition()); story.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        main.Children.Add(story);
        var introduction = new StackPanel { Margin = new Thickness(0, 21, 0, 0) };
        introduction.Children.Add(Label("让研究，\n向前一步。", 32, "#263247", true, new Thickness(0, 0, 0, 13)));
        introduction.Children.Add(Label("把资料、想法和下一步，连接起来。", 12, "#8A94A6", false, new Thickness(1, 0, 0, 0)));
        story.Children.Add(introduction);
        var graph = Graph(); Grid.SetRow(graph, 1); story.Children.Add(graph);
        var scenes = new WrapPanel { Margin = new Thickness(0, 0, 8, 7) };
        foreach (var name in new string[] { "通用对话", "文件管理", "数据分析", "论文核验", "演示文稿", "视频创作" })
        {
            var tile = new StackPanel { Orientation = Orientation.Horizontal };
            tile.Children.Add(new Ellipse { Width = 4, Height = 4, Fill = Brush("#9DAED0"), VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 7, 0) });
            tile.Children.Add(Label(name, 10, "#8A94A6", false, new Thickness(0)));
            scenes.Children.Add(new Border { Width = 96, Padding = new Thickness(1, 7, 0, 7), Child = tile });
        }
        Grid.SetRow(scenes, 2); story.Children.Add(scenes);

        var panel = new StackPanel { Margin = new Thickness(22, 24, 22, 20) };
        var card = new Border { Background = Brushes.White, BorderBrush = Brush("#E6EAF2"), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(16), Child = panel, VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(0, 10, 0, 0) };
        Grid.SetColumn(card, 2); main.Children.Add(card);
        heading = Label("安装 GeneLoop Desktop", 17, "#283345", true, new Thickness(0, 0, 0, 10)); panel.Children.Add(heading);
        subtitle = Label("为你的研究，准备一个专属工作区。", 11, "#929AAA", false, new Thickness(0, 0, 0, 27)); panel.Children.Add(subtitle);
        panel.Children.Add(Label("安装位置", 11, "#808B9D", false, new Thickness(0, 0, 0, 9)));
        var location = new Grid(); location.ColumnDefinitions.Add(new ColumnDefinition()); location.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        pathLabel = Label(target.Path, 11, "#61718B", false, new Thickness(0)); pathLabel.TextWrapping = TextWrapping.NoWrap; pathLabel.TextTrimming = TextTrimming.CharacterEllipsis; pathLabel.VerticalAlignment = VerticalAlignment.Center;
        location.Children.Add(new Border { Background = Brush("#F5F7FB"), CornerRadius = new CornerRadius(8), Padding = new Thickness(11, 10, 11, 10), Child = pathLabel });
        browse = MakeButton("更改", false); browse.Width = 42; browse.Margin = new Thickness(5, 0, 0, 0); browse.Foreground = Brush("#6887BE"); browse.Click += delegate { ChooseFolder(); }; Grid.SetColumn(browse, 1); location.Children.Add(browse); panel.Children.Add(location);
        install = MakeButton("立即安装", true); install.Margin = new Thickness(0, 23, 0, 0); install.Height = 42; install.IsDefault = true; install.Click += async delegate { await RunInstallation(); }; panel.Children.Add(install);
        status = Label("安装后，可统一准备本机工具。", 11, "#99A2B2", false, new Thickness(0, 12, 0, 0)); status.LineHeight = 18; panel.Children.Add(status);
        progress = new ProgressBar { Height = 3, Foreground = Brush("#7195D6"), Background = Brush("#EEF2F8"), BorderThickness = new Thickness(0), Margin = new Thickness(0, 13, 0, 0), Visibility = Visibility.Collapsed }; panel.Children.Add(progress);
        openApp = Check("打开 GeneLoop Desktop", true); openApp.Visibility = Visibility.Collapsed; openApp.Margin = new Thickness(0, 16, 0, 0); panel.Children.Add(openApp);
        details = MakeButton("自定义设置  ⌄", false); details.Height = 28; details.HorizontalAlignment = HorizontalAlignment.Left; details.Margin = new Thickness(-9, 17, 0, 0); panel.Children.Add(details);
        options = new StackPanel(); shortcut = Check("创建桌面快捷方式", true); shortcut.Checked += delegate { target.DesktopShortcut = true; }; shortcut.Unchecked += delegate { target.DesktopShortcut = false; }; options.Children.Add(shortcut);
        options.Children.Add(Label(target.Machine ? "安装范围：此电脑的所有用户" : "安装范围：当前用户", 10, "#9CA4B3", false, new Thickness(0, 12, 0, 0)));
        optionsArea = new Border { BorderBrush = Brush("#EDF0F6"), BorderThickness = new Thickness(0, 1, 0, 0), Padding = new Thickness(0, 15, 0, 0), Margin = new Thickness(0, 8, 0, 0), Child = options, Visibility = Visibility.Collapsed }; panel.Children.Add(optionsArea);
        details.Click += delegate { bool shown = optionsArea.Visibility != Visibility.Visible; optionsArea.Visibility = shown ? Visibility.Visible : Visibility.Collapsed; options.Visibility = optionsArea.Visibility; details.Content = shown ? "自定义设置  ⌃" : "自定义设置  ⌄"; Height = shown ? 584 : 504; };
        options.Visibility = Visibility.Collapsed;
        var footer = new Grid { Margin = new Thickness(28, 0, 28, 0) }; Grid.SetRow(footer, 2); root.Children.Add(footer);
        var version = (AssemblyInformationalVersionAttribute)Attribute.GetCustomAttribute(Assembly.GetExecutingAssembly(), typeof(AssemblyInformationalVersionAttribute));
        footer.Children.Add(Label("GeneLoop Desktop  ·  " + (version == null ? "Preview" : version.InformationalVersion), 10, "#A2AAB9", false, new Thickness(0)));
        var license = MakeButton("开源许可", false); license.FontSize = 10; license.HorizontalAlignment = HorizontalAlignment.Right; license.Click += delegate { MessageBox.Show(this, "本安装器保留 NSIS 的安装与回退机制。\n工具包使用 7-Zip；完整许可随应用提供。\n\nhttps://nsis.sourceforge.io\nhttps://www.7-zip.org/license.txt", "开源许可", MessageBoxButton.OK, MessageBoxImage.Information); }; footer.Children.Add(license);
        RefreshLocation();
    }

    private static Image Logo(double width, double height)
    {
        var image = new BitmapImage(); using (var data = Assembly.GetExecutingAssembly().GetManifestResourceStream("GeneLoop.Brand")) { image.BeginInit(); image.StreamSource = data; image.CacheOption = BitmapCacheOption.OnLoad; image.EndInit(); }
        return new Image { Source = image, Width = width, Height = height, Stretch = Stretch.Uniform };
    }
    private static FrameworkElement Graph()
    {
        var canvas = new Canvas { Width = 288, Height = 170, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(-7, 3, 0, 0) };
        var links = new System.Windows.Shapes.Path { Data = Geometry.Parse("M36,118 C65,118 68,52 114,52 M114,52 C161,52 169,114 222,114 M114,52 C152,54 175,35 250,35"), Stroke = Brush("#DDE4F3"), StrokeThickness = 1.2 };
        canvas.Children.Add(links);
        AddNode(canvas, 13, 91, "#8AA8D9", "M8,4 L17,4 L22,9 L22,23 L8,23 Z M17,4 L17,10 L22,10 M12,15 L18,15 M12,19 L18,19");
        AddNode(canvas, 87, 25, "#9489D0", "M7,5 L23,5 L23,20 L7,20 Z M15,20 L15,25 M11,25 L19,25 M11,10 L19,10 M11,14 L17,14");
        AddNode(canvas, 197, 86, "#6EB9AF", "M7,23 L7,8 M7,23 L24,23 M12,19 L12,12 M17,19 L17,5 M22,19 L22,10");
        var small = new Ellipse { Width = 7, Height = 7, Fill = Brush("#BCCAE8") }; Canvas.SetLeft(small, 247); Canvas.SetTop(small, 31); canvas.Children.Add(small);
        return canvas;
    }
    private static void AddNode(Canvas canvas, double x, double y, string color, string geometry)
    {
        var drawing = new System.Windows.Shapes.Path { Width = 27, Height = 27, Data = Geometry.Parse(geometry), Stroke = Brush(color), StrokeThickness = 1.25, StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round, StrokeLineJoin = PenLineJoin.Round };
        var tile = new Border { Width = 54, Height = 54, Background = Brushes.White, BorderBrush = Brush("#E8ECF5"), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(13), Child = drawing, Padding = new Thickness(12), Effect = new System.Windows.Media.Effects.DropShadowEffect { BlurRadius = 16, ShadowDepth = 3, Opacity = .045, Color = Colors.SlateGray } };
        Canvas.SetLeft(tile, x); Canvas.SetTop(tile, y); canvas.Children.Add(tile);
    }
    private void ChooseFolder()
    {
        using (var dialog = new Forms.FolderBrowserDialog()) { dialog.Description = "选择 GeneLoop Desktop 的安装位置"; if (Directory.Exists(target.Path)) dialog.SelectedPath = target.Path; if (dialog.ShowDialog() != Forms.DialogResult.OK) return; string root = System.IO.Path.GetFullPath(dialog.SelectedPath).TrimEnd(System.IO.Path.DirectorySeparatorChar); target.Path = String.Equals(System.IO.Path.GetFileName(root), "GeneLoop Desktop", StringComparison.OrdinalIgnoreCase) ? root : System.IO.Path.Combine(root + System.IO.Path.DirectorySeparatorChar, "GeneLoop Desktop"); RefreshLocation(); }
    }
    private void RefreshLocation() { pathLabel.Text = target.Path; pathLabel.ToolTip = target.Path; }
    internal void VerifyLocationControls() { details.RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); if (options.Visibility != Visibility.Visible || pathLabel.Text != target.Path || !(browse.Parent is Grid) || Grid.GetColumn(browse) != 1 || !Object.Equals(install.Content, "立即安装")) throw new InvalidOperationException("安装位置选项未正确显示"); }
    private void ShowCompletion() { if (optionsArea.Visibility == Visibility.Visible) details.RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); completed = true; heading.Text = "安装完成"; subtitle.Text = "你的研究工作区已准备好。"; install.Content = "完成"; status.Text = "首次打开可统一准备本机工具。"; openApp.Visibility = Visibility.Visible; details.Visibility = Visibility.Collapsed; browse.IsEnabled = false; progress.Visibility = Visibility.Collapsed; }
    internal void VerifyCompletionControls(bool launch) { ShowCompletion(); if (openApp.Visibility != Visibility.Visible || openApp.IsChecked != true || !Object.Equals(install.Content, "完成")) throw new InvalidOperationException("安装完成选项未显示"); openApp.IsChecked = launch; if (ShouldOpenApp != launch) throw new InvalidOperationException("启动选项无效"); }
    internal void Preview(string view) { if (view == "options") details.RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); else if (view == "complete") ShowCompletion(); else if (view == "installing") { install.Content = "正在安装…"; install.IsEnabled = details.IsEnabled = browse.IsEnabled = false; progress.Visibility = Visibility.Visible; progress.IsIndeterminate = true; status.Text = "正在写入应用文件…"; } }
    private async Task RunInstallation()
    {
        if (completed) { if (ShouldOpenApp) { if (returnLaunchToParent) LaunchRequested = true; else { try { InstallEngine.OpenApp(target); } catch { status.Text = "请从开始菜单打开 GeneLoop Desktop。"; openApp.IsChecked = false; return; } } } Close(); return; }
        busy = true; install.IsEnabled = close.IsEnabled = details.IsEnabled = browse.IsEnabled = false;
        if (optionsArea.Visibility == Visibility.Visible) details.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        install.Content = "正在安装…"; string phase = "正在准备安装文件"; var elapsed = Stopwatch.StartNew();
        Action update = () => { int seconds = (int)elapsed.Elapsed.TotalSeconds; status.Text = phase + (seconds < 60 ? "…" : " · 已用 " + seconds / 60 + " 分 " + seconds % 60 + " 秒"); };
        var clock = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) }; clock.Tick += delegate { update(); }; clock.Start();
        var phases = new Progress<string>(value => { if (!busy || completed) return; phase = value; update(); }); update(); progress.Visibility = Visibility.Visible; progress.IsIndeterminate = true;
        try { int result = await Task.Run(() => InstallEngine.Run(target, null, phases)); if (result == 1618) throw new InvalidOperationException("GeneLoop Desktop 仍在运行，请从托盘退出后重试。"); if (result != 0) throw new InvalidOperationException("安装未完成，错误代码 " + result + "。"); var expected = (AssemblyInformationalVersionAttribute)Attribute.GetCustomAttribute(Assembly.GetExecutingAssembly(), typeof(AssemblyInformationalVersionAttribute)); string file = System.IO.Path.Combine(target.Path, "GeneLoop Desktop.exe"); if (!File.Exists(file) || FileVersionInfo.GetVersionInfo(file).FileVersion != expected.InformationalVersion) throw new InvalidOperationException("未能确认所选位置安装的版本。"); ShowCompletion(); }
        catch (Win32Exception e) { status.Text = e.NativeErrorCode == 1223 ? "已取消管理员授权，可以重试。" : "无法启动安装程序（" + e.NativeErrorCode + "）。"; }
        catch (Exception e) { status.Text = e.Message; }
        finally { clock.Stop(); busy = false; progress.IsIndeterminate = false; progress.Visibility = Visibility.Collapsed; install.IsEnabled = close.IsEnabled = true; details.IsEnabled = browse.IsEnabled = !completed; if (!completed) install.Content = "重试"; }
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
        var border = new FrameworkElementFactory(typeof(Border), "Chrome"); border.SetValue(Border.CornerRadiusProperty, new CornerRadius(8)); border.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(Control.BackgroundProperty));
        var content = new FrameworkElementFactory(typeof(ContentPresenter)); content.SetValue(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Center); content.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center); border.AppendChild(content);
        var template = new ControlTemplate(typeof(Button)) { VisualTree = border }; var hover = new Trigger { Property = UIElement.IsMouseOverProperty, Value = true }; hover.Setters.Add(new Setter(Border.BackgroundProperty, Brush(primary ? "#3565BE" : "#F0F3FA"), "Chrome")); template.Triggers.Add(hover);
        var focus = new Trigger { Property = UIElement.IsKeyboardFocusedProperty, Value = true }; focus.Setters.Add(new Setter(Border.BackgroundProperty, Brush(primary ? "#3565BE" : "#E9EFFB"), "Chrome")); template.Triggers.Add(focus);
        var disabled = new Trigger { Property = UIElement.IsEnabledProperty, Value = false }; disabled.Setters.Add(new Setter(UIElement.OpacityProperty, .55)); template.Triggers.Add(disabled);
        return new Button { Content = text, Template = template, Background = Brush(primary ? "#4776CD" : "#00FFFFFF"), Foreground = primary ? Brushes.White : Brush("#9AA4B5"), FontSize = primary ? 13 : 11, Height = 32, MinWidth = 28, Padding = new Thickness(9, 0, 9, 0), BorderThickness = new Thickness(0), Cursor = System.Windows.Input.Cursors.Hand };
    }
}
