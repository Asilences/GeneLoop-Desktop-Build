using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32;

// A filesystem transaction around the existing NSIS registration lifecycle.
// User data stays outside this transaction. No process is killed.
internal sealed class InstallTransaction : IDisposable
{
    private readonly string original, target, stage, previous, failed;
    private string externalPartial;
    private readonly Action<string> record;
    private readonly List<RegistryCopy> registry = new List<RegistryCopy>();
    private readonly List<ShortcutCopy> shortcuts = new List<ShortcutCopy>();
    private bool moved, committed;
    internal bool RecoveryRequired { get; private set; }
    internal string PreviousDirectory { get { return moved ? previous : ""; } }
    internal string ReuseJournal { get { return Path.Combine(stage, "reused-components.txt"); } }

    internal InstallTransaction(string originalDirectory, string targetDirectory, string stageDirectory, Action<string> trace)
    {
        original = String.IsNullOrWhiteSpace(originalDirectory) ? null : Path.GetFullPath(originalDirectory).TrimEnd('\\');
        target = Path.GetFullPath(targetDirectory).TrimEnd('\\');
        stage = Path.GetFullPath(stageDirectory).TrimEnd('\\');
        previous = Path.Combine(stage, "previous-install");
        failed = Path.Combine(stage, "failed-install");
        record = trace ?? delegate { };
    }

