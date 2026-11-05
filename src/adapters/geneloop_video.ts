/** Fixed Remotion recipe; callers cannot select images, mounts, network or credentials. */
import {existsSync,lstatSync,mkdirSync,realpathSync,readFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
export type VideoRenderer={image:string;runtimeRoot:string;mediaToolsRoot:string};
function fixed(path:string){
 if(!path||realpathSync(path)!==resolve(path)||!lstatSync(path).isDirectory()||lstatSync(path).isSymbolicLink()||path.includes(','))throw Error('video requires fixed directories');
 return path;
}
export function videoConfiguration(value:any):VideoRenderer {
 if(!value||Object.keys(value).sort().join(',')!=='image,mediaToolsRoot,runtimeRoot'||!/^sha256:[a-f0-9]{64}$/.test(value.image))throw Error('video renderer must be an immutable installation');
 const runtimeRoot=fixed(value.runtimeRoot),mediaToolsRoot=fixed(value.mediaToolsRoot);
 const pkg=JSON.parse(readFileSync(join(runtimeRoot,'node_modules/remotion/package.json'),'utf8'));
 for(const root of [runtimeRoot,mediaToolsRoot])if(['.env','.npmrc','.credentials.yaml'].some(name=>existsSync(join(root,name))))throw Error('video installation contains private configuration');
 if(pkg.version!=='4.0.539'||!existsSync(join(runtimeRoot,'node_modules/@remotion/cli/remotion-cli.js'))||!existsSync(join(mediaToolsRoot,'node_modules/@ffmpeg-installer/linux-x64/ffmpeg')))throw Error('video runtime dependencies unavailable');
 return {image:value.image,runtimeRoot,mediaToolsRoot};
}
export function videoCommand(output:string,session:string,command:string,renderer:VideoRenderer){
 if(!/^session-[a-f0-9-]{36}$/.test(session)||typeof command!=='string'||!command||Buffer.byteLength(command)>1024*1024)throw Error('invalid owning video Session');
 const root=fixed(output);let work=root;
 for(const part of ['sessions',session,'work'])work=fixed(join(work,part));
 const project=join(work,'remotion');if(!existsSync(project))mkdirSync(project,{mode:0o700});fixed(project);
 for(const part of ['public','node_modules']){const path=join(project,part);if(!existsSync(path))mkdirSync(path,{mode:0o700});fixed(path);}
 return videoProjectCommand(project,command,renderer,session);
}

export function videoProjectCommand(project:string,command:string,renderer:VideoRenderer,session?:string){
 fixed(project);
 fixed(join(project,'public'));
 fixed(join(project,'node_modules'));
 const config=videoConfiguration(renderer),name='geneloop-video-'+randomUUID();
 const labels=session?['--label','geneloop.service=video-web','--label','geneloop.session='+session]:['--label','geneloop.service=desktop-video'];
 return {name,project,argv:['/usr/bin/docker','run','--rm','--name',name,...labels,
 '--user',`${process.getuid!()}:${process.getgid!()}`,'--network','none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=512','--memory=4g','--cpus=2','--shm-size=512m','--tmpfs','/tmp:rw,size=1g',
 '--mount',`type=bind,source=${config.runtimeRoot},target=/runtime,readonly`,
 '--mount',`type=bind,source=${config.mediaToolsRoot},target=/media-tools,readonly`,
 '--mount',`type=bind,source=${project},target=/work${session?'':',readonly'}`,
 '--mount',`type=bind,source=${join(project,'public')},target=/work/public,readonly`,
 '--mount',`type=bind,source=${join(config.runtimeRoot,'node_modules')},target=/work/node_modules,readonly`,
 '--workdir','/work','--env','HOME=/tmp','--env','PATH=/media-tools/node_modules/@ffmpeg-installer/linux-x64:/runtime/node_modules/@remotion/compositor-linux-x64-gnu:/usr/local/bin:/usr/bin:/bin:/home/frappe/.nvm/current/bin',
 '--entrypoint','/bin/sh',config.image,'-c',command]};
}
