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
import {digest} from '../src/motif_core/runtime/online_skill_runtime.mjs';
import {commandLayout} from '../src/adapters/geneloop_shell.ts';
import {registerPptDesignTools} from '../src/adapters/ppt/authoring/ppt_design.ts';
import {registerPptComponentTool} from '../src/adapters/ppt/runtime/ppt_component_tool.ts';
import {registerPptDeliveryTool,pptWorkspacePath} from '../src/adapters/ppt/delivery/ppt_delivery_pipeline.ts';
import {registerPptWriteTool} from '../src/adapters/ppt/runtime/ppt_write_tool.ts';
import {pptWorkflowEnvironment} from '../src/adapters/ppt/runtime/ppt_workflow_host.ts';
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
const writer=candidate.ir.writer.tool,mode=candidate.ir.mode;
assert.ok(['create_ppt_page','compose_ppt_page'].includes(writer));assert.equal(candidate.ir.delivery.tool,'finalize_ppt');
assert.ok(['new','revision'].includes(mode));assert.equal(candidate.status,'candidate');
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
const independence=candidate.certification.independence_policy;
assert.ok(independence===undefined||independence==='ppt_distinct_source_decision_v2');
for(const key of independence?['decision_id','source_signature','source_family']:['decision_id','source_signature','question_sha256','source_family']){
 assert.ok(new Set(candidate.provenance.map(w=>w[key]??w.source_signature)).size>=2);
 assert.ok(candidate.provenance.every(w=>(w[key]??w.source_signature)!==(sample.witness[key]??sample.witness.source_signature)));
}
candidate.provenance.forEach(source);
const events=source(sample.witness),calls=new Map();
for(const event of events)if(event.type==='tool/call'){
 const data=event.data;calls.set(data.callId,{name:data.name,arguments:typeof data.arguments==='string'?JSON.parse(data.arguments):data.arguments});
}
const setup=sample.setup_calls.map(id=>calls.get(id)),writes=(sample.write_calls??[sample.revision_call]).map(id=>calls.get(id));
const sourceWrites=[...setup,...writes];
assert.ok(writes.length>0&&writes.length<=64&&sourceWrites.every(row=>row?.name===writer));
assert.ok(sourceWrites.every(row=>writer==='compose_ppt_page'?row.arguments.layout&&row.arguments.content:row.arguments.parameters&&row.arguments.notes));
assert.ok(writes.length>=(candidate.ir.writer.repeated_page_run?2:1));
if(mode==='revision'){assert.ok(setup.length>=2);writes.forEach(row=>assert.match(row.arguments.expected_page_sha256,/^[a-f0-9]{64}$/));}
else{assert.equal(setup.length,0);assert.ok(writes.every(row=>!row.arguments.expected_page_sha256));}
const originalEnv={...process.env};
delete process.env.DEEPSEEK_API_KEY;delete process.env.KOURI_API_KEY;delete process.env.GENELOOP_COMMAND_SOCKET;
const resources=JSON.parse(originalEnv.GENELOOP_ARTIFACT_RESOURCES??'{}');resources.projectRoot=root;
let library=null;
if(writer==='create_ppt_page'){
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
try{library=loadArtifactLibrary(libraryPath);}catch(error){
 if(error.message!=='artifact_code_changed')throw error;
 // Re-run the existing Artifact certifier on its immutable historical inputs.
 // Never patch a certificate's hashes or overwrite the live library/pointer.
  const historical=read(libraryPath),required=new Set(sourceWrites.map(row=>row.arguments.id));
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
assert.ok(sourceWrites.every(row=>library.programs.some(p=>p.id===row.arguments.id&&p.component)));
}
const session='session-'+randomUUID(),sandbox=join(folder,'native-execution');
assert.ok(!existsSync(sandbox),'prior interrupted certification requires reconciliation');mkdirSync(sandbox,{mode:0o700});
const layout=commandLayout(sandbox,session),ctx=new Context();
const assetBindings=new Map();
for(const asset of plan.assets??[]){
 assert.match(asset.sha256,/^[a-f0-9]{64}$/);assert.ok(['png','jpg'].includes(asset.extension));
 const bytes=readFileSync(checked(asset.ref,asset.sha256));assert.equal(bytes.length,asset.bytes);
 const logical='/work/ppt-certified-assets/'+asset.sha256+'.'+asset.extension;
 const directory=join(layout.scratch,'ppt-certified-assets');mkdirSync(directory,{recursive:true,mode:0o700});
 const target=join(directory,asset.sha256+'.'+asset.extension);
 if(existsSync(target))assert.equal(hash(readFileSync(target)),asset.sha256);
 else writeFileSync(target,bytes,{flag:'wx',mode:0o600});
 assert.ok(!assetBindings.has(asset.original));assetBindings.set(asset.original,logical);
}
function bindAssets(args){
 if(writer!=='compose_ppt_page'||!args.content?.image)return args;
 assert.ok(assetBindings.has(args.content.image),'recorded image needs a versioned certification snapshot');
 return {...args,content:{...args.content,image:assetBindings.get(args.content.image)}};
}
new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);
let current;
const audit=row=>writeFileSync(join(sandbox,'audit.jsonl'),JSON.stringify(row)+'\n',{flag:'a',mode:0o600});
function own(workflow=null){
 const taskId=randomUUID().replaceAll('-',''),taskOutput=join(sandbox,'tasks',taskId);mkdirSync(taskOutput,{recursive:true,mode:0o700});
 const task={workspace:layout.work,output:taskOutput,status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},
  scene_options:{allow_output:true},request:{task_id:taskId,session_id:session,mode:'execute',learning_eligible:false},selection:{rsi:true},stats:{}};
  const context=library?provideArtifactPrograms({library,workspace:layout.work,taskId,allowOutput:true,cacheRoot:join(sandbox,'component-cache'),resources,audit,auditPath:join(taskOutput,'artifact-motif-audit.jsonl')}):null;
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
 for(const arm of ['ordinary','compiled',...(!candidate.ir.writer.repeated_page_run?['automatic-entry']:[])]){
   own();const project=(await execute('start_ppt',{name:arm,title:'独立原生执行认证',theme:'general',slide_count:mode==='new'?writes.length:setup.length})).project;
  await execute('prepare_ppt',{project});
   for(const call of setup){const {expected_page_sha256,output,...args}=bindAssets(call.arguments);await execute(writer,{...args,project});}
  // A revision starts from an already delivered draft, including exporter annotations.
   if(mode==='revision')assert.equal((await execute('finalize_ppt',{project})).mechanical_status,'passed');
   const targets=new Set(writes.map(row=>row.arguments.page));
   const before=Object.fromEntries(setup.filter(c=>!targets.has(c.arguments.page)).flatMap(c=>['svg_output/'+c.arguments.page,'notes/'+c.arguments.page.replace(/\.svg$/,'.md')]).filter(name=>existsSync(join(pptWorkspacePath(layout.work,project),name))).map(name=>[name,hash(readFileSync(pptWorkspacePath(layout.work,project+'/'+name)))]));
   const pages=writes.map(row=>{
    const {project:oldProject,output,...args}=bindAssets(row.arguments);
    if(mode==='revision')args.expected_page_sha256=hash(readFileSync(pptWorkspacePath(layout.work,project+'/svg_output/'+args.page)));
    return args;
   });
  let delivered;
   if(arm==='ordinary'){for(const args of pages)await execute(writer,{...args,project});delivered=await execute('finalize_ppt',{project});}
  else if(arm==='compiled'){
   current.workflow=workflow;
    const result=await ctx.tools.execute({name:'execute_ppt_program',arguments:{id:trial.id,project,pages},callId:randomUUID(),agent,signal:new AbortController().signal});
    assert.equal(result.isError,false,JSON.stringify(result));assert.equal(result.value.status,'completed');
    assert.equal(result.content.filter(block=>block.type==='image').length,mode==='new'?writes.length:setup.length,'current Office previews must reach the parent tool');
   delivered=result.value.delivery;
  }else{
   assert.equal(pages.length,1);current.workflow=workflow;
   const result=await ctx.tools.execute({name:writer,arguments:{...pages[0],project},callId:randomUUID(),agent,signal:new AbortController().signal});
   assert.equal(result.isError,false,JSON.stringify(result));assert.equal(result.value.continued_by,'execute_ppt_program');
   assert.equal(result.value.execution_status,'completed');
   assert.equal(result.content.filter(block=>block.type==='image').length,mode==='new'?writes.length:setup.length,'automatic entry must return native previews to its original caller');
   delivered=result.value.delivery;
  }
  assert.equal(delivered.mechanical_status,'passed');
  for(const [name,sha] of Object.entries(before))assert.equal(hash(readFileSync(pptWorkspacePath(layout.work,project+'/'+name))),sha,'unselected page or notes changed');
   const names=[...new Set(sourceWrites.map(row=>row.arguments.page))].flatMap(name=>['svg_output/'+name,'notes/'+name.replace(/\.svg$/,'.md')]);
   results.push({arm,project,artifacts:delivered.artifacts,files:Object.fromEntries(names.filter(name=>existsSync(join(pptWorkspacePath(layout.work,project),name))).map(name=>[name,hash(readFileSync(pptWorkspacePath(layout.work,project+'/'+name)))]))});
 }
 for(const row of results.slice(1))assert.deepEqual(results[0].files,row.files,'native page/notes bytes differ');
  const inspection=spawnSync(process.env.SSS_PYTHON??'python3',['-c',`import json,sys; from src.adapters.filesystem_paths import Path; from src.adapters.ppt.delivery.ppt_delivery_quality import inspect_delivery; from PIL import Image,ImageChops
rows=json.load(sys.stdin); evidence=[]
for row in rows:
 files={ext:[Path(p) for p in row['paths'] if Path(p).suffix==ext] for ext in ['.pptx','.pdf','.png']}; evidence.append(inspect_delivery(files,include_content=True))
assert all(item['registered_png_count']==item['slide_count'] for item in evidence)
for index in range(1,len(rows)):
 assert len(rows[0]['png'])==len(rows[index]['png'])==evidence[0]['slide_count']
 assert evidence[0]['native_slide_content']==evidence[index]['native_slide_content']
 assert evidence[0]['speaker_notes']==evidence[index]['speaker_notes']
 for a,b in zip(rows[0]['png'],rows[index]['png']):
  x,y=Image.open(a).convert('RGB'),Image.open(b).convert('RGB'); assert x.size==y.size and ImageChops.difference(x,y).getbbox() is None
print(json.dumps({'native_equivalence':True,'slide_count':evidence[0]['slide_count']}))`],{cwd:root,env:{...process.env,PYTHONPATH:root,PYTHONUTF8:'1'},input:JSON.stringify(results.map(row=>({paths:row.artifacts.map(a=>pptWorkspacePath(layout.work,a.path)),png:row.artifacts.filter(a=>a.path.endsWith('.png')).map(a=>pptWorkspacePath(layout.work,a.path))}))),encoding:'utf8'});
 assert.equal(inspection.status,0,inspection.stderr);
 const result={version:1,status:'passed',plan_sha256:hash(readFileSync(planPath)),environment_sha256:plan.environment_sha256,
  native_equivalence:true,unmodified_pages_preserved:true,preview_complete:true,model_requests:0,
  automatic_entry_verified:results.some(row=>row.arm==='automatic-entry'),
  scientific_quality_certified:false,cost_reduction_proven:false,heldout_source:sample.witness,
  asset_input_scope:'current_owned_snapshots_for_native_certification',assets:plan.assets??[],results};
 writeFileSync(join(folder,'result.json'),JSON.stringify(result,null,2),{mode:0o600,flag:'wx'});console.log(JSON.stringify({status:'passed',model_requests:0}));
}finally{registerArtifactContext(session,null);await ctx.fiber.dispose();}
