// Preserve Chromium's own Windows renderer sandbox. Remotion normally adds
// --no-sandbox; remove that flag rather than nesting Chromium under DSH's
// WRITE_RESTRICTED token, which cannot create Chromium's Mojo named pipes.
// Trusted build tools remain in the DSH managed process range. No Agent loop.
using System;
using System.Diagnostics;
using System.Linq;
using System.Text;
using System.Web.Script.Serialization;
using System.Runtime.InteropServices;
internal static class RemotionBrowser {
  [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct StartupInfo {
    public int cb; public string reserved,desktop,title;
    public int x,y,width,height,xChars,yChars,fill,flags;
    public short show,reservedBytes; public IntPtr reserved2,input,output,error;
  }
  [StructLayout(LayoutKind.Sequential)] struct ProcessInfo { public IntPtr process,thread; public int pid,tid; }
  [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int kind);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcessW(
    string app,StringBuilder command,IntPtr processSecurity,IntPtr threadSecurity,bool inherit,int flags,
    IntPtr environment,string directory,ref StartupInfo startup,out ProcessInfo process);
  [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr handle,uint timeout);
  [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr handle,out uint code);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
  private static string Quote(string value) {
    var result = new StringBuilder("\""); int slashes = 0;
    foreach (char ch in value) {
      if (ch == '\\') { slashes++; continue; }
      if (ch == '"') { result.Append('\\', slashes * 2 + 1); result.Append(ch); }
      else { result.Append('\\', slashes); result.Append(ch); }
      slashes = 0;
    }
    result.Append('\\', slashes * 2); return result.Append('"').ToString();
  }
  public static int Main(string[] args) {
    try {
      string raw = Environment.GetEnvironmentVariable("GENELOOP_REMOTION_BROWSER_PREFIX");
      var prefix = new JavaScriptSerializer().Deserialize<string[]>(raw ?? "[]");
      if (prefix.Length != 1) throw new InvalidOperationException("Missing browser executable");
      var start = new StartupInfo(); start.cb=Marshal.SizeOf(start); start.flags=0x100;
      start.input=GetStdHandle(-10);start.output=GetStdHandle(-11);start.error=GetStdHandle(-12);
      ProcessInfo child;
      var safeArgs=args.Where(arg => arg != "--no-sandbox" && arg != "--disable-setuid-sandbox");
      var command = new StringBuilder(String.Join(" ", prefix.Concat(safeArgs).Select(Quote)));
      if(!CreateProcessW(null,command,IntPtr.Zero,IntPtr.Zero,true,0x08000000,IntPtr.Zero,null,ref start,out child))
        throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
      try {WaitForSingleObject(child.process,0xffffffff);uint code;GetExitCodeProcess(child.process,out code);return (int)code;}
      finally {CloseHandle(child.thread);CloseHandle(child.process);}
    } catch (Exception error) { Console.Error.WriteLine("GeneLoop browser: " + error.Message); return 127; }
  }
}
