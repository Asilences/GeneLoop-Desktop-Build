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

internal sealed class InstallTarget
{
    internal bool DesktopShortcut = true;
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
                    if (!target.DesktopShortcut)
                    {
                        string desktop = Environment.GetFolderPath(target.Machine ? Environment.SpecialFolder.CommonDesktopDirectory : Environment.SpecialFolder.DesktopDirectory);
                        if (!String.IsNullOrWhiteSpace(desktop))
                        {
                            string shortcut = Path.Combine(desktop, "GeneLoop Desktop.lnk");
                            if (File.Exists(shortcut)) File.Delete(shortcut);
                        }
                    }
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
            if (args.Length == 3 && args[0] == "--render-ui")
            {
                if (args[1] != "ready" && args[1] != "options" && args[1] != "installing" && args[1] != "complete") return 2;
                var preview = new InstallerWindow(new InstallTarget { Path = @"D:\GeneLoop Desktop" }, true);
                preview.Preview(args[1]);
                var visual = (FrameworkElement)preview.Content;
                visual.Measure(new Size(preview.Width, preview.Height));
                visual.Arrange(new Rect(0, 0, preview.Width, preview.Height));
                visual.UpdateLayout();
                var bitmap = new RenderTargetBitmap((int)preview.Width, (int)preview.Height, 96, 96, PixelFormats.Pbgra32);
                bitmap.Render(visual); var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(bitmap));
                using (var stream = File.Create(args[2])) png.Save(stream);
                preview.Close(); return 0;
            }
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
