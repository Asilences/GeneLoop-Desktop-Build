import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {Context} from '@deepseek-ai/cordis';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {SessionStore} from '@deepseek-ai/dsh-session';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {ToolRuntime,defineTool,assertSupportedJsonSchema} from '@deepseek-ai/dsh-tools';
import {LlmRuntime} from '@deepseek-ai/dsh-llm';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {registerPptWriteTool,pptWriteTools} from '../src/adapters/ppt_write_tool.ts';
import {pptWorkflowHost} from '../src/adapters/ppt_workflow_host.ts';
import {pptWorkspacePath} from '../src/adapters/ppt_delivery_pipeline.ts';
import {pptComponentTool} from '../src/adapters/ppt_component_tool.ts';
import {pptPageTool} from '../src/adapters/ppt_design.ts';

test('write program schema is supported by the real native runtime',()=>{
 for(const tool of pptWriteTools)assertSupportedJsonSchema(tool.parameters);
});

test('native program dispatch preflights all pages, preserves others and controls component abandonment',async()=>{
 const ctx=new Context();new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);
 new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);
 const root=mkdtempSync(join(process.cwd(),'.local/write-native-'));
 mkdirSync(join(root,'code/projects/deck/svg_output'),{recursive:true});mkdirSync(join(root,'output'));
 mkdirSync(join(root,'code/projects/deck/notes'));
 let writes=0,arbitrary=0,deliveryFailed=false;
 const state={task:{workspace:root,output:join(root,'output'),status:'running',scene_options:{allow_output:true},selection:{rsi:true},
  request:{mode:'execute',task_id:'diagnostic',content:[{text:'用户明确要求加入当前结论页无法表达的三维交互模型'}]}},workflowValid:()=>true,
  workflowAudit(){},context:{library:{programs:[{id:'component',component:{parameters_schema:{type:'object',properties:{title:{type:'string',maxLength:30}},required:['title'],additionalProperties:false}},
   certification:{passed:true,component_source_equivalence:{passed:true}}}]}}};
 try{
  const loop=new AgentLoop(ctx,{agents:[]}),agent=await loop.create('write-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash'});
  const output={schema:{type:'json'},render:(_a,value)=>[{type:'text',text:JSON.stringify(value)}]};
  const rawOutput={...output,schema:{type:'object'}};
  ctx.tools.register({...pptComponentTool,output:rawOutput,execute:async args=>{
   assert.equal(typeof args.parameters,'object');assert.equal(args.parameters_file,undefined);
   assert.equal(args.output,undefined,'Host allocates fresh scratch output instead of replaying a model-selected directory');
   writes++;const path=join(root,'code/projects/deck/svg_output',args.page),bytes=Buffer.from(args.parameters.title);
   writeFileSync(path,bytes);return {installed_page_sha256:createHash('sha256').update(bytes).digest('hex')};}});
  ctx.tools.register({...pptPageTool,output:rawOutput,execute:async()=>{throw Error('unused');}});
  ctx.tools.register(defineTool({name:'finalize_ppt',description:'Diagnostic',parameters:{project:{type:'string',required:true}},output,
   execute:async()=>({mechanical_status:deliveryFailed?'failed':'passed',findings:deliveryFailed?[{rule:'overflow',page:2,severity:'error'}]:[],review_pages:[],artifacts:[]})}));
  ctx.tools.register(defineTool({name:'read_image',description:'Diagnostic',parameters:{file_path:{type:'string',required:true}},output,execute:async()=>({})}));
  ctx.tools.register(defineTool({name:'bash',description:'Diagnostic',parameters:{command:{type:'string',required:true}},output,execute:async()=>{arbitrary++;return {};}}));
  const host=pptWorkflowHost({agent}),contract=host.contracts.create_ppt_page;
  const ir={version:1,kind:'observed_page_write_delivery',mode:'new',writer:{tool:'create_ppt_page',schema_sha256:contract.schema_sha256,
   argument_names:['id','notes','output','page','parameters','parameters_file','project'],required_arguments:['id','notes','page','project'],...contract.page_write},
   delivery:{tool:'finalize_ppt',schema_sha256:host.contracts.finalize_ppt.schema_sha256,resource_argument:'project',argument_names:['project'],...host.contracts.finalize_ppt.observed_completion}};
  const witness=id=>({decision_id:id,source_signature:'source-'+id,question_sha256:'question-'+id});
  const program={id:'ppt_write_'+digest(ir).slice(0,24),ir,status:'certified',provenance:[witness('a'),witness('b')],
   certification:{scope:'independent_observed_write_binding_replay',status:'passed',training_decisions:2,independent_replay_decisions:1,replay:[witness('c')]}};
  const body={version:1,kind:'trace_learned_tool_continuations',environment_sha256:host.environment_sha256,programs:[program]};
  state.workflow={...body,digest:digest(body)};
  registerPptWriteTool(ctx,()=>state,pptWorkspacePath);
  const execute=(name,args)=>ctx.tools.execute({name,arguments:args,callId:randomUUID(),agent,signal:new AbortController().signal});
  const page=title=>({id:'component',page:title+'.svg',parameters:{title},notes:'Current source notes'});
  const invalid=await execute('execute_ppt_program',{id:program.id,project:'/work/projects/deck',pages:[page('one'),{...page('two'),parameters:{title:'x'.repeat(40)}}]});
  assert.equal(invalid.isError,true);assert.equal(writes,0,'Every page is admitted before the first write');
  writeFileSync(join(root,'code/one-parameters.json'),JSON.stringify({title:'one'}));
  const {parameters,...filePage}=page('one');
  const result=await execute('execute_ppt_program',{id:program.id,project:'/work/projects/deck',pages:[{...filePage,parameters_file:'/work/one-parameters.json',output:'/work/outputs/already-used'},page('two')]});
  assert.equal(result.isError,false,JSON.stringify(result));assert.equal(result.value.status,'completed');assert.equal(writes,2);
  assert.equal((await execute('bash',{command:'rewrite all slides'})).isError,true);assert.equal(arbitrary,0);
  assert.equal((await execute('release_ppt_program',{project:'/work/projects/deck',reason:'delivery_failure'})).isError,true);
  assert.equal((await execute('release_ppt_program',{project:'/work/projects/deck',reason:'unsupported_requirement',requirement_quote:'我想换一个新样式'})).isError,true);
  const release=await execute('release_ppt_program',{project:'/work/projects/deck',reason:'unsupported_requirement',requirement_quote:'用户明确要求加入当前结论页无法表达的三维交互模型'});
  assert.equal(release.isError,false,JSON.stringify(release));
  assert.equal((await execute('bash',{command:'repair only unsupported part'})).isError,false);assert.equal(arbitrary,1);
  assert.equal(readFileSync(join(root,'code/projects/deck/svg_output/one.svg'),'utf8'),'one');
  state.writeReleased.delete('/work/projects/deck');
  const originalWorkflow=state.workflow,revisionIr=structuredClone(ir);
  revisionIr.mode='revision';revisionIr.writer.argument_names.push('expected_page_sha256');
  const revisionProgram={...program,id:'ppt_write_'+digest(revisionIr).slice(0,24),ir:revisionIr};
  const revisionBody={...body,programs:[revisionProgram]};state.workflow={...revisionBody,digest:digest(revisionBody)};
  const before=createHash('sha256').update(readFileSync(join(root,'code/projects/deck/svg_output/one.svg'))).digest('hex');
  const early=await execute('create_ppt_page',{...page('one'),project:'/work/projects/deck',expected_page_sha256:before});
  assert.equal(early.isError,false,JSON.stringify(early));assert.equal(early.value.continued_by,undefined,'Do not auto-export an initial deck that has not been delivered');
  state.workflow=originalWorkflow;
  writeFileSync(join(root,'code/projects/deck/delivery.json'),'{}');
  const direct=await execute('create_ppt_page',{...page('continued'),project:'/work/projects/deck'});
  assert.equal(direct.isError,false,JSON.stringify(direct));assert.equal(direct.value.continued_by,'execute_ppt_program');
  assert.equal(direct.value.execution_status,'completed');assert.equal(writes,4,'A single-page call continues the learned program without rejection or duplicate writes');
  deliveryFailed=true;
  const broken=await execute('create_ppt_page',{...page('specific-failure'),project:'/work/projects/deck'});
  assert.equal(broken.value.execution_status,'failed');
  assert.equal(broken.value.error_details.findings[0].rule,'overflow');
  assert.equal(broken.value.delivery.findings[0].page,2,'The exact failure reaches the original caller instead of an empty delivery');

 }finally{await ctx.fiber.dispose();}
});
