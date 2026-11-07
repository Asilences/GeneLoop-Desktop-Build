using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Diagnostics;
using System.Reflection;
using System.Globalization;

internal static class ExtractPayload
{
    private static string trace;
    private static readonly Stopwatch elapsed = Stopwatch.StartNew();
    private static void Record(string phase, long files = 0, long bytes = 0)
    {
        if (String.IsNullOrEmpty(trace)) return;
        try { File.AppendAllText(trace, "{\"phase\":\"" + phase + "\",\"elapsed_ms\":" + elapsed.ElapsedMilliseconds + ",\"files\":" + files + ",\"bytes\":" + bytes + "}\n"); } catch { }
    }
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
            if (args.Length != 2 && args.Length != 3 && args.Length != 5) return 20;
            trace = args.Length >= 3 ? args[2] : null;
            Record("extract_start");
            var root = Path.GetFullPath(args[1]).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            // ZipArchive seeks to each member's local header. A 128 KiB input
            // buffer rereads many neighbouring small members after every seek
            // (several GB for a 976 MB archive). Keep metadata reads small;
            // CopyTo's separate large write buffer still handles file data.
            using (var input = new FileStream(args[0], FileMode.Open, FileAccess.Read, FileShare.Read, 4096, FileOptions.None))
            {
                using (var sha = SHA256.Create())
                    if (BitConverter.ToString(sha.ComputeHash(input)).Replace("-", "").ToLowerInvariant() != PayloadBuild.Sha256) return 21;
                Record("payload_verified");
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
                    Record("paths_validated", paths.Count, total);
                    var directories = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    CheckDirectory(root.TrimEnd(Path.DirectorySeparatorChar), directories);
                    var reused = args.Length == 5 ? ReuseTools(root, args[3], args[4], paths, directories) : new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    long written = 0, count = 0;
                    var buffer = new byte[65536];
                    foreach (var pair in paths)
                    {
                        var entry = pair.Key; var destination = pair.Value;
                        bool kept = false;
                        foreach (var prefix in reused) if (destination.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) { kept = true; break; }
                        if (kept) { count++; written += entry.Length; continue; }
                        CheckDirectory(Path.GetDirectoryName(destination), directories);
                        if (File.Exists(destination) && (File.GetAttributes(destination) & FileAttributes.ReparsePoint) != 0) return 22;
                        using (var from = entry.Open())
                        using (var to = new FileStream(destination, FileMode.Create, FileAccess.Write, FileShare.None, 4096, FileOptions.SequentialScan))
                        { int length; while ((length = from.Read(buffer, 0, buffer.Length)) != 0) to.Write(buffer, 0, length); }
                        if (new FileInfo(destination).Length != entry.Length) return 24;
                        // Python's matching bytecode depends on the source file timestamp.
                        File.SetLastWriteTime(destination, entry.LastWriteTime.DateTime);
                        count++; written += entry.Length;
                        if (count % 2000 == 0) Record("files_written", count, written);
                    }
                    Record("extract_complete", count, written);
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

    private sealed class Member { internal string Name, Sha; internal long Bytes; }
    private static string Relative(string value)
    {
        var path = Encoding.UTF8.GetString(Convert.FromBase64String(value)).Replace('/', '\\');
        if (Path.IsPathRooted(path) || path.IndexOf(':') >= 0 || path.IndexOf('\0') >= 0) throw new IOException("工具清单路径无效");
        foreach (var part in path.Split('\\')) if (part.Length == 0 || part == "." || part == ".." || part.EndsWith(" ") || part.EndsWith(".")) throw new IOException("工具清单路径无效");
        return path;
    }
    private static bool PlainFiles(string directory, Dictionary<string, Member> expected)
    {
        var pending = new Stack<string>(); pending.Push(directory);
        int found = 0;
        using (var sha = SHA256.Create())
        while (pending.Count != 0)
        {
            var at = pending.Pop();
            if ((File.GetAttributes(at) & FileAttributes.ReparsePoint) != 0) return false;
            foreach (var path in Directory.EnumerateFileSystemEntries(at))
            {
                var attributes = File.GetAttributes(path);
                if ((attributes & FileAttributes.ReparsePoint) != 0) return false;
                if ((attributes & FileAttributes.Directory) != 0) { pending.Push(path); continue; }
                Member member;
                if (!expected.TryGetValue(path.Substring(directory.Length + 1), out member) || new FileInfo(path).Length != member.Bytes) return false;
                using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 4096, FileOptions.SequentialScan))
                    if (BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant() != member.Sha) return false;
                found++;
            }
        }
        return found == expected.Count;
    }
    private static HashSet<string> ReuseTools(string root, string previous, string journal,
        Dictionary<ZipArchiveEntry, string> paths, HashSet<string> directories)
    {
        var reused = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (String.IsNullOrWhiteSpace(previous) || String.IsNullOrWhiteSpace(journal) || !Directory.Exists(previous)) return reused;
        previous = Path.GetFullPath(previous).TrimEnd('\\');
        if (!String.Equals(Path.GetPathRoot(root), Path.GetPathRoot(previous), StringComparison.OrdinalIgnoreCase)) return reused;
        var groups = new Dictionary<string, Dictionary<string, Member>>(StringComparer.OrdinalIgnoreCase);
        using (var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("GeneLoop.PayloadReuse"))
        {
            if (resource == null) return reused;
            using (var reader = new StreamReader(resource, Encoding.UTF8))
            {
                if (reader.ReadLine() != "GeneLoopPayloadReuse1") throw new IOException("工具清单版本无效");
                string line;
                while ((line = reader.ReadLine()) != null)
                {
                    if (line.Length == 0) continue;
                    var fields = line.Split('\t'); if (fields.Length != 4) throw new IOException("工具清单无效");
                    var part = Relative(fields[0]); var name = Relative(fields[1]);
                    Dictionary<string, Member> members;
                    if (!groups.TryGetValue(part, out members)) groups.Add(part, members = new Dictionary<string, Member>(StringComparer.OrdinalIgnoreCase));
                    members.Add(name, new Member { Name = name, Bytes = Int64.Parse(fields[2], CultureInfo.InvariantCulture), Sha = fields[3] });
                }
            }
        }
        long count = 0, bytes = 0;
        foreach (var group in groups)
        {
            var destination = Path.Combine(root, group.Key); var source = Path.Combine(previous, group.Key);
            if (!Directory.Exists(source) || Directory.Exists(destination) || File.Exists(destination)) continue;
            bool plain = true;
            for (var at = source; at != null && at.Length >= previous.Length; at = Path.GetDirectoryName(at))
                if ((File.GetAttributes(at) & FileAttributes.ReparsePoint) != 0) { plain = false; break; }
            if (!plain) continue;
            // The embedded roster must describe exactly this archive's subtree.
            int archived = 0;
            foreach (var pair in paths) if (pair.Value.StartsWith(destination + "\\", StringComparison.OrdinalIgnoreCase))
            {
                Member member;
                if (!group.Value.TryGetValue(pair.Value.Substring(destination.Length + 1), out member) || member.Bytes != pair.Key.Length) throw new IOException("工具清单与安装包不一致");
                archived++;
            }
            if (archived != group.Value.Count) throw new IOException("工具清单与安装包不一致");
            Record("checking_existing_tools", count, bytes);
            bool matches;
            try { matches = PlainFiles(source, group.Value); }
            catch (IOException) { matches = false; }
            catch (UnauthorizedAccessException) { matches = false; }
            if (!matches) continue;
            CheckDirectory(Path.GetDirectoryName(destination), directories);
            // Persist intent before the atomic move so the parent can restore
            // reused directories even when extraction fails immediately after it.
            var intent = Encoding.UTF8.GetBytes(Convert.ToBase64String(Encoding.UTF8.GetBytes(group.Key)) + "\n");
            using (var output = new FileStream(journal, FileMode.Append, FileAccess.Write, FileShare.Read, 4096, FileOptions.WriteThrough))
            { output.Write(intent, 0, intent.Length); output.Flush(true); }
            Directory.Move(source, destination);
            reused.Add(destination + "\\");
            foreach (var member in group.Value.Values) { count++; bytes += member.Bytes; }
            Record("existing_tools_reused", count, bytes);
        }
        return reused;
    }
}
