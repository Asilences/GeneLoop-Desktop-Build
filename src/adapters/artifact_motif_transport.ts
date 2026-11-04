/** Shared foreground transport for certified jobs, including member namespaces. */
import {fileURLToPath} from 'node:url';
import {writeFileSync,mkdtempSync} from 'node:fs';
import {join} from 'node:path';
import {spawn} from 'node:child_process';

export function artifactJobArgv(job:any,session:string){
 const {audit,...serializable}=job;
 const payload={...serializable,bound:job.bound.map((b:any)=>({...b,data:b.data.toString('base64')}))};
 const path=join(mkdtempSync(join(job.workspace,'command-tmp','artifact-job-')),'job.json');
 writeFileSync(path,JSON.stringify(payload),{mode:0o600,flag:'wx'});
 const socket=process.env.GENELOOP_COMMAND_SOCKET;
 return socket?[process.execPath,fileURLToPath(new URL('./geneloop_command_client.mjs',import.meta.url)),socket,
  Buffer.from(JSON.stringify({operation:'run',session,file:path})).toString('base64url'),'/artifact']:
  [process.execPath,fileURLToPath(new URL('../../scripts/run-artifact-motif.mjs',import.meta.url)),path];
}

export async function executeArtifactJob(job:any,session:string,signal?:AbortSignal){
 signal?.throwIfAborted();
 const argv=artifactJobArgv(job,session);
 return await new Promise<any>((resolve,reject)=>{
  const child=spawn(argv[0],argv.slice(1),{signal,stdio:['ignore','pipe','pipe']});
  let stdout='',stderr='',overflow=false;
  child.stdout.on('data',chunk=>{stdout+=chunk;if(Buffer.byteLength(stdout)>2_000_000){overflow=true;child.kill();}});
  child.stderr.on('data',chunk=>{stderr=(stderr+chunk).slice(-8000);});
  child.on('error',reject);
  child.on('close',code=>{
   if(overflow||code!==0)return reject(Error('component_execution_failed: '+stderr));
   try{resolve(JSON.parse(stdout.trim()));}catch{reject(Error('component_execution_receipt_invalid'));}
  });
 });
}
