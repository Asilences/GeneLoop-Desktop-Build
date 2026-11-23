/** Harness tool registration for the existing paper and video business code. */
import {spawn} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {revisionTools} from '../../scenarios/paper_proofreading/revision_session.ts';

const root=fileURLToPath(new URL('../../',import.meta.url));
const paper=JSON.parse(readFileSync(new URL('../../scenarios/paper_proofreading/native-tool-schemas.json',import.meta.url),'utf8'));
const video=JSON.parse(readFileSync(new URL('../../scenarios/remotion_edit/web-tool-schemas.json',import.meta.url),'utf8'));
const render=(_args:any,value:any)=>value.content;

export async function callNativeScene(request:any,signal?:AbortSignal,python=process.env.SSS_PYTHON??'python3'){
 return await new Promise<any>((resolve,reject)=>{
  const child=spawn(python,['-m','scenarios.native_scene_call'],{cwd:root,stdio:['pipe','pipe','pipe'],
   env:{...process.env,...request.native_environment,PYTHONUNBUFFERED:'1'}});
  let stdout='',stderr='',overflow=false,settled=false;
  const finish=(error?:Error,value?:any)=>{if(settled)return;settled=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);error?reject(error):resolve(value);};
  const abort=()=>{child.kill();finish(Error('native_scene_cancelled'));};
  signal?.addEventListener('abort',abort,{once:true});
  const timer=setTimeout(()=>{child.kill();finish(Error('native_scene_timeout'));},request.scene==='video'?660000:180000);
  child.stdout.on('data',(chunk:Buffer)=>{stdout+=chunk.toString('utf8');if(stdout.length>64_000_000){overflow=true;child.kill();}});
  child.stderr.on('data',(chunk:Buffer)=>{stderr=(stderr+chunk.toString('utf8')).slice(-4000);});
  child.once('error',error=>finish(error));
  child.once('close',code=>{
   if(overflow||code!==0)return finish(Error('native_scene_execution_failed: '+stderr));
   try{finish(undefined,JSON.parse(stdout));}catch{finish(Error('native_scene_receipt_invalid'));}
  });
  child.stdin.on('error',()=>{});child.stdin.end(JSON.stringify(request));
 });
}

export function registerNativeSceneTools(ctx:any,scenes:any[],current:(session:string)=>any,privateRoot:string,python?:string){
 const paperScene=scenes.find(scene=>scene.id==='paper-proofreading'&&scene.mcp_rows?.length===0);
 const videoScene=scenes.find(scene=>scene.id==='video-editing'&&scene.mcp_rows?.length===0);
 const learned=(videoScene?.certified_tool_schemas??[]).filter((row:any)=>videoScene.video_program_tools?.includes(row.name));
 const schemas=[...(paperScene?paper:[]),...(videoScene?[...video,...learned]:[])];
 for(const schema of schemas){
  ctx.tools.register({...schema,output:{schema:{type:'object'},render},
   async execute(args:any,execution:any){
    const task=current(execution?.agent?.session?.id);
    const kind=schema.name.startsWith('mcp__paper_')?'paper':'video';
    const sceneId=kind==='paper'?'paper-proofreading':'video-editing';
    if(!task||task.status!=='running'||task.scene?.id!==sceneId||!task.scene.allowed_tools.includes(schema.name))
     throw Error('native_scene_task_not_authorized');
    if(schema.name.startsWith('mcp__paper_trace_rsi__')){
     const api=revisionTools(task.workspace,privateRoot);
     const value=api.call(schema.name.slice('mcp__paper_trace_rsi__'.length),args);
     return {content:[{type:'text',text:JSON.stringify(value)}],structuredContent:value};
    }
    const result=await callNativeScene({scene:kind,workspace:task.workspace,tool:schema.name,arguments:args,
     renderer_root:task.scene.paper_renderer_root,private_root:privateRoot,
     native_environment:task.scene.native_environment??{},
     program_store:task.request.mode==='execute'?task.scene.video_program_store:undefined,
     program_owner:task.request.mode==='execute'?task.scene.video_program_owner:undefined},execution.signal,python);
    if(result.isError)throw Error(result.content?.filter((row:any)=>row.type==='text').map((row:any)=>row.text).join('\n')||'native_scene_tool_failed');
    return result;
   }});
 }
 return schemas.map((row:any)=>row.name);
}
