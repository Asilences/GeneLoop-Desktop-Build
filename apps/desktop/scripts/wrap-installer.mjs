import {execFileSync} from 'node:child_process';
import {readFileSync,readdirSync,statSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';

const app=fileURLToPath(new URL('../',import.meta.url));
const {version}=JSON.parse(readFileSync(join(app,'package.json'),'utf8'));
const framework=join(process.env.WINDIR||'C:/Windows','Microsoft.NET/Framework64/v4.0.30319');
const release=resolve(app,process.env.GENELOOP_DESKTOP_RELEASE_DIRECTORY||'release');
const prefix='GeneLoop-Desktop-'+version+'-x64';
const compiler=join(framework,'csc.exe');
const require=createRequire(import.meta.url);
if(process.argv[2]!=='--wrap-only'){
  execFileSync(process.execPath,[
    require.resolve('electron-builder/cli.js'),'--win','nsis','--x64','--publish','never',
    '-c.directories.output='+release,...process.argv.slice(2),
  ],{cwd:app,stdio:'inherit',windowsHide:true});
}
const versionSource=join(release,'SetupVersion.cs');
function directoryBytes(directory){
  return readdirSync(directory,{withFileTypes:true}).reduce((bytes,entry)=>{
    const path=join(directory,entry.name);
    return bytes+(entry.isDirectory()?directoryBytes(path):statSync(path).size);
  },0);
}
const payloadBytes=directoryBytes(join(release,'win-unpacked'));
writeFileSync(versionSource,'[assembly: System.Reflection.AssemblyInformationalVersion('+JSON.stringify(version)+')]\n'+
  'internal static class SetupBuild { public const long PayloadBytes = '+payloadBytes+'L; }\n');
execFileSync(compiler,[
  '/nologo','/target:winexe','/platform:x64','/optimize+','/codepage:65001',
  '/out:'+join(release,prefix+'-Setup.exe'),
  '/win32icon:'+join(app,'assets/icon.ico'),
  ...['WindowsBase','PresentationCore','PresentationFramework'].map(name=>'/reference:'+join(framework,'WPF',name+'.dll')),
  '/reference:System.Xaml.dll','/reference:System.Windows.Forms.dll','/reference:Microsoft.CSharp.dll',
  '/resource:'+join(release,prefix+'-Engine.exe')+',GeneLoop.InstallEngine',
  '/resource:'+join(app,'assets/icon.png')+',GeneLoop.Brand',
  join(app,'setup/Installer.cs'),
  versionSource,
],{cwd:app,stdio:'inherit',windowsHide:true});
console.log('Built '+prefix+'-Setup.exe');
