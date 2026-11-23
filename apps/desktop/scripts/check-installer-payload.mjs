// Tiny Windows extraction checks; no installation, registry or model requests.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {join,dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {execFileSync,spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
if(process.platform!=='win32'){console.log('Windows installer payload check skipped');process.exit(0);}
const app=fileURLToPath(new URL('../',import.meta.url)),root=fs.realpathSync(fs.mkdtempSync(join(tmpdir(),'GeneLoop-extractor-check-')));
const compiler=join(process.env.SystemRoot,'Microsoft.NET/Framework64/v4.0.30319/csc.exe');
const generator=join(root,'MakeZip.cs'),make=join(root,'MakeZip.exe');
fs.writeFileSync(generator,`using System;using System.IO;using System.IO.Compression;using System.Text;
class MakeZip { static void Main(string[] a) { using(var f=File.Create(a[0])) using(var z=new ZipArchive(f,ZipArchiveMode.Create)) { var e=z.CreateEntry(a[1]); using(var s=e.Open()) {var b=Encoding.UTF8.GetBytes("hello");s.Write(b,0,b.Length);} } } }`);
const run=(bin,args)=>spawnSync(bin,args,{windowsHide:true,encoding:'utf8'});
let junction;
try {
  execFileSync(compiler,['/nologo','/target:exe','/reference:System.IO.Compression.dll','/out:'+make,generator],{windowsHide:true});
  function fixture(name,entry,reuse){
    const archive=join(root,name+'.zip'),constants=join(root,name+'.cs'),exe=join(root,name+'.exe');assert.equal(run(make,[archive,entry]).status,0);
    const sha=createHash('sha256').update(fs.readFileSync(archive)).digest('hex');
    fs.writeFileSync(constants,`static class PayloadBuild { public const string Sha256="${sha}";public const int Files=1;public const long Bytes=5;}`);
    let resources=[];
    if(reuse){const manifest=join(root,name+'.tsv');const encode=value=>Buffer.from(value,'utf8').toString('base64');
      fs.writeFileSync(manifest,'GeneLoopPayloadReuse1\n'+[encode(reuse.part),encode(reuse.name),5,createHash('sha256').update('hello').digest('hex')].join('\t')+'\n');resources=['/resource:'+manifest+',GeneLoop.PayloadReuse'];}
    execFileSync(compiler,['/nologo','/target:winexe','/reference:System.IO.Compression.dll',...resources,'/out:'+exe,join(app,'setup/ExtractPayload.cs'),constants],{windowsHide:true});
    return {archive,exe};
  }
  const good=fixture('unicode','中文/材料.txt'),output=join(root,'result');assert.equal(run(good.exe,[good.archive,output]).status,0);assert.equal(fs.readFileSync(join(output,'中文/材料.txt'),'utf8'),'hello');
  const bad=fixture('traversal','../escape.txt');assert.equal(run(bad.exe,[bad.archive,join(root,'refused')]).status,22);assert.equal(fs.existsSync(join(root,'escape.txt')),false);
  assert.equal(run(good.exe,[bad.archive,join(root,'wrong-hash')]).status,21);assert.equal(fs.existsSync(join(root,'wrong-hash')),false);
  const outside=join(root,'outside');fs.mkdirSync(outside);junction=join(root,'linked');fs.symlinkSync(outside,junction,'junction');
  assert.notEqual(run(good.exe,[good.archive,junction]).status,0);assert.equal(fs.readdirSync(outside).length,0);
  const reusable=fixture('reuse','中文/材料.txt',{part:'中文',name:'材料.txt'});
  for(const [label,original,extra] of [['unchanged','hello',false],['changed','jello',false],['unexpected-file','hello',true]]){
    const previous=join(root,label+'-previous'),destination=join(root,label+'-destination'),log=join(root,label+'.jsonl'),journal=join(root,label+'.journal');
    fs.mkdirSync(join(previous,'中文'),{recursive:true});fs.writeFileSync(join(previous,'中文/材料.txt'),original);
    if(extra)fs.writeFileSync(join(previous,'中文/extra.txt'),'keep in backup');
    assert.equal(run(reusable.exe,[reusable.archive,destination,log,previous,journal]).status,0);
    assert.equal(fs.readFileSync(join(destination,'中文/材料.txt'),'utf8'),'hello');
    if(label==='unchanged'){assert.equal(fs.existsSync(join(previous,'中文')),false);assert.equal(fs.readFileSync(journal,'utf8').trim(),Buffer.from('中文').toString('base64'));}
    else {assert.equal(fs.readFileSync(join(previous,'中文/材料.txt'),'utf8'),original);assert.equal(fs.existsSync(journal),false);}
  }
  console.log(JSON.stringify({unicode:true,traversalDenied:true,wrongHashDeniedBeforeWrites:true,junctionDenied:true,unchangedToolsMoved:true,changedToolsExtracted:true,unexpectedFilesNotReused:true,modelRequests:0}));
} finally {
  if(junction&&fs.existsSync(junction))fs.unlinkSync(junction);
  assert.equal(dirname(root),fs.realpathSync(tmpdir()));fs.rmSync(root,{recursive:true,force:true});
}
