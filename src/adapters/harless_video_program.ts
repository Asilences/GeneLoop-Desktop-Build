/** Product binding for the original published source-program runtime; no learning algorithm changes. */
import {readFileSync,lstatSync,realpathSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {loadSourceForm} from './source_program_runtime.ts';
import {observeHarnessToolResult} from './dsh_online_motif.mjs';
import type {Scene} from './harless_settings.ts';
const sha=(value:string|Uint8Array)=>createHash('sha256').update(value).digest('hex');
export function videoProgramScene(scene:Scene,mode:string):Scene {
 if(scene.runtime_kind!=='video_program_v1'||mode==='execute')return scene;
 const learned=new Set(scene.video_program_tools??[]),rows=structuredClone(scene.mcp_rows??[]);
 for(const row of rows)if(row.config?.env){row.config.env.GENELOOP_VIDEO_MOTIF_STORE='';row.config.env.GENELOOP_VIDEO_MOTIF_OWNER='';}
 return {...scene,mcp_rows:rows,allowed_tools:scene.allowed_tools.filter(name=>!learned.has(name)),
  certified_tool_schemas:scene.certified_tool_schemas?.filter(row=>!learned.has(row.name)),
  certified_tool_schema_variants:scene.certified_tool_schema_variants?.map(rows=>rows.filter(row=>!learned.has(row.name)))};
}
export function videoProgramUnavailable(scene:Scene):string|null {
 try{
  if(scene.runtime_kind!=='video_program_v1'||scene.adapter!=='video'||scene.id!=='video-editing'||scene.quality_cost_promoted!==true||
   !scene.video_program_store||!scene.video_program_owner||!scene.runtime_library||!scene.video_program_tools?.length||!scene.certified_tool_schemas?.length||
   !scene.video_program_file_locks||Object.keys(scene.video_program_file_locks).length<5)throw Error('missing published binding');
  for(const [path,expected]of Object.entries({...scene.certified_code_locks,...scene.video_program_file_locks})){
   const stat=lstatSync(path);if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1||realpathSync(path)!==path||sha(readFileSync(path))!==expected)throw Error('published file changed');
  }
  const loaded=loadSourceForm(scene.video_program_store,scene.video_program_owner);
  if(loaded.policy.digest!==scene.video_program_policy_digest||loaded.policy.library_digest!==scene.video_program_library_digest||
   loaded.library_path!==scene.runtime_library||sha(readFileSync(loaded.library_path))!==scene.runtime_library_sha256||
   scene.video_program_tools.some(name=>!scene.allowed_tools.includes(name)||!scene.certified_tool_schemas!.some(row=>row.name===name)))throw Error('published binding changed');
  return null;
 }catch{return 'video_program_publication_invalid';}
}
/** Count only successful task-owned renders from the fixed MCP, never predicted skips. */
export function videoProgramReuse(scene:Scene,taskId:string,workspace:string,execution:any,result:any,seen:Set<string>){
 if(scene.runtime_kind!=='video_program_v1'||!scene.video_program_tools?.includes(execution?.name))return null;
 const callId=execution?.callId??execution?.id;
 if(typeof callId!=='string'||!callId||seen.has(callId))return null;
 const value=observeHarnessToolResult(result,execution.name);
 if(!value||value.source_current!==true||value.full_video_decode!==true||
  value.library_digest!==scene.video_program_library_digest||value.policy_digest!==scene.video_program_policy_digest||
  !/^source_[a-f0-9]{24}$/.test(value.program_id??'')||!Array.isArray(value.artifacts))return null;
 try{
  const path=join(workspace,'source-program-audit.jsonl'),stat=lstatSync(path);
  if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1||stat.size>32*1024*1024)return null;
  const rows=readFileSync(path,'utf8').split('\n').filter(Boolean).map(line=>JSON.parse(line));
  const proof=rows.reverse().find(row=>row.kind==='source_program_rendered'&&row.task_id===taskId&&row.program_id===value.program_id&&
   row.library_digest===value.library_digest&&row.policy_digest===value.policy_digest);
  if(!proof||proof.source_current!==true||proof.source_sha256!==value.source_version||
   proof.render?.source_current!==true||proof.render?.full_video_decode!==true||proof.render?.source_version!==value.source_version||
   JSON.stringify(proof.render?.artifacts)!==JSON.stringify(value.artifacts))return null;
  const proofKey='proof:'+sha(JSON.stringify(proof));if(seen.has(proofKey))return null;
  const receiptPath=join(workspace,'outputs/video',taskId,'delivery.json'),receiptStat=lstatSync(receiptPath);
  if(!receiptStat.isFile()||receiptStat.isSymbolicLink()||receiptStat.nlink!==1)return null;
  const receipt=JSON.parse(readFileSync(receiptPath,'utf8'));
  if(receipt.task_id!==taskId||receipt.kind!=='video-delivery-v1'||receipt.full_video_decode!==true||
   receipt.source_version!==value.source_version||JSON.stringify(receipt.files)!==JSON.stringify(value.artifacts))return null;
  for(const row of receipt.files){
   if(!['video.mp4','source.tsx'].some(name=>row.name===`outputs/video/${taskId}/${name}`))return null;
   const file=join(workspace,row.name),st=lstatSync(file);
   if(!st.isFile()||st.isSymbolicLink()||st.nlink!==1||st.size!==row.bytes||sha(readFileSync(file))!==row.sha256)return null;
  }
  if(receipt.files.length!==2||new Set(receipt.files.map((row:any)=>row.name)).size!==2)return null;
  seen.add(proofKey);seen.add(callId);return {kind:'video_program_reused',task_id:taskId,call_id:callId,tool:execution.name,
   program_id:value.program_id,library_digest:value.library_digest,policy_digest:value.policy_digest,source_version:value.source_version};
 }catch{return null;}
}
