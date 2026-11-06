import assert from 'node:assert/strict';
import fs from 'node:fs';
import {join,resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';

// NSIS retains upgrade, permissions, process checks and registration. The payload
// is written once by .NET: the legacy nsisunz plugin corrupts UTF-8 member names.
export async function buildWindowsEngine(app,release,compiler,extraArgs) {
  const require=createRequire(join(app,'package.json')),cli=require.resolve('electron-builder/cli.js');
  const options=[...extraArgs],at=options.indexOf('--prepackaged');
  const packed=at>=0?resolve(app,options.splice(at,2)[1]):join(release,'win-unpacked');
  if(at<0) execFileSync(process.execPath,[cli,'--win','--dir','--x64','--publish','never','-c.directories.output='+release,...options],{cwd:app,stdio:'inherit',windowsHide:true});
  let bytes=0,files=0;
  function count(directory){for(const item of fs.readdirSync(directory,{withFileTypes:true})){const file=join(directory,item.name);assert.ok(!item.isSymbolicLink(),'载荷不接受链接');if(item.isDirectory())count(file);else{files++;bytes+=fs.statSync(file).size;}}}count(packed);
  const payload=process.env.GENELOOP_REUSE_WINDOWS_PAYLOAD?resolve(process.env.GENELOOP_REUSE_WINDOWS_PAYLOAD):join(release,'windows-payload.zip');
  if(!process.env.GENELOOP_REUSE_WINDOWS_PAYLOAD){
    const {archive}=require('app-builder-lib/out/targets/archive.js');
    const previous=process.env.ELECTRON_BUILDER_COMPRESSION_LEVEL;process.env.ELECTRON_BUILDER_COMPRESSION_LEVEL=previous??'1';
    try{await archive('zip',payload,packed,{withoutDir:true,compression:'normal'});}finally{if(previous===undefined)delete process.env.ELECTRON_BUILDER_COMPRESSION_LEVEL;else process.env.ELECTRON_BUILDER_COMPRESSION_LEVEL=previous;}
  }
  const hash=createHash('sha256');for await(const chunk of fs.createReadStream(payload))hash.update(chunk);const sha256=hash.digest('hex');
  const constants=join(release,'PayloadBuild.cs'),extractor=join(release,'GeneLoopExtract.exe');
  fs.writeFileSync(constants,`internal static class PayloadBuild { public const string Sha256 = "${sha256}"; public const long Bytes = ${bytes}L; public const int Files = ${files}; }\n`);
  execFileSync(compiler,['/nologo','/target:winexe','/platform:x64','/optimize+','/codepage:65001','/reference:System.IO.Compression.dll','/out:'+extractor,join(app,'setup/ExtractPayload.cs'),constants],{cwd:app,stdio:'inherit',windowsHide:true});
  const bootstrap=join(release,'nsis-bootstrap');fs.mkdirSync(join(bootstrap,'resources'),{recursive:true});fs.writeFileSync(join(bootstrap,'.geneloop-bootstrap'),'installer bootstrap\n');
  const include=join(release,'direct-payload.nsh');
  fs.writeFileSync(include,`!ifdef ESTIMATED_SIZE
!undef ESTIMATED_SIZE
!endif
!define ESTIMATED_SIZE ${Math.ceil(bytes/1024)}
!ifdef APP_64_UNPACKED_SIZE
!undef APP_64_UNPACKED_SIZE
!endif
!define APP_64_UNPACKED_SIZE ${Math.ceil(bytes/1024)}
!include "${join(app,'installer.nsh')}"
!macro customFiles_x64
  SetCompress off
  File /oname=$PLUGINSDIR\\GeneLoopPayload.zip "${payload}"
  File /oname=$PLUGINSDIR\\GeneLoopExtract.exe "${extractor}"
  !ifdef COMPRESS
    SetCompress "\${COMPRESS}"
  !endif
  ExecWait '\"$PLUGINSDIR\\GeneLoopExtract.exe\" \"$PLUGINSDIR\\GeneLoopPayload.zip\" \"$INSTDIR\"' $R0
  \${If} $R0 != 0
    SetErrorLevel $R0
    Quit
  \${EndIf}
  Delete "$INSTDIR\\.geneloop-bootstrap"
!macroend
`);
  execFileSync(process.execPath,[cli,'--win','nsis','--x64','--publish','never','--prepackaged',bootstrap,'-c.directories.output='+release,'-c.nsis.include='+include,'-c.nsis.packElevateHelper=false','-c.nsis.differentialPackage=false',...options],{cwd:app,stdio:'inherit',windowsHide:true});
  fs.writeFileSync(join(release,'direct-payload.json'),JSON.stringify({schema:1,files,bytes,sha256,payload,extractor,packed,method:'NSIS lifecycle + verified .NET ZIP direct extraction'},null,2)+'\n');
  return bytes;
}
