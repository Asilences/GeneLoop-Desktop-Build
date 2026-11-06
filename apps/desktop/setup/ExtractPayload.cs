using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;

internal static class ExtractPayload
{
    private static void CheckDirectory(string directory, HashSet<string> checkedDirectories)
    {
        if (checkedDirectories.Contains(directory)) return;
        var parent = Path.GetDirectoryName(directory);
        if (!String.IsNullOrEmpty(parent) && parent != directory) CheckDirectory(parent, checkedDirectories);
        if (Directory.Exists(directory))
        {
            if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0) throw new IOException("安装目录包含链接");
        }
        else Directory.CreateDirectory(directory);
        checkedDirectories.Add(directory);
    }

    [STAThread]
    public static int Main(string[] args)
    {
        try
        {
            if (args.Length != 2) return 20;
            var root = Path.GetFullPath(args[1]).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            using (var input = new FileStream(args[0], FileMode.Open, FileAccess.Read, FileShare.Read, 131072, FileOptions.SequentialScan))
            {
                using (var sha = SHA256.Create())
                    if (BitConverter.ToString(sha.ComputeHash(input)).Replace("-", "").ToLowerInvariant() != PayloadBuild.Sha256) return 21;
                input.Position = 0;
                using (var zip = new ZipArchive(input, ZipArchiveMode.Read, false, Encoding.UTF8))
                {
                    var paths = new Dictionary<ZipArchiveEntry, string>();
                    var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    long total = 0;
                    foreach (var entry in zip.Entries)
                    {
                        var name = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                        if (String.IsNullOrEmpty(entry.Name)) continue;
                        if (Path.IsPathRooted(name) || name.IndexOf(':') >= 0 || name.IndexOf('\0') >= 0) return 22;
                        foreach (var part in name.Split(Path.DirectorySeparatorChar))
                            if (part == "." || part == ".." || part.EndsWith(" ") || part.EndsWith(".")) return 22;
                        var destination = Path.GetFullPath(Path.Combine(root, name));
                        if (!destination.StartsWith(root, StringComparison.OrdinalIgnoreCase) || !seen.Add(destination)) return 22;
                        // Fail before touching files if this Windows/.NET path cannot be represented.
                        if (destination.Length >= 260) return 23;
                        total = checked(total + entry.Length);
                        paths.Add(entry, destination);
                    }
                    if (paths.Count != PayloadBuild.Files || total != PayloadBuild.Bytes) return 24;
                    var directories = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    CheckDirectory(root.TrimEnd(Path.DirectorySeparatorChar), directories);
                    foreach (var pair in paths)
                    {
                        var entry = pair.Key; var destination = pair.Value;
                        CheckDirectory(Path.GetDirectoryName(destination), directories);
                        if (File.Exists(destination) && (File.GetAttributes(destination) & FileAttributes.ReparsePoint) != 0) return 22;
                        using (var from = entry.Open())
                        using (var to = new FileStream(destination, FileMode.Create, FileAccess.Write, FileShare.None, 131072, FileOptions.SequentialScan))
                            from.CopyTo(to, 131072);
                        if (new FileInfo(destination).Length != entry.Length) return 24;
                        // Python's matching bytecode depends on the source file timestamp.
                        File.SetLastWriteTime(destination, entry.LastWriteTime.DateTime);
                    }
                }
            }
            return 0;
        }
        catch (Exception error)
        {
            try { File.WriteAllText(Path.Combine(Path.GetTempPath(), "GeneLoop-extract-error-" + Guid.NewGuid().ToString("N") + ".log"), error.ToString()); } catch { }
            return 25;
        }
    }
}
