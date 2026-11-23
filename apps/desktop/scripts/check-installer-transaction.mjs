// Real directory operations in an isolated fixture; no installation or registry writes.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {join,dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
if(process.platform!=='win32'){console.log('Windows installer transaction check skipped');process.exit(0);}
const app=fileURLToPath(new URL('../',import.meta.url));
const root=fs.realpathSync(fs.mkdtempSync(join(tmpdir(),'GeneLoop-transaction-check-')));
try {
  fs.writeFileSync(join(root,'Check.cs'),`using System;using System.IO;
class Check {
  static void Require(bool value) { if(!value)throw new Exception("Transaction assertion failed"); }
  static string Old(string root,string id) { var p=Path.Combine(root,id);Directory.CreateDirectory(p);File.WriteAllText(Path.Combine(p,"GeneLoop Desktop.exe"),"old-app");File.WriteAllText(Path.Combine(p,"Uninstall GeneLoop Desktop.exe"),"old-uninstaller");Directory.CreateDirectory(Path.Combine(p,"resources"));File.WriteAllText(Path.Combine(p,"resources","unchanged.txt"),"old-payload");return p; }
  static string Stage(string root,string id) { var p=Path.Combine(root,id);Directory.CreateDirectory(p);InstallTransaction.SecureStage(p);return p; }
  static void Main(string[] a) {
    var root=a[0];var old=Old(root,"rollback-old");var stage=Stage(root,"rollback-stage");
    using(var tx=new InstallTransaction(old,old,stage,null)) {tx.Prepare(false);Require(tx.HasBackup);Require(new FileInfo(Path.Combine(old,"GeneLoop Desktop.exe")).Length==0);File.WriteAllText(tx.ReuseJournal,Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes("resources"))+"\\n");Directory.Move(Path.Combine(tx.PreviousDirectory,"resources"),Path.Combine(old,"resources"));File.WriteAllText(Path.Combine(old,"GeneLoop Desktop.exe"),"partial-new");}
    Require(File.ReadAllText(Path.Combine(old,"GeneLoop Desktop.exe"))=="old-app");Require(File.ReadAllText(Path.Combine(old,"resources","unchanged.txt"))=="old-payload");
    old=Old(root,"commit-old");stage=Stage(root,"commit-stage");
    using(var tx=new InstallTransaction(old,old,stage,null)) {tx.Prepare(false);File.WriteAllText(Path.Combine(old,"GeneLoop Desktop.exe"),"new-app");tx.Commit();}
    Require(File.ReadAllText(Path.Combine(old,"GeneLoop Desktop.exe"))=="new-app");Require(File.ReadAllText(Path.Combine(stage,"previous-install","resources","unchanged.txt"))=="old-payload");
    old=Old(root,"changed-old");stage=Stage(root,"changed-stage");var target=Path.Combine(root,"changed-target");
    using(var tx=new InstallTransaction(old,target,stage,null)) {tx.Prepare(false);Directory.CreateDirectory(target);File.WriteAllText(Path.Combine(target,"partial.txt"),"new");}
    Require(File.ReadAllText(Path.Combine(old,"GeneLoop Desktop.exe"))=="old-app");Require(!Directory.Exists(target));
    var nested=Path.Combine(old,"nested");bool refused=false;
    try {using(var tx=new InstallTransaction(old,nested,stage,null))tx.Prepare(false);}catch(IOException){refused=true;}
    Require(refused);Require(File.ReadAllText(Path.Combine(old,"GeneLoop Desktop.exe"))=="old-app");
    refused=false;try {using(var tx=new InstallTransaction(old,Path.GetPathRoot(root),stage,null))tx.Prepare(false);}catch(IOException){refused=true;}Require(refused);
    Console.WriteLine("rollback, commit, changed-destination rollback, overlap and root guards passed");
  }
}`);
  const exe=join(root,'Check.exe');
  execFileSync(join(process.env.SystemRoot,'Microsoft.NET/Framework64/v4.0.30319/csc.exe'),['/nologo','/target:exe','/out:'+exe,join(root,'Check.cs'),join(app,'setup/InstallTransaction.cs')],{windowsHide:true,stdio:'pipe'});
  execFileSync(exe,[root],{windowsHide:true,stdio:'inherit'});
  assert.equal(fs.readdirSync(root).some(x=>x.startsWith('changed-target.GeneLoop-failed-')),true);
  console.log(JSON.stringify({wholeDirectoryRollback:true,reusedToolRollback:true,committedBackupRetained:true,changedDestinationRollback:true,overlappingPathsDenied:true,driveRootDenied:true,registryWrites:0,modelRequests:0}));
} finally {
  assert.equal(dirname(root),fs.realpathSync(tmpdir()));fs.rmSync(root,{recursive:true,force:true});
}