    internal static void SecureStage(string path)
    {
        var security = new DirectorySecurity();
        security.SetAccessRuleProtection(true, false);
        foreach (var id in new[] { WindowsIdentity.GetCurrent().User,
            new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null),
            new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null) })
            security.AddAccessRule(new FileSystemAccessRule(id, FileSystemRights.FullControl,
                InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
                PropagationFlags.None, AccessControlType.Allow));
        new DirectoryInfo(path).SetAccessControl(security);
    }

    private static void PlainDirectory(string path)
    {
        for (var at = path; !String.IsNullOrEmpty(at); at = Path.GetDirectoryName(at))
            if (Directory.Exists(at) && (File.GetAttributes(at) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("安装路径不能包含链接。");
        if (Path.GetPathRoot(path).TrimEnd('\\') == path.TrimEnd('\\'))
            throw new IOException("不能将磁盘根目录作为应用目录。");
    }

    private static bool Same(string left, string right) { return String.Equals(left, right, StringComparison.OrdinalIgnoreCase); }
    private static bool Contains(string parent, string child) { return Same(parent, child) || child.StartsWith(parent + "\\", StringComparison.OrdinalIgnoreCase); }

    internal void Prepare(bool captureRegistry, bool machine = false)
    {
        PlainDirectory(target); PlainDirectory(stage);
        if (original == null || !Directory.Exists(original)) return;
        PlainDirectory(original);
        if (!Same(Path.GetPathRoot(original), Path.GetPathRoot(stage))) throw new IOException("旧版本备份必须位于同一磁盘。");
        if (Contains(original, stage) || Contains(target, stage) || Contains(stage, original) || Contains(stage, target) ||
            (!Same(original, target) && (Contains(original, target) || Contains(target, original))))
            throw new IOException("新旧安装目录和备份目录不能互相包含。");
        if (!File.Exists(Path.Combine(original, "GeneLoop Desktop.exe")) || !File.Exists(Path.Combine(original, "Uninstall GeneLoop Desktop.exe")))
            throw new IOException("原安装目录不完整，保留现场，未移动文件。");
        if (!String.Equals(original, target, StringComparison.OrdinalIgnoreCase) && Directory.Exists(target) && Directory.GetFileSystemEntries(target).Length != 0)
            throw new IOException("所选新目录已有文件，请选择空目录。");
        if (Process.GetProcessesByName("GeneLoop Desktop").Length != 0 || IsRunningFrom(original))
            throw new InvalidOperationException("GeneLoop Desktop 仍在运行，请从托盘退出。");
        if (captureRegistry && machine)
        {
            // NSIS can uninstall both per-user and all-user installations. Keep
            // its original flow when they point to different directories.
            foreach (var hive in new[] { RegistryHive.CurrentUser, RegistryHive.LocalMachine })
            using (var root = RegistryKey.OpenBaseKey(hive, RegistryView.Registry64))
            using (var key = root.OpenSubKey(@"Software\df43dd29-397e-5d1c-b2f3-fe84b0ec1dc1"))
            {
                var location = key == null ? null : key.GetValue("InstallLocation") as string;
                if (!String.IsNullOrWhiteSpace(location) && !Same(Path.GetFullPath(location).TrimEnd('\\'), original))
                { record("legacy_multiple_installations"); return; }
            }
        }
        if (captureRegistry)
            foreach (var hive in machine ? new[] { RegistryHive.CurrentUser, RegistryHive.LocalMachine } : new[] { RegistryHive.CurrentUser })
                foreach (var key in new[] { @"Software\df43dd29-397e-5d1c-b2f3-fe84b0ec1dc1", @"Software\Microsoft\Windows\CurrentVersion\Uninstall\df43dd29-397e-5d1c-b2f3-fe84b0ec1dc1", @"Software\Classes\AppUserModelId\ai.geneloop.desktop" })
                    registry.Add(RegistryCopy.Capture(hive, key));
        if (captureRegistry)
            foreach (var folder in machine ? new[] { Environment.SpecialFolder.DesktopDirectory, Environment.SpecialFolder.Programs, Environment.SpecialFolder.CommonDesktopDirectory, Environment.SpecialFolder.CommonPrograms } :
                new[] { Environment.SpecialFolder.DesktopDirectory, Environment.SpecialFolder.Programs })
            {
                var parent = Environment.GetFolderPath(folder);
                if (!String.IsNullOrEmpty(parent)) shortcuts.Add(new ShortcutCopy(Path.Combine(parent, "GeneLoop Desktop.lnk")));
            }
        Journal("prepared");
        Directory.Move(original, previous);
        moved = true;
        Journal("old_directory_moved");
        Directory.CreateDirectory(original);
        File.Copy(Path.Combine(previous, "Uninstall GeneLoop Desktop.exe"), Path.Combine(original, "Uninstall GeneLoop Desktop.exe"));
        // NSIS uses FileExists(appExe) to retain existing shortcuts on update.
        // The original executable remains untouched in the whole-tree backup.
        using (var stub = new FileStream(Path.Combine(original, "GeneLoop Desktop.exe"), FileMode.CreateNew)) { }
        record("old_directory_staged");
    }

    private void Journal(string phase)
    {
        var path = Path.Combine(stage, "recovery.txt");
        File.WriteAllLines(path, new[] { "GeneLoop installer transaction v1", "phase=" + phase,
            "original=" + original, "target=" + target, "backup=" + previous });
    }

    internal void Commit()
    {
        Journal("committed"); committed = true; record("installation_committed");
    }

    internal bool HasBackup { get { return Directory.Exists(previous); } }

    public void Dispose()
    {
        if (!moved || committed) return;
        try
        {
            record("rollback_start");
            RestoreReusedDirectories();
            // First retain any partial replacement, then restore the old
            // directory with one rename. AppData is never part of this tree.
            if (Directory.Exists(original)) { PlainDirectory(original); Directory.Move(original, failed); }
            if (!Same(original, target) && Directory.Exists(target))
            {
                PlainDirectory(target);
                // A changed destination can be on another volume. Retain the
                // partial tree there instead of copying it during rollback.
                externalPartial = target + ".GeneLoop-failed-" + Guid.NewGuid().ToString("N");
                Directory.Move(target, externalPartial);
            }
            Directory.Move(previous, original);
            foreach (var copy in registry) copy.Restore();
            foreach (var shortcut in shortcuts) shortcut.Restore();
            moved = false; Journal("restored");
            if (externalPartial != null)
            {
                File.AppendAllText(Path.Combine(stage, "recovery.txt"), "\npartial=" + externalPartial);
                RecoveryRequired = true;
            }
            record("rollback_complete");
        }
        catch { RecoveryRequired = true; Journal("recovery_required"); throw; }
    }

    private void RestoreReusedDirectories()
    {
        if (!File.Exists(ReuseJournal)) return;
        var lines = File.ReadAllLines(ReuseJournal);
        Array.Reverse(lines);
        foreach (var line in lines)
        {
            if (String.IsNullOrWhiteSpace(line)) continue;
            var relative = Encoding.UTF8.GetString(Convert.FromBase64String(line));
            if (Path.IsPathRooted(relative) || relative.IndexOf(':') >= 0) throw new IOException("工具恢复记录无效。");
            var source = Path.GetFullPath(Path.Combine(target, relative));
            var saved = Path.GetFullPath(Path.Combine(previous, relative));
            if (!source.StartsWith(target + "\\", StringComparison.OrdinalIgnoreCase) ||
                !saved.StartsWith(previous + "\\", StringComparison.OrdinalIgnoreCase)) throw new IOException("工具恢复路径无效。");
            if (Directory.Exists(saved)) continue; // Intent was recorded but no move occurred.
            if (!Directory.Exists(source)) throw new IOException("工具恢复目录缺失，请保留安装备份。");
            PlainDirectory(source); PlainDirectory(saved);
            Directory.CreateDirectory(Path.GetDirectoryName(saved));
            Directory.Move(source, saved);
        }
    }

    [DllImport("kernel32.dll", SetLastError = true)] private static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool QueryFullProcessImageName(IntPtr process, int flags, StringBuilder path, ref int size);
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);
    private static bool IsRunningFrom(string directory)
    {
        foreach (var process in Process.GetProcesses())
        using (process)
        {
            var handle = OpenProcess(0x1000, false, process.Id);
            if (handle == IntPtr.Zero) continue;
            try {
                int size = 32768; var path = new StringBuilder(size);
                if (QueryFullProcessImageName(handle, 0, path, ref size) && path.ToString().StartsWith(directory + "\\", StringComparison.OrdinalIgnoreCase)) return true;
            } finally { CloseHandle(handle); }
        }
        return false;
    }

    private sealed class ShortcutCopy
    {
        private readonly string path;
        private readonly byte[] bytes;
        internal ShortcutCopy(string location) { path = location; if (File.Exists(path)) bytes = File.ReadAllBytes(path); }
        internal void Restore()
        {
            if (File.Exists(path)) File.Delete(path);
            if (bytes != null) using (var stream = new FileStream(path, FileMode.CreateNew)) stream.Write(bytes, 0, bytes.Length);
        }
    }

    private sealed class RegistryCopy
    {
        private RegistryHive hive;
        private string path;
        private bool existed;
        private readonly Dictionary<string, object> values = new Dictionary<string, object>();
        private readonly Dictionary<string, RegistryValueKind> kinds = new Dictionary<string, RegistryValueKind>();
        private readonly List<RegistryCopy> children = new List<RegistryCopy>();
        internal static RegistryCopy Capture(RegistryHive hive, string path)
        {
            var copy = new RegistryCopy { hive = hive, path = path };
            using (var root = RegistryKey.OpenBaseKey(hive, RegistryView.Registry64))
            using (var key = root.OpenSubKey(path))
            {
                copy.existed = key != null;
                if (key != null) foreach (var name in key.GetValueNames())
                {
                    copy.values[name] = key.GetValue(name, null, RegistryValueOptions.DoNotExpandEnvironmentNames);
                    copy.kinds[name] = key.GetValueKind(name);
                }
                if (key != null) foreach (var name in key.GetSubKeyNames()) copy.children.Add(Capture(hive, path + "\\" + name));
            }
            return copy;
        }
        internal void Restore()
        {
            using (var root = RegistryKey.OpenBaseKey(hive, RegistryView.Registry64))
            {
                root.DeleteSubKeyTree(path, false);
                if (!existed) return;
                using (var key = root.CreateSubKey(path))
                    foreach (var value in values) key.SetValue(value.Key, value.Value, kinds[value.Key]);
                foreach (var child in children) child.Restore();
            }
        }
    }
}
