/** Native research IO, extracted from ChartMimic bd05847.
 * Learning/certification/Runtime stay upstream. GENELOOP_CHART_* is compatible. */
import {spawn} from 'node:child_process';
import {appendFileSync,readFileSync,realpathSync,mkdirSync,cpSync,readdirSync,lstatSync,writeFileSync} from 'node:fs';
import {resolve,relative,isAbsolute,extname,basename,join,posix} from 'node:path';
import {createHash} from 'node:crypto';

export const name='research-native-tools';
export const inject=['tools'];
const sha=(data:Buffer)=>createHash('sha256').update(data).digest('hex');
export function apply(ctx:any){
 const container=(process.env.GENELOOP_RESEARCH_CONTAINER??process.env.GENELOOP_CHART_CONTAINER)!;
 const workspace=realpathSync((process.env.GENELOOP_RESEARCH_WORKSPACE??process.env.GENELOOP_CHART_WORKSPACE)!);
 const output=realpathSync((process.env.GENELOOP_RESEARCH_RUN??process.env.GENELOOP_CHART_RUN)!);
 const workdir=process.env.GENELOOP_RESEARCH_WORKDIR??'/work';
 if(!workdir.startsWith('/')||posix.resolve(workdir)!==workdir||workdir==='/')throw Error('research_workdir_invalid');
 const imageRoots=JSON.parse(process.env.GENELOOP_RESEARCH_IMAGE_ROOTS??'[]');
 if(!Array.isArray(imageRoots)||imageRoots.some((row:any)=>!row||typeof row.virtual!=='string'||
   !row.virtual.startsWith('/')||posix.resolve(row.virtual)!==row.virtual||row.virtual==='/'||row.virtual===workdir||typeof row.host!=='string'))
  throw Error('research_image_roots_invalid');
 for(const row of imageRoots)row.host=realpathSync(row.host);
 const record=(row:any)=>appendFileSync(join(output,'native-tools.jsonl'),JSON.stringify(row)+'\n',{mode:0o600});
 let sequence=0;
 // Same /work namespaces and bounds as SkillsBenchTrial.capture_learning_boundary.
 // This is evidence copying; it grants no candidate execution authority.
 function boundary(call:string,phase:string){
  const target=join(output,'learning-boundaries',call+(phase==='after'?'-after':''),'workspace');
  mkdirSync(target,{recursive:true,mode:0o700});
  mkdirSync(join(target,'command-tmp'),{mode:0o700});
  const files:Record<string,any>={};let total=0,complete=true;
  const walk=(source:string,destination:string)=>{
   mkdirSync(destination,{recursive:true});
   for(const entry of readdirSync(source,{withFileTypes:true})){
    const src=join(source,entry.name),dst=join(destination,entry.name);
    if(entry.isSymbolicLink()){complete=false;continue;}
    if(entry.isDirectory()){walk(src,dst);continue;}
    if(!entry.isFile()){complete=false;continue;}
    const bytes=lstatSync(src).size;total+=bytes;
    if(bytes>1_000_000||total>8_000_000||Object.keys(files).length>=256){complete=false;continue;}
    cpSync(src,dst);files[relative(target,dst)]={path:dst,sha256:sha(readFileSync(dst))};
   }
  };
  for(const folder of ['inputs','code','outputs/code'])walk(join(workspace,folder),join(target,folder));
  const value={call_id:call,workdir,workspace:target,[phase]:{complete,files,scope:'bounded_original_task_workdir_'+phase+'_execute'}};
  const path=join(output,'learning-boundaries',call+(phase==='after'?'-after':''),'boundary.json');
  writeFileSync(path,JSON.stringify(value),{mode:0o600});return {path,sha256:sha(readFileSync(path))};
 }
 ctx.tools.register({name:'execute',description:process.env.GENELOOP_RESEARCH_EXECUTE_DESCRIPTION??'Run a shell command in the isolated task workspace. Python, Matplotlib, NumPy and ordinary command-line tools are available.',
  parameters:{type:'object',properties:{command:{type:'string'}},required:['command'],additionalProperties:false},
  output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(value)}]},
  async execute(args:any,execution:any){
   const call='call-'+(++sequence),started=Date.now(),before=boundary(call,'before');
   record({phase:'started',name:'execute',call_id:execution.callId,sequence:call,arguments:args,boundary:before});
   try{
    const result=await new Promise<any>((done,reject)=>{
     const child=spawn('docker',['exec','-w',workdir,container,'bash','-lc',args.command],{stdio:['ignore','pipe','pipe'],signal:execution.signal});
     let stdout='',stderr='';child.stdout.on('data',(b:Buffer)=>stdout+=b.toString());child.stderr.on('data',(b:Buffer)=>stderr+=b.toString());
     child.once('error',reject);child.once('close',returncode=>done({returncode,stdout,stderr}));
    });
    record({phase:'finished',name:'execute',call_id:execution.callId,sequence:call,arguments:args,result,boundary:before,
     after_boundary:boundary(call,'after'),elapsed_ms:Date.now()-started});
    return result;
   }catch(error){record({phase:'failed',name:'execute',call_id:execution.callId,sequence:call,error:String(error),boundary:before});throw error;}
  }});
 ctx.tools.register({name:'read_image',description:'Inspect the actual PNG/JPEG pixels of a task input or your rendered output.',
  parameters:{type:'object',properties:{file_path:{type:'string'}},required:['file_path'],additionalProperties:false},
  output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:value.path},{type:'image',attachment:value.image}]},
  async execute(args:any,execution:any){
   const virtual=posix.resolve(workdir,args.file_path),rel=posix.relative(workdir,virtual);
   let host:string,allowed:string;
   if(!rel.startsWith('..')&&!posix.isAbsolute(rel)){
    host=resolve(workspace,rel.startsWith('inputs/')?rel:rel.startsWith('outputs/')?'outputs/code/'+rel.slice(8):'code/'+rel);
    allowed=workspace;
   }else{
    const extra=imageRoots.filter((row:any)=>virtual.startsWith(row.virtual+'/'));
    if(extra.length!==1)throw Error('chart_image_outside_workspace');
    host=resolve(extra[0].host,virtual.slice(extra[0].virtual.length+1));allowed=extra[0].host;
   }
   const path=realpathSync(host),inside=relative(allowed,path);
   if(inside.startsWith('..')||isAbsolute(inside)||!['.png','.jpg','.jpeg'].includes(extname(path).toLowerCase()))throw Error('chart_image_not_regular_input');
   const data=readFileSync(path),attachments=ctx.get('attachments');
   if(!attachments)throw Error('chart_image_attachment_service_missing');
   const image=await attachments.saveImage({data,mediaType:extname(path).toLowerCase()==='.png'?'image/png':'image/jpeg',name:basename(path)});
   record({phase:'finished',name:'read_image',call_id:execution.callId,arguments:args,image_sha256:sha(data),image_bytes:data.length});
   return {path:virtual,image};
  }});
}
