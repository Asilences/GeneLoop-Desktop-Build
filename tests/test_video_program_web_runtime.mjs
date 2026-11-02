import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
const options={skip:!process.features?.typescript};
const sha=value=>createHash('sha256').update(value).digest('hex');
const name='mcp__remotion__reuse_test',program='source_'+'a'.repeat(24);
const base=()=>({id:'video-editing',adapter:'video',runtime_kind:'video_program_v1',
 video_program_tools:[name],video_program_library_digest:'a'.repeat(64),video_program_policy_digest:'b'.repeat(64),
 video_program_agent_instruction:'Same comparison instruction',
 allowed_tools:['mcp__remotion__read_source',name],certified_tool_schemas:[{name:'mcp__remotion__read_source'},{name}],
 mcp_rows:[{config:{env:{HARLESS_PRIVATE_ROOT:'/private',GENELOOP_VIDEO_MOTIF_STORE:'/published',GENELOOP_VIDEO_MOTIF_OWNER:'owner'}}}]});
test('video baseline cannot inherit published tools or store authority; optimized scene remains immutable',options,async()=>{
 const {videoProgramScene}=await import('../src/adapters/harless_video_program.ts');const scene=base(),before=structuredClone(scene);
 const baseline=videoProgramScene(scene,'baseline');
 assert.deepEqual(baseline.allowed_tools,['mcp__remotion__read_source']);assert.deepEqual(baseline.certified_tool_schemas,[{name:'mcp__remotion__read_source'}]);
 assert.equal(baseline.mcp_rows[0].config.env.GENELOOP_VIDEO_MOTIF_STORE,'');assert.equal(baseline.mcp_rows[0].config.env.GENELOOP_VIDEO_MOTIF_OWNER,'');
 assert.equal(baseline.mcp_rows[0].config.env.HARLESS_PRIVATE_ROOT,'/private');
 assert.equal(baseline.video_program_agent_instruction,scene.video_program_agent_instruction);
 assert.equal(videoProgramScene(scene,'execute'),scene);assert.deepEqual(scene,before);
 assert.deepEqual(videoProgramScene(scene,'shadow'),baseline);
});
test('missing or unaccepted publication cannot enable video program mode',options,async()=>{
 const {videoProgramUnavailable}=await import('../src/adapters/harless_video_program.ts');
 assert.equal(videoProgramUnavailable(base()),'video_program_publication_invalid');
 assert.equal(videoProgramUnavailable({...base(),quality_cost_promoted:false}),'video_program_publication_invalid');
});
function fixture(){
 const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-program-web-'))),task='c'.repeat(32),folder=join(root,'outputs/video',task);mkdirSync(folder,{recursive:true});
 const files=['video.mp4','source.tsx'].map(leaf=>{const raw=Buffer.from('real fixture '+leaf);writeFileSync(join(folder,leaf),raw);return {name:`outputs/video/${task}/${leaf}`,sha256:sha(raw),bytes:raw.length};});
 const source_version=files[1].sha256;
 const result={source_current:true,full_video_decode:true,source_version,program_id:program,library_digest:'a'.repeat(64),policy_digest:'b'.repeat(64),artifacts:files};
 writeFileSync(join(folder,'delivery.json'),JSON.stringify({task_id:task,kind:'video-delivery-v1',full_video_decode:true,source_version,files}));
 const journal={kind:'source_program_rendered',task_id:task,program_id:program,library_digest:result.library_digest,policy_digest:result.policy_digest,source_sha256:source_version,render:result,source_current:true};
 writeFileSync(join(root,'source-program-audit.jsonl'),JSON.stringify(journal)+'\n');
 return {root,task,result,journal,folder,close:()=>rmSync(root,{recursive:true,force:true})};
}
test('program reuse requires actual tool result plus own host journal and immutable delivery, once per call',options,async()=>{
 const {videoProgramReuse}=await import('../src/adapters/harless_video_program.ts');const f=fixture();try{
  const seen=new Set(),execution={name,callId:'actual-call'};
  const accepted=videoProgramReuse(base(),f.task,f.root,execution,{structuredContent:f.result},seen);
  assert.equal(accepted.kind,'video_program_reused');assert.equal(accepted.program_id,program);assert.equal(accepted.verified_skip,undefined);
  assert.equal(videoProgramReuse(base(),f.task,f.root,{name,callId:'different-call-same-proof'},{structuredContent:f.result},seen),null);
  assert.equal(videoProgramReuse(base(),f.task,f.root,execution,{structuredContent:f.result},seen),null);
  assert.equal(videoProgramReuse(base(),'d'.repeat(32),f.root,{name,callId:'foreign-task'},{structuredContent:f.result},seen),null);
  assert.equal(videoProgramReuse(base(),f.task,f.root,{name:'mcp__remotion__render_source',callId:'ordinary'},{structuredContent:f.result},seen),null);
  assert.equal(videoProgramReuse(base(),f.task,f.root,{name,callId:'failed'},{isError:true,structuredContent:f.result},seen),null);
  for(const delta of [{source_current:false},{full_video_decode:false},{policy_digest:'wrong'},{library_digest:'wrong'}])
   assert.equal(videoProgramReuse(base(),f.task,f.root,{name,callId:'bad-result'},{structuredContent:{...f.result,...delta}},seen),null);
  writeFileSync(join(f.folder,'video.mp4'),'changed');assert.equal(videoProgramReuse(base(),f.task,f.root,{name,callId:'tampered'},{structuredContent:f.result},seen),null);
 }finally{f.close();}
});
test('displayed model text without host proof cannot count as video program reuse',options,async()=>{
 const {videoProgramReuse}=await import('../src/adapters/harless_video_program.ts');const f=fixture();try{
  writeFileSync(join(f.root,'source-program-audit.jsonl'),JSON.stringify({...f.journal,task_id:'foreign'})+'\n');
  assert.equal(videoProgramReuse(base(),f.task,f.root,{name,callId:'forged'},{content:[{type:'text',text:JSON.stringify(f.result)}]},new Set()),null);
 }finally{f.close();}
});

test('old program journal and repeated output rows cannot certify a new render',options,async()=>{
 const {videoProgramReuse}=await import('../src/adapters/harless_video_program.ts');const f=fixture();try{
  for(const delta of [{source_current:false},{source_sha256:'changed'},{render:{...f.result,full_video_decode:false}},{render:{...f.result,artifacts:[]}}]){
   writeFileSync(join(f.root,'source-program-audit.jsonl'),JSON.stringify({...f.journal,...delta})+'\n');
   assert.equal(videoProgramReuse(base(),f.task,f.root,{name,callId:'stale'},{structuredContent:f.result},new Set()),null);
  }
  const artifacts=[f.result.artifacts[0],f.result.artifacts[0]],result={...f.result,artifacts};
  writeFileSync(join(f.root,'source-program-audit.jsonl'),JSON.stringify({...f.journal,render:result})+'\n');
  writeFileSync(join(f.folder,'delivery.json'),JSON.stringify({task_id:f.task,kind:'video-delivery-v1',full_video_decode:true,source_version:result.source_version,files:artifacts}));
  assert.equal(videoProgramReuse(base(),f.task,f.root,{name,callId:'duplicates'},{structuredContent:result},new Set()),null);
 }finally{f.close();}
});
