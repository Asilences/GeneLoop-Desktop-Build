/** Offline real namespace replay; no LLM certification calls or fabricated traces. */
import {readFileSync,writeFileSync,readdirSync,lstatSync,realpathSync} from 'node:fs';
import {join,resolve,relative,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {artifactLocks,hash,identity,matchesArtifactInput,runArtifactProgram,loadArtifactLibrary} from '../src/adapters/artifact_motif_runtime.ts';
import {assertComponentSchema,validateComponentParameters} from '../src/adapters/ppt_component_schema.ts';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
/** Hash the representation that is actually persisted, including optional fields. */
export function sealArtifactLibrary(body){
 const persisted=JSON.parse(JSON.stringify(body,function(key,value){
  if(typeof value==='number'&&!Number.isFinite(value)||['function','symbol','bigint'].includes(typeof value)||Array.isArray(this)&&value===undefined)throw Error('artifact_metadata_must_be_json');
  return value;
 }));
 return {...persisted,digest:digest(persisted)};
}
function candidates(workspace,contract){
 const found=[];
 function visit(path,depth=0){
  if(depth>5)return;
  for(const file of readdirSync(path,{withFileTypes:true})){
   if(file.name.startsWith('.')||file.isSymbolicLink())continue;
   const host=join(path,file.name);
   if(file.isDirectory()){visit(host,depth+1);continue;}
   if(!file.isFile()||lstatSync(host).size>16_000_000||realpathSync(host)!==host)continue;
   const data=readFileSync(host);if(matchesArtifactInput(contract,host,data))found.push({host,data,sha256:hash(data)});
  }
 }
 for(const dir of (contract.source_origin==='uploaded_input'?['inputs']:['code','outputs/code']))visit(join(workspace,dir));
 return found;
}
function originalFiles(path){
 const rows=[];
 function visit(p){for(const f of readdirSync(p,{withFileTypes:true})){
  const h=join(p,f.name);if(f.isSymbolicLink())throw Error('historical_output_link');
  if(f.isDirectory())visit(h);else if(f.isFile())rows.push({path:relative(path,h),bytes:lstatSync(h).size,sha256:hash(readFileSync(h))});
 }}visit(path);return rows.sort((a,b)=>a.path.localeCompare(b.path));
}
function outputProfile(directory,files){
 const svgs=files.filter(f=>extname(f.path)==='.svg');if(!svgs.length)return undefined;
 const raw=readFileSync(join(directory,svgs[0].path),'utf8');
 return {kind:'observed_svg_declarations_not_rendered_quality',svg_pages:svgs.length,
  viewBox:/\bviewBox=["']([^"']+)["']/.exec(raw)?.[1]??null,
  font_families:[...new Set([...raw.matchAll(/font-family=["']([^"']+)["']/g)].map(m=>m[1]))],
  hex_colors:[...new Set([...raw.matchAll(/(?:fill|stroke)=["'](#[0-9a-fA-F]{3,8})["']/g)].map(m=>m[1]))]};
}
export function witnessedHeldoutInputs(program,held){
 const matches=(held.candidates??[]).filter(p=>p.id===program.id&&p.source_sha256===program.source_sha256);
 if(!matches.length)return null;
 const versions=new Map();
 for(const p of matches){
  const bound=program.input_argument_indices.map((index,i)=>{
   const host=p.witness.input_paths[index],data=readFileSync(host),version=p.witness.input_sha256[index];
   const rel=relative(held.workspace,host);
   if(rel.startsWith('..')||realpathSync(host)!==host||hash(data)!==version||!matchesArtifactInput(program.inputs[i],host,data))throw Error('heldout_native_input_changed');
   return {host,data,sha256:version};
  });
  const key=digest(bound.map(b=>b.sha256));if(!versions.has(key))versions.set(key,{bound,witness:p.witness});
 }
 if(versions.size!==1)throw Error('heldout_native_binding_ambiguous');
 return [...versions.values()][0];
}
export function certifyArtifactRows(rows,resources={}){
 if(rows.length<2||new Set(rows.map(r=>r.task_id)).size!==rows.length||new Set(rows.map(r=>r.scene)).size!==1)throw Error('independent_same_scene_tasks_required');
 const [held,...training]=rows,programs=[],rejected=[],seen=new Set();
 for(const row of training)for(const p of row.candidates){
  if(seen.has(p.id))continue;
  try{
   if(p.component)assertComponentSchema(p.component.parameters_schema);
   const own=p.input_argument_indices.map((index,i)=>{
    const host=p.witness.input_paths[index],data=readFileSync(host),version=p.witness.input_sha256[index];
    if(realpathSync(host)!==host||hash(data)!==version||!matchesArtifactInput(p.inputs[i],host,data))throw Error('source_input_changed');
    return {host,data,sha256:version};
   });
   const nativeHeld=witnessedHeldoutInputs(p,held);
   const other=nativeHeld?.bound??p.inputs.map(contract=>{const matches=candidates(held.workspace,contract);if(matches.length!==1)throw Error('heldout_input_ambiguous_or_absent');return matches[0];});
   if(digest(own.map(b=>b.sha256))===digest(other.map(b=>b.sha256)))throw Error('distinct_input_required');
   if(p.component)for(const bound of [own,other]){
    const errors=validateComponentParameters(p.component.parameters_schema,JSON.parse(bound[0].data.toString('utf8')));
    if(errors.length)throw Error('component_certification_parameters_invalid: '+JSON.stringify(errors));
   }
   const ownText=own.map(b=>b.data.toString('utf8')).join('\n'),otherText=other.map(b=>b.data.toString('utf8')).join('\n');
   // Conservative content-leak guard in addition to sandbox isolation. This is
   // not a semantic correctness proof; current model still owns suitability.
   let technical=new Set();
   if(p.component){
    const reference=join(p.witness.original_output,'page.svg');
    if(hash(readFileSync(reference))!==p.component.historical_source_sha256)throw Error('historical_component_source_changed');
    const classified=spawnSync(process.env.SSS_PYTHON??'python3',['-m','src.adapters.ppt_component_literals'],
     {cwd:root,encoding:'utf8',timeout:30000,input:JSON.stringify({source:p.source,reference})});
    if(classified.status!==0)throw Error('component_literal_classification_failed');
    const roles=JSON.parse(classified.stdout);
    technical=new Set([...roles.interface_keys,...roles.presentation_palette]);
   }
   for(const text of p.literal_selectors??[])if(!technical.has(text)&&!(p.interface_comparison_literals??[]).includes(text)&&ownText.includes(text)&&!otherText.includes(text))throw Error('task_specific_content_not_parameterized');
   const cases=[];let sourceFiles,componentEquivalence;
   for(const [role,task,bound] of [['source',row,own],['certification',held,other]]){
    const job={workspace:task.workspace,program:p,bound,resources,nonce:'certification',certification:true,
     ...(role==='source'?{certificationArguments:p.witness.invocation_arguments}:nativeHeld?{certificationArguments:nativeHeld.witness.invocation_arguments}:{})};
    const a=runArtifactProgram(job),b=runArtifactProgram(job);
    const signature=receipt=>digest({stdout:receipt.stdout,files:receipt.files.slice().sort((x,y)=>x.path.localeCompare(y.path))});
    if(signature(a.receipt)!==signature(b.receipt))throw Error('artifact_nondeterministic');
    if(role==='source'){
     sourceFiles=a.receipt.files.slice().sort((x,y)=>x.path.localeCompare(y.path));
     if(p.component){
      if(hash(readFileSync(join(p.witness.original_output,'page.svg')))!==p.component.historical_source_sha256)throw Error('historical_component_source_changed');
      const reference=join(p.witness.original_output,'page.svg'),data=readFileSync(reference);
      const referenceProgram={id:'trusted_ppt_svg_reference_v1',argument_count:2,input_argument_indices:[0],output_argument_index:1,
       component:p.component,source:'import sys\nfrom pathlib import Path\nout=Path(sys.argv[2]);out.mkdir(parents=True)\n(out/"page.svg").write_bytes(Path(sys.argv[1]).read_bytes())\n'};
      const rendered=runArtifactProgram({workspace:row.workspace,program:referenceProgram,
       bound:[{host:reference,data,sha256:hash(data)}],resources,certification:true,
       componentReferenceAllowDesignFindings:(p.component.certification_mode??'preserve')!=='preserve'});
      const checked=spawnSync(process.env.SSS_PYTHON??'python3',['-m','src.adapters.ppt_component_equivalence',rendered.output,a.output,p.component.certification_mode??'preserve'],{cwd:root,encoding:'utf8',timeout:30000});
      if(checked.status!==0)throw Error('component_equivalence_checker_failed');
      componentEquivalence=JSON.parse(checked.stdout);
      componentEquivalence.reference_renderer='same_namespace_fonts_and_resources';
      if(componentEquivalence.passed!==true)throw Error('component_source_equivalence_failed: '+JSON.stringify(componentEquivalence));
     }else if(digest(sourceFiles)!==digest(originalFiles(p.witness.original_output)))throw Error('historical_output_not_reproduced');
     if(p.component){
      const changedArguments=p.witness.invocation_arguments.slice();changedArguments[p.output_argument_index]='/work/outputs/component-output-independence';
      const changed=runArtifactProgram({...job,certificationArguments:changedArguments});
      if(digest(changed.receipt.files.slice().sort((x,y)=>x.path.localeCompare(y.path)))!==digest(sourceFiles))throw Error('component_depends_on_output_directory');
     }
    }
    if(role==='certification'&&nativeHeld&&digest(a.receipt.files.slice().sort((x,y)=>x.path.localeCompare(y.path)))!==digest(originalFiles(nativeHeld.witness.original_output)))throw Error('heldout_historical_output_not_reproduced');
    cases.push({role,task_id:task.task_id,inputs:bound.map(b=>b.sha256),files:a.receipt.files,stdout_sha256:hash(a.receipt.stdout)});
   }
   if(digest(cases[0].files)===digest(cases[1].files))throw Error('input_dependency_not_demonstrated');
   const {witness,...program}=p;
   programs.push({...program,output_profile:outputProfile(p.witness.original_output,sourceFiles),certification:{passed:true,distinct_inputs:2,source_equivalent:true,program_sha256:digest(identity(p)),
    source_task_id:row.task_id,source_call_id:witness.call_id,events_sha256:witness.events_sha256,boundary_sha256:witness.boundary_sha256,
    ...(p.component?{component_source_equivalence:componentEquivalence,source_parameterization:{origin:witness.origin,historical_source:witness.historical_source,
      witness_sha256:witness.parameterization_witness_sha256}}:{}),
    invariant_input_versions:Object.fromEntries(own.flatMap((b,i)=>b.sha256===other[i].sha256?[[i,b.sha256]]:[])),
    binding_evidence:nativeHeld?{kind:'native_heldout_invocation',call_id:nativeHeld.witness.call_id,boundary_sha256:nativeHeld.witness.boundary_sha256}:{kind:'unique_typed_approved_input'},
    output_extensions:[...new Set(sourceFiles.map(f=>extname(f.path)))],cases,semantic_quality_accepted:false}});
   seen.add(p.id);
  }catch(error){rejected.push({program_id:p.id,call_id:p.witness.call_id,reason:error.message});}
 }
 const observedCommon=Object.fromEntries(Object.entries(held.approved_inputs??{}).filter(([name,version])=>training.every(r=>r.approved_inputs?.[name]===version)));
 const body={version:1,kind:'witnessed_artifact_program_library',scene:held.scene,programs,observed_common_approved_inputs:observedCommon,code_locks:Object.fromEntries(artifactLocks.map(p=>[p,hash(readFileSync(join(root,p)))])),
  heldout_task_id:held.task_id,compilation_model_requests:0,
  scope:programs.some(p=>p.component)?'parameterized_historical_svg_equivalence_and_distinct_material_execution':'native_program_source_equivalence_and_distinct_input_determinism_not_semantic_quality'};
 return {library:sealArtifactLibrary(body),report:{published:programs.length,rejected,quality_cost_promoted:false}};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const result=certifyArtifactRows(JSON.parse(readFileSync(process.argv[2],'utf8')),process.env.GENELOOP_ARTIFACT_RESOURCES?JSON.parse(process.env.GENELOOP_ARTIFACT_RESOURCES):{});
 for(const [name,value] of Object.entries(result))writeFileSync(join(process.argv[3],name+'.json'),JSON.stringify(value,null,2)+'\n',{mode:0o600,flag:'wx'});
 loadArtifactLibrary(join(process.argv[3],'library.json'));
 console.log(JSON.stringify(result.report));
}
