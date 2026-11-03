import {execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';

const app=fileURLToPath(new URL('../',import.meta.url));
const {version}=JSON.parse(readFileSync(join(app,'package.json'),'utf8'));
const framework=join(process.env.WINDIR||'C:/Windows','Microsoft.NET/Framework64/v4.0.30319');
const release=join(app,'release');
const prefix='GeneLoop-Desktop-'+version+'-x64';
const compiler=join(framework,'csc.exe');
const require=createRequire(import.meta.url);
if(process.argv[2]!=='--wrap-only'){
  execFileSync(process.execPath,[
    require.resolve('electron-builder/cli.js'),'--win','nsis','--x64','--publish','never',...process.argv.slice(2),
  ],{cwd:app,stdio:'inherit',windowsHide:true});
}
const versionSource=join(release,'SetupVersion.cs');
writeFileSync(versionSource,'[assembly: System.Reflection.AssemblyInformationalVersion('+JSON.stringify(version)+')]\n');
execFileSync(compiler,[
  '/nologo','/target:winexe','/platform:x64','/optimize+','/codepage:65001',
  '/out:'+join(release,prefix+'-Setup.exe'),
  '/win32icon:'+join(app,'assets/icon.ico'),
  ...['WindowsBase','PresentationCore','PresentationFramework'].map(name=>'/reference:'+join(framework,'WPF',name+'.dll')),
  '/reference:System.Xaml.dll','/reference:System.Windows.Forms.dll',
  '/resource:'+join(release,prefix+'-Engine.exe')+',GeneLoop.InstallEngine',
  '/resource:'+join(app,'assets/icon.png')+',GeneLoop.Brand',
  join(app,'setup/Installer.cs'),
  versionSource,
],{cwd:app,stdio:'inherit',windowsHide:true});
console.log('Built '+prefix+'-Setup.exe');
