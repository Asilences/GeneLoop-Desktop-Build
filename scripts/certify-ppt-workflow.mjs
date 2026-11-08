/** Native replay certifier. The workflow comes from the miner, not this test. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,lstatSync,realpathSync,existsSync,readdirSync} from 'node:fs';
import {resolve,dirname,join,relative,isAbsolute} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {Context} from '@deepseek-ai/cordis';
import {SessionStore} from '@deepseek-ai/dsh-session';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {ToolRuntime} from '@deepseek-ai/dsh-tools';
import {LlmRuntime} from '@deepseek-ai/dsh-llm';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {commandLayout} from '../src/adapters/geneloop_shell.ts';
import {registerPptDesignTools} from '../src/adapters/ppt_design.ts';
import {registerPptComponentTool} from '../src/adapters/ppt_component_tool.ts';
import {registerPptDeliveryTool,pptWorkspacePath} from '../src/adapters/ppt_delivery_pipeline.ts';
import {registerPptWriteTool} from '../src/adapters/ppt_write_tool.ts';
import {pptWorkflowEnvironment} from '../src/adapters/ppt_workflow_host.ts';
import {loadArtifactLibrary,provideArtifactPrograms,registerArtifactContext} from '../src/adapters/artifact_motif_runtime.ts';
import {certifyArtifactRows,sealArtifactLibrary} from './certify-artifact-motifs.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const read=path=>JSON.parse(readFileSync(path,'utf8'));
const planPath=realpathSync(process.argv[2]),folder=dirname(planPath),output=resolve(folder,'../../../../..');
assert.match(relative(output,planPath).split('\\').join('/'),/^learning\/ppt-[a-f0-9]{64}\/workflows\/certification\/[a-f0-9]{64}\/plan\.json$/);
const plan=read(planPath),{candidate,case:sample}=plan;
assert.equal(plan.kind,'ppt_native_workflow_certification');
assert.equal(plan.environment_sha256,pptWorkflowEnvironment());
assert.equal(candidate.id,'ppt_write_'+digest(candidate.ir).slice(0,24));
assert.equal(candidate.ir.writer.tool,'create_ppt_page');assert.equal(candidate.ir.delivery.tool,'finalize_ppt');
assert.equal(candidate.ir.mode,'revision');assert.equal(candidate.status,'candidate');
const store=resolve(folder,'../../..'),request=read(join(store,'request.json'));
assert.equal(plan.user,request.user);assert.equal(plan.scope,request.scope);
assert.equal(store,join(output,'learning','ppt-'+hash(plan.user+'\0'+plan.scope)));
function checked(name,version){
 const path=resolve(output,name),rel=relative(output,path),stat=lstatSync(path);
 assert.ok(rel&&!rel.startsWith('..')&&!isAbsolute(rel)&&realpathSync(path)===path&&!stat.isSymbolicLink()&&stat.nlink===1);
 if(version)assert.equal(hash(readFileSync(path)),version);
 return path;
}
function source(witness){
 assert.match(witness.task_id,/^[a-f0-9]{32}$/);assert.ok(request.task_ids.includes(witness.task_id));
 const directory=join('tasks',witness.task_id),state=read(checked(directory+'/task-state.json'));
 const effective=read(checked(directory+'/effective-config.json'));
 assert.equal(state.user_id,plan.user);assert.equal(state.scene,'ppt');assert.equal(state.status,'completed');assert.ok(!state.failure);
 const ownRequest=effective.request??read(checked(directory+'/task.json'));
 assert.notEqual(ownRequest.learning_eligible,false);assert.ok(!['holdout','evaluate','benchmark'].includes(ownRequest.role));
 return readFileSync(checked(directory+'/events.jsonl',witness.events_sha256),'utf8').split('\n').filter(Boolean).map(JSON.parse);
}
assert.ok(candidate.provenance.length>=2);
for(const key of ['decision_id','source_signature','question_sha256','source_family']){
 assert.ok(new Set(candidate.provenance.map(w=>w[key]??w.source_signature)).size>=2);
 assert.ok(candidate.provenance.every(w=>(w[key]??w.source_signature)!==(sample.witness[key]??sample.witness.source_signature)));
}
candidate.provenance.forEach(source);
const events=source(sample.witness),calls=new Map();
for(const event of events)if(event.type==='tool/call'){
 const data=event.data;calls.set(data.callId,{name:data.name,arguments:typeof data.arguments==='string'?JSON.parse(data.arguments):data.arguments});
}
const setup=sample.setup_calls.map(id=>calls.get(id)),revision=calls.get(sample.revision_call);
assert.ok(setup.length>=2&&revision&&[...setup,revision].every(row=>row?.name==='create_ppt_page'&&row.arguments.parameters&&row.arguments.notes));
assert.ok(setup.every(row=>!row.arguments.expected_page_sha256));assert.match(revision.arguments.expected_page_sha256,/^[a-f0-9]{64}$/);
const originalEnv={...process.env};
delete process.env.DEEPSEEK_API_KEY;delete process.env.KOURI_API_KEY;delete process.env.GENELOOP_COMMAND_SOCKET;
const resources=JSON.parse(originalEnv.GENELOOP_ARTIFACT_RESOURCES??'{}');resources.projectRoot=root;
const snapshot=read(checked(plan.component_snapshot,plan.component_snapshot_sha256));
assert.equal(plan.component_snapshot,'tasks/'+sample.witness.task_id+'/ppt-program-snapshot.json');
assert.equal(snapshot.user,plan.user);assert.equal(snapshot.scope,plan.scope);assert.ok(['active','probation'].includes(snapshot.phase));
assert.equal(snapshot.library_sha256,plan.component_library_sha256);
const libraryPath=checked(plan.component_library,plan.component_library_sha256);
assert.equal(resolve(isAbsolute(snapshot.library)?snapshot.library:join(store,snapshot.library)),libraryPath);
const componentEnvironment=digest(Object.fromEntries(Object.keys(read(libraryPath).code_locks??{}).map(name=>{
 const path=resolve(root,name),rel=relative(root,path);assert.ok(rel&&!rel.startsWith('..')&&!isAbsolute(rel));
 return [name,hash(readFileSync(path))];
})));
assert.equal(plan.component_environment_sha256,componentEnvironment);
let library;
try{library=loadArtifactLibrary(libraryPath);}catch(error){
 if(error.message!=='artifact_code_changed')throw error;
 // Re-run the existing Artifact certifier on its immutable historical inputs.
 // Never patch a certificate's hashes or overwrite the live library/pointer.
 const historical=read(libraryPath),required=new Set([...setup,revision].map(row=>row.arguments.id));
 const destination=join(folder,'component-recertification');mkdirSync(destination,{mode:0o700});
 const certified=[];
 for(const id of required){
  const old=historical.programs.find(program=>program.id===id&&program.component);assert.ok(old,'component not in original certified library');
  let result;
  for(const entry of readdirSync(store,{withFileTypes:true}).filter(entry=>entry.isDirectory()&&/^program-[a-f0-9]{24}$/.test(entry.name))){
   const generation=join(store,entry.name);
   for(const leaf of ['candidate','candidate-repair']){
    const path=join(generation,leaf,'candidates.json');if(!existsSync(path))continue;
    const rows=read(checked(relative(output,path)));
    if(!rows.some(row=>(row.candidates??[]).some(p=>p.id===id&&p.source_sha256===old.source_sha256)))continue;
    const restricted=rows.map(row=>({...row,candidates:(row.candidates??[]).filter(p=>p.id===id&&p.source_sha256===old.source_sha256)}));
    result=certifyArtifactRows(restricted,resources);
    if(result.library.programs.some(p=>p.id===id))break;
   }
   if(result?.library.programs.some(p=>p.id===id))break;
  }
  assert.ok(result?.library.programs.some(p=>p.id===id),'original component failed current native recertification');
  writeFileSync(join(destination,id+'.json'),JSON.stringify(result,null,2),{flag:'wx',mode:0o600});certified.push(result.library);
 }
 const {digest:oldDigest,...body}=certified[0];
 const merged=sealArtifactLibrary({...body,programs:certified.flatMap(row=>row.programs)});
 writeFileSync(join(destination,'library.json'),JSON.stringify(merged,null,2),{flag:'wx',mode:0o600});
 library=loadArtifactLibrary(join(destination,'library.json'));
}
assert.ok([...setup,revision].every(row=>library.programs.some(p=>p.id===row.arguments.id&&p.component)));
const session='session-'+randomUUID(),sandbox=join(folder,'native-execution');
assert.ok(!existsSync(sandbox),'prior interrupted certification requires reconciliation');mkdirSync(sandbox,{mode:0o700});
const layout=commandLayout(sandbox,session),ctx=new Context();
new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);
let current;
const audit=row=>writeFileSync(join(sandbox,'audit.jsonl'),JSON.stringify(row)+'\n',{flag:'a',mode:0o600});
function own(workflow=null){
 const taskId=randomUUID().replaceAll('-',''),taskOutput=join(sandbox,'tasks',taskId);mkdirSync(taskOutput,{recursive:true,mode:0o700});
 const task={workspace:layout.work,output:taskOutput,status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},
  scene_options:{allow_output:true},request:{task_id:taskId,session_id:session,mode:'execute',learning_eligible:false},selection:{rsi:true},stats:{}};
 const context=provideArtifactPrograms({library,workspace:layout.work,taskId,allowOutput:true,cacheRoot:join(sandbox,'component-cache'),resources,audit,auditPath:join(taskOutput,'artifact-motif-audit.jsonl')});
 registerArtifactContext(session,context);current={task,context,workflow,workflowValid:()=>true,workflowAudit:audit,fontRules:[]};return task;
}
own();const owner=id=>id===session?current:null;
registerPptDesignTools(ctx,owner,resources);registerPptComponentTool(ctx,owner);registerPptDeliveryTool(ctx,owner,resources);registerPptWriteTool(ctx,owner,pptWorkspacePath,resources);
const sourceConfig=read(checked(join('tasks',sample.witness.task_id,'effective-config.json')));
const imageSchema=sourceConfig.tools.find(row=>row.name==='read_image')?.parameters;
if(candidate.ir.preview)ctx.tools.register({name:'read_image',parameters:imageSchema,
 output:{schema:{type:'object'},render:(_args,result)=>[{type:'image',attachment:result.image}]},async execute(args){
  const bytes=readFileSync(pptWorkspacePath(layout.work,args.file_path));assert.equal(bytes.subarray(0,8).toString('hex'),'89504e470d0a1a0a');
  return {image:{attachmentId:'sha256:'+hash(bytes),mediaType:'image/png',bytes:bytes.length}};
 }});
if(candidate.ir.preview)assert.equal(digest(imageSchema),candidate.ir.preview.schema_sha256);
const loop=new AgentLoop(ctx,{agents:[]}),agent=await loop.create(session,{provider:'deepseek-official',model:'deepseek-flash'});
const execute=async(name,args)=>{const result=await ctx.tools.execute({name,arguments:args,callId:randomUUID(),agent,signal:new AbortController().signal});assert.equal(result.isError,false,JSON.stringify(result));return result.value;};
const trial={...candidate,status:'certified',certification:{...candidate.certification,status:'passed',independent_replay_decisions:1,replay:[sample.witness]}};
const body={version:1,kind:'trace_learned_tool_continuations',environment_sha256:plan.environment_sha256,programs:[trial]},workflow={...body,digest:digest(body)};
const results=[];
try{
 for(const arm of ['ordinary','compiled']){
  own();const project=(await execute('start_ppt',{name:arm,title:'独立原生执行认证',theme:'general',slide_count:setup.length})).project;
  await execute('prepare_ppt',{project});
  for(const call of setup){const {expected_page_sha256,output,...args}=call.arguments;await execute('create_ppt_page',{...args,project});}
  // A revision starts from an already delivered draft, including exporter annotations.
  assert.equal((await execute('finalize_ppt',{project})).mechanical_status,'passed');
  const before=Object.fromEntries(setup.filter(c=>c.arguments.page!==revision.arguments.page).flatMap(c=>['svg_output/'+c.arguments.page,'notes/'+c.arguments.page.replace(/\.svg$/,'.md')]).map(name=>[name,hash(readFileSync(pptWorkspacePath(layout.work,project+'/'+name)))]));
  const {project:oldProject,output,...args}=revision.arguments;
  args.expected_page_sha256=hash(readFileSync(pptWorkspacePath(layout.work,project+'/svg_output/'+args.page)));
  let delivered;
  if(arm==='ordinary'){await execute('create_ppt_page',{...args,project});delivered=await execute('finalize_ppt',{project});}
  else{
   current.workflow=workflow;
   const result=await ctx.tools.execute({name:'create_ppt_page',arguments:{...args,project},callId:randomUUID(),agent,signal:new AbortController().signal});
   assert.equal(result.isError,false,JSON.stringify(result));assert.equal(result.value.continued_by,'execute_ppt_program');
   assert.equal(result.value.workflow_program_id,trial.id);assert.equal(result.value.execution_status,'completed');
   assert.equal(result.content.filter(block=>block.type==='image').length,setup.length,'current Office previews must reach the parent tool');
   delivered=result.value.delivery;
  }
  assert.equal(delivered.mechanical_status,'passed');
  for(const [name,sha] of Object.entries(before))assert.equal(hash(readFileSync(pptWorkspacePath(layout.work,project+'/'+name))),sha,'unselected page or notes changed');
  results.push({arm,project,artifacts:delivered.artifacts,files:Object.fromEntries(setup.flatMap(c=>['svg_output/'+c.arguments.page,'notes/'+c.arguments.page.replace(/\.svg$/,'.md')]).map(name=>[name,hash(readFileSync(pptWorkspacePath(layout.work,project+'/'+name)))]))});
 }
 assert.deepEqual(results[0].files,results[1].files,'native page/notes bytes differ');
 const inspection=spawnSync(process.env.SSS_PYTHON??'python3',['-c',`import json,sys; from pathlib import Path; from src.adapters.ppt_delivery_quality import inspect_delivery; from PIL import Image,ImageChops
rows=json.load(sys.stdin); evidence=[]
for row in rows:
 files={ext:[Path(p) for p in row['paths'] if Path(p).suffix==ext] for ext in ['.pptx','.pdf','.png']}; evidence.append(inspect_delivery(files,include_content=True))
assert all(item['registered_png_count']==item['slide_count'] for item in evidence)
assert len(rows[0]['png'])==len(rows[1]['png'])==evidence[0]['slide_count']
assert evidence[0]['native_slide_content']==evidence[1]['native_slide_content']
assert evidence[0]['speaker_notes']==evidence[1]['speaker_notes']
for a,b in zip(rows[0]['png'],rows[1]['png']):
 x,y=Image.open(a).convert('RGB'),Image.open(b).convert('RGB'); assert x.size==y.size and ImageChops.difference(x,y).getbbox() is None
print(json.dumps({'native_equivalence':True,'slide_count':evidence[0]['slide_count']}))`],{cwd:root,env:{PATH:process.env.PATH,PYTHONPATH:root,PYTHONUTF8:'1'},input:JSON.stringify(results.map(row=>({paths:row.artifacts.map(a=>pptWorkspacePath(layout.work,a.path)),png:row.artifacts.filter(a=>a.path.endsWith('.png')).map(a=>pptWorkspacePath(layout.work,a.path))}))),encoding:'utf8'});
 assert.equal(inspection.status,0,inspection.stderr);
 const result={version:1,status:'passed',plan_sha256:hash(readFileSync(planPath)),environment_sha256:plan.environment_sha256,
  native_equivalence:true,unmodified_pages_preserved:true,preview_complete:true,model_requests:0,
  scientific_quality_certified:false,cost_reduction_proven:false,heldout_source:sample.witness,results};
 writeFileSync(join(folder,'result.json'),JSON.stringify(result,null,2),{mode:0o600,flag:'wx'});console.log(JSON.stringify({status:'passed',model_requests:0}));
}finally{registerArtifactContext(session,null);await ctx.fiber.dispose();}
