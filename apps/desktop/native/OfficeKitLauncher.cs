// The parent supplies its trusted Electron/Node executable. No system lookup,
// shell, engine download, cloud fallback, or second Agent runtime.
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
internal static class OfficeKitLauncher {
  static string Quote(string value) {
    var b=new StringBuilder("\"");int n=0;
    foreach(char c in value){if(c=='\\'){n++;continue;}
      if(c=='"'){b.Append('\\',n*2+1);b.Append(c);}else{b.Append('\\',n);b.Append(c);}n=0;}
    b.Append('\\',n*2);return b.Append('"').ToString();
  }
  public static int Main(string[] args) {
    try {
      string node=Environment.GetEnvironmentVariable("GENELOOP_OFFICE_NODE");
      if(String.IsNullOrEmpty(node)||!Path.IsPathRooted(node)||!File.Exists(node))throw new Exception("本机 Office 宿主未配置。");
      string root=Directory.GetParent(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location)).FullName;
      var p=new ProcessStartInfo(node,String.Join(" ",new[]{Path.Combine(root,"bridge.mjs")}.Concat(args).Select(Quote)));
      p.UseShellExecute=false;p.CreateNoWindow=true;p.RedirectStandardOutput=true;p.RedirectStandardError=true;
      p.EnvironmentVariables["ELECTRON_RUN_AS_NODE"]="1";
      using(var child=Process.Start(p)){var output=child.StandardOutput.ReadToEndAsync();var error=child.StandardError.ReadToEndAsync();
        child.WaitForExit();Console.Out.Write(output.Result);Console.Error.Write(error.Result);return child.ExitCode;}
    }catch(Exception e){Console.Error.WriteLine(e.Message);return 127;}
  }
}
