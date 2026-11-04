/** Host-boundary diagnostics; synthetic programs/certificates are not research evidence. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,rmSync,existsSync} from 'node:fs';
import {join,resolve,dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {execFileSync,spawnSync} from 'node:child_process';
import {artifactLocks,identity,hash} from '../src/adapters/artifact_motif_runtime.ts';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {buildArtifactCapabilities} from '../src/adapters/artifact_capability_runtime.ts';
import {capabilityRef,capabilityDigest} from '../src/adapters/capability_contract.ts';
import {publicPptValidationTask} from '../src/adapters/ppt_capability_broker.ts';
import {preparePptProgramJob} from '../src/adapters/ppt_program_broker.ts';
import {startCommandBroker} from '../src/adapters/geneloop_command_broker.ts';

const root=resolve(import.meta.dirname,'..'),python=process.env.SSS_PURE_CODE_PYTHON??process.env.SSS_PYTHON;
const save=(file,value)=>writeFileSync(file,JSON.stringify(value));
const sha=file=>hash(readFileSync(file));
const available=python&&existsSync(python);
function fixture(t){
 const output=mkdtempSync(join(tmpdir(),'public-ppt-member-'));t.after(()=>rmSync(output,{recursive:true,force:true}));
 const owner='diagnostic-owner',scope='diagnostic-scope',learning=join(output,'learning','ppt-'+hash(owner+'\0'+scope));
 const programFolder=join(learning,'program-'+'b'.repeat(24));mkdirSync(programFolder,{recursive:true});
 const png=execFileSync(python,['-c',"import io,base64;from PIL import Image;b=io.BytesIO();Image.new('RGB',(1,1),'white').save(b,format='PNG');print(base64.b64encode(b.getvalue()).decode())"],{encoding:'utf8'}).trim();
 const svg=title=>'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text x="5" y="30">'+title+'</text></svg>';
 const source='import json,sys,base64\nfrom pathlib import Path\nd=json.load(open(sys.argv[1]))\no=Path(sys.argv[2]);o.mkdir()\n'+
  '(o/"page.svg").write_text(\'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text x="5" y="30">\'+d["title"]+\'</text></svg>\')\n'+
  '(o/"page.png").write_bytes(base64.b64decode('+JSON.stringify(png)+'))\n';
 const program={version:1,source,source_sha256:hash(source),inputs:[{suffix:'.json',format:'json',shape:{object:{title:'string'}}}],
  dependencies:{},input_argument_indices:[0],output_argument_index:1,argument_count:2,language:'python',execution_policy:'fresh_output_network_disabled_v1'};
 const version=digest(identity(program));program.id='artifact_'+version.slice(0,24);
 program.certification={passed:true,distinct_inputs:2,source_equivalent:true,program_sha256:version};
 const body={kind:'witnessed_artifact_program_library',version:1,scene:'ppt',programs:[program],
  code_locks:Object.fromEntries(artifactLocks.map(file=>[file,sha(join(root,file))]))};
 const library=join(programFolder,'library.json');save(library,{...body,digest:digest(body)});
 const catalog=buildArtifactCapabilities(library,owner),native=catalog.capabilities[0];
 const proposal={format:'capability_compose_proposal_v1',owner,contract:native.contract,
  steps:[{id:'page',capability:capabilityRef(native),arguments:{kind:'input',path:[]}}],output:{kind:'step',step_id:'page',path:[]}};
 const compiled=JSON.parse(execFileSync(python,['-c',
  'import json,sys;from src.adapters.capability_builder import compile_proposal;x=json.load(sys.stdin);print(json.dumps(compile_proposal(x["proposal"],x["snapshot"],x["owner"])))'],
  {cwd:root,input:JSON.stringify({proposal,snapshot:catalog.snapshot,owner}),encoding:'utf8'}));
 const proof=join(output,'host-proof.json');save(proof,{diagnostic:true});
 const pointer={user:owner,scope,phase:'probation',library:'program-'+'b'.repeat(24)+'/library.json',library_sha256:sha(library),
  library_digest:body.digest??digest(body),evidence_locks:{'host-proof.json':sha(proof)},feedback_version:null};
 save(join(learning,'program-selected.json'),pointer);
 const attempt=join(learning,'capability/improvements','a'.repeat(64),'job','attempt-0');mkdirSync(attempt,{recursive:true});
 const candidate=join(attempt,'candidate.json');save(candidate,compiled);
 const plan={owner,store:join(learning,'capability/store'),candidate,expected_latest:null,output:join(attempt,'publication'),
  libraries:[{path:library,sha256:sha(library)}],resources:{}};
 for(const [label,title] of [['validation','First'],['followup','Second']]){
  const workspace=join(attempt,label+'-workspace');
  for(const name of ['inputs','code','outputs/code','command-tmp'])mkdirSync(join(workspace,name),{recursive:true});
  const input=join(workspace,'inputs/current.json');save(input,{title});
  const reference=join(learning,'references',label);mkdirSync(reference,{recursive:true});
  writeFileSync(join(reference,'page.svg'),svg(title));writeFileSync(join(reference,'page.png'),Buffer.from(png,'base64'));
  plan[label]={id:'independent-'+label,workspace,input:{inputs:['/work/inputs/current.json'],output:'/work/outputs/page'},
   input_versions:[{path:'/work/inputs/current.json',sha256:sha(input)}],sources:[],
   reference_svg:{path:join(reference,'page.svg'),sha256:sha(join(reference,'page.svg'))},
   reference_png:{path:join(reference,'page.png'),sha256:sha(join(reference,'page.png'))}};
 }
 const planPath=join(attempt,'publication-plan.json');save(planPath,plan);
 // A frozen host manifest for read-only authority tests; the full cycle creates
 // both real manifests itself and publishes through the original Store.
 const directory=join(plan.output,'validation');mkdirSync(directory,{recursive:true});
 const registry=join(directory,'registry.json');save(registry,compiled.snapshot);save(join(directory,'args.json'),plan.validation.input);
 const manifest={format:'artifact_capability_task_v1',owner,task_id:plan.validation.id,workspace:plan.validation.workspace,
  registry_path:registry,libraries:plan.libraries,inputs:plan.validation.input_versions,
  grant:{id:'diagnostic-grant',task_id:plan.validation.id,root:capabilityRef(compiled.capability),snapshot_sha256:compiled.snapshot.digest,
   arguments_sha256:capabilityDigest(plan.validation.input),effects:['workspace_write'],mode:'validate',revoked:false}};
 const manifestPath=join(directory,'manifest.json');save(manifestPath,manifest);
 return {output,owner,scope,learning,plan,planPath,manifest,manifestPath,pointer,registry};
}

test('public validation owns its private learner, frozen grant and independent workspace',{skip:!available},t=>{
 const f=fixture(t),options={output:f.output,python,node:process.execPath};
 const task=publicPptValidationTask(f.output,f.manifestPath,python);
 const job=preparePptProgramJob(options,{operation:'capability',file:f.manifestPath});
 assert.ok(job.argv.includes('--member-public'));assert.equal(job.env.GENELOOP_COMMAND_SOCKET,undefined);
 assert.equal(task.resolvePath('/app/.local/web/'+f.manifestPath.slice(f.output.length+1)),f.manifestPath);
 assert.throws(()=>preparePptProgramJob(options,{operation:'capability',file:f.manifestPath,source:'untrusted'}),/invalid public/);
 assert.throws(()=>publicPptValidationTask(f.output,join(f.output,'host-proof.json'),python),/outside_owned/);
 const saved=structuredClone(f.manifest);
 for(const field of ['owner','workspace','registry_path']){
  save(f.manifestPath,{...saved,[field]:field==='owner'?'foreign':f.output});
  assert.throws(()=>publicPptValidationTask(f.output,f.manifestPath,python));
 }
 save(f.manifestPath,{...saved,grant:{...saved.grant,revoked:true}});
 assert.throws(()=>publicPptValidationTask(f.output,f.manifestPath,python),/grant_invalid/);
 save(f.manifestPath,saved);
 save(join(f.learning,'program-selected.json'),{...f.pointer,phase:'disabled'});
 assert.throws(()=>task.assertAuthority(),/authority_changed/,'Revocation stays live after admission');
});

const trueCommand=existsSync('/usr/bin/true')?'/usr/bin/true':'/bin/true';
const namespace=process.platform==='linux'&&spawnSync('bwrap',['--unshare-user','--ro-bind','/','/','--unshare-net',trueCommand]).status===0;
test('independent validate, publish, reload and followup cross the real member command broker',
 {skip:!available||!namespace,timeout:60000},async t=>{
 const f=fixture(t);rmSync(f.plan.output,{recursive:true,force:true});
 const broker=await startCommandBroker({output:f.output,python,node:process.execPath,resources:{}});t.after(()=>broker.close());
 const {spawn}=await import('node:child_process');
 const child=spawn(process.execPath,['--experimental-strip-types',join(root,'scenarios/ppt_master/publish_capability.mjs'),f.planPath],
  {cwd:root,env:{...process.env,SSS_PYTHON:python,GENELOOP_COMMAND_SOCKET:broker.socketPath},stdio:['ignore','pipe','pipe']});
 let stderr='';child.stderr.on('data',data=>stderr+=data);const {once}=await import('node:events');const [status]=await once(child,'close');
 const result=JSON.parse(readFileSync(join(f.plan.output,'result.json'),'utf8'));
 assert.equal(status,0,stderr+'\n'+JSON.stringify(result));assert.equal(result.followup_passed,true);
 for(const label of ['validation','followup']){
  const trace=JSON.parse(readFileSync(join(f.plan.output,label,'trace.json'),'utf8'));
  assert.equal(trace.status,'succeeded');assert.equal(trace.task_id,f.plan[label].id);
 }
});
