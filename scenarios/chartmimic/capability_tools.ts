/** Chart task authority/binding only; all execution uses the original Artifact Runtime. */
import {readFileSync,writeFileSync,mkdirSync,realpathSync,lstatSync,existsSync,appendFileSync} from 'node:fs';
import {join,resolve,relative,isAbsolute,basename} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

export const name='chartmimic-certified-capabilities';
export const inject=['tools'];
const hash=(raw:Buffer)=>createHash('sha256').update(raw).digest('hex');
export function apply(ctx:any){
 const runtime=process.env.GENELOOP_CHART_RUNTIME!,library=process.env.GENELOOP_CHART_LIBRARY!;
 const expected=process.env.GENELOOP_CHART_LIBRARY_SHA256!,owner=process.env.GENELOOP_CHART_OWNER!;
 const directory=realpathSync(process.env.GENELOOP_CHART_RUN!),workspace=realpathSync(process.env.GENELOOP_CHART_WORKSPACE!);
 const taskId=process.env.GENELOOP_CHART_TASK!;
 const record=(row:any)=>appendFileSync(join(directory,'native-tools.jsonl'),JSON.stringify(row)+'\n',{mode:0o600});
 async function load():Promise<any>{
  if(process.env.GENELOOP_CHART_BUNDLE){
   const raw=readFileSync(process.env.GENELOOP_CHART_BUNDLE);
   if(hash(raw)!==process.env.GENELOOP_CHART_BUNDLE_SHA256)throw Error('chart_capability_bundle_changed');
   const bundle=JSON.parse(raw.toString('utf8'));
   if(!bundle.libraries.length)return {module:null,catalog:{snapshot:bundle.snapshot,capabilities:[]},body:{programs:[]},libraries:[],cards:[],menu:[]};
   const module=await import(pathToFileURL(join(runtime,'src/adapters/artifact_capability_runtime.ts')).href);
   const native=await import(pathToFileURL(join(runtime,'src/adapters/artifact_motif_runtime.ts')).href);
   const scripts=await import(pathToFileURL(join(runtime,'src/adapters/script_capability_runtime.ts')).href);
   const caps=new Map<string,any>(),programs:any[]=[];
   for(const ref of bundle.libraries){
    const catalog=module.buildArtifactCapabilities(ref.path,owner,ref.sha256),body=native.loadArtifactLibrary(ref.path);
    native.provideArtifactPrograms({library:body,workspace});
    for(const cap of catalog.capabilities)caps.set(cap.id,cap);
    for(const cap of scripts.buildArtifactValueCapabilities(ref.path,owner,ref.sha256).capabilities)caps.set(cap.id,cap);
    programs.push(...body.programs);
   }
   const contract=await import(pathToFileURL(join(runtime,'src/capability/graph/capability_contract.ts')).href);
   const snapshot=contract.validateCapabilitySnapshot(bundle.snapshot,owner);
   if(snapshot.capabilities.some((cap:any)=>!caps.has(cap.id)||contract.capabilityRef(caps.get(cap.id)).sha256!==contract.capabilityRef(cap).sha256))throw Error('chart_capability_bundle_native_changed');
   return {module,scripts,catalog:{snapshot,capabilities:snapshot.capabilities},body:{programs},libraries:bundle.libraries,
    cards:bundle.execution_capabilities??bundle.capabilities,auditCards:bundle.capabilities,menu:bundle.menu};
  }
  if(!library)return {module:null,catalog:{snapshot:{digest:null,roots:[]},capabilities:[]},body:{programs:[]}};
  const module=await import(pathToFileURL(join(runtime,'src/adapters/artifact_capability_runtime.ts')).href);
  const catalog=module.buildArtifactCapabilities(library,owner,expected);
  const body=JSON.parse(readFileSync(library,'utf8'));
  return {module,catalog,body};
 }
 ctx.tools.register({name:'capability_list',description:'Inspect the frozen drawing menu, or pass capability_id for one execution interface with native input contracts, observed opaque-field types, source-authored field semantics and cached source path. include_audit=true also retrieves its full original audit card. Reuse is optional; visual suitability remains your judgment.',
  parameters:{type:'object',properties:{capability_id:{type:'string'},include_audit:{type:'boolean'}},additionalProperties:false},
  output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(value)}]},
  async execute(_args:any,execution:any){
   const {catalog,body,cards,auditCards,menu}=await load();
   if(_args.include_audit&&_args.capability_id===undefined)throw Error('chart_selected_capability_required_for_audit');
   const full=(_args.include_audit?auditCards:cards)??catalog.capabilities.map((cap:any)=>{
    const program=body.programs.find((p:any)=>p.id===cap.implementation.legacy_ref.object_id);
    return {id:cap.id,interface:program.interface,input_contracts:program.inputs,
     source_sha256:program.source_sha256,scope:'current_parameters_to_artifacts; visual_suitability_is_not_certified'};
   });
   const selected=_args.capability_id===undefined?undefined:full.find((card:any)=>card.id===_args.capability_id);
   if(_args.capability_id!==undefined&&!selected)throw Error('chart_capability_not_in_frozen_library');
   const value={snapshot_sha256:catalog.snapshot.digest,capabilities:selected?[selected]:(menu??full)};
   record({phase:'finished',name:'capability_list',call_id:execution.callId,arguments:_args,result:value});return value;
  }});
 ctx.tools.register({name:'capability_call',description:'Execute a selected certified drawing program through the original isolated Runtime. Follow its input_schema: use input_files for the file interface, or values with input0, input1, etc. for the JSON value interface. Bind CURRENT inputs and a NEW nonexistent output_directory under /work/outputs on every call, including refinements; inspect the real artifacts. Ordinary tools remain available.',
  parameters:{type:'object',properties:{capability_id:{type:'string'},input_files:{type:'array',items:{type:'string'}},values:{type:'object',additionalProperties:true},output_directory:{type:'string'}},required:['capability_id','output_directory'],additionalProperties:false},
  output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(value)}]},
  async execute(args:any,execution:any){
   if(!/^[A-Za-z0-9_-]{1,160}$/.test(execution.callId))throw Error('chart_capability_call_id_invalid');
   const {module,scripts,catalog,libraries}=await load();
   const selected=catalog.snapshot.roots.find((r:any)=>r.id===args.capability_id);
   if(!selected)throw Error('chart_capability_not_in_frozen_library');
   const capability=catalog.capabilities.find((cap:any)=>cap.id===selected.id);
   const valueMode=Object.hasOwn(capability.contract.input_schema.properties,'values');
   if(valueMode?(!args.values||Object.hasOwn(args,'input_files')):(!Array.isArray(args.input_files)||Object.hasOwn(args,'values')))throw Error('chart_capability_input_interface_mismatch');
   const contract=await import(pathToFileURL(join(runtime,'src/capability/graph/capability_contract.ts')).href);
   const callerInputs:any[]=[];
   const inputs=(valueMode?[]:args.input_files).map((value:string,index:number)=>{
    const virtual=resolve('/work',value),rel=relative('/work',virtual);
    if(rel.startsWith('..')||isAbsolute(rel))throw Error('chart_capability_input_outside_task');
    const path=resolve(workspace,rel.startsWith('inputs/')?rel:rel.startsWith('outputs/')?'outputs/code/'+rel.slice(8):'code/'+rel);
    if(realpathSync(path)!==path||!lstatSync(path).isFile()||lstatSync(path).isSymbolicLink())throw Error('chart_capability_input_not_fixed');
    const raw=readFileSync(path),sha256=hash(raw),name='bound-'+index+'-'+sha256.slice(0,20)+'.json',target=join(workspace,'inputs',name);
    if(!existsSync(target))writeFileSync(target,raw,{flag:'wx',mode:0o400});
    if(hash(readFileSync(target))!==sha256)throw Error('chart_capability_bound_input_changed');
    callerInputs.push({path:virtual,sha256});
    return {path:'/work/inputs/'+name,sha256};
   });
   const values=valueMode?{values:args.values,output:args.output_directory}:{inputs:inputs.map((r:any)=>r.path),output:args.output_directory};
   const calls=join(directory,'capability-calls',execution.callId);mkdirSync(calls,{recursive:true,mode:0o700});
   const registry=join(calls,'registry.json');writeFileSync(registry,JSON.stringify(catalog.snapshot),{flag:'wx',mode:0o600});
   const refs=libraries??[{path:library,sha256:expected}];
   const manifest={format:valueMode?'script_capability_task_v1':'artifact_capability_task_v1',owner,task_id:taskId,workspace,registry_path:registry,
    libraries:valueMode?[]:refs,...(valueMode?{artifact_libraries:refs}:{}),inputs,resources:{network:'none'},
    grant:{id:'chart-'+execution.callId,task_id:taskId,snapshot_sha256:catalog.snapshot.digest,
     arguments_sha256:contract.capabilityDigest(values),root:selected,mode:'execute',effects:['workspace_write'],revoked:false}};
   const manifestPath=join(calls,'manifest.json');writeFileSync(manifestPath,JSON.stringify(manifest),{flag:'wx',mode:0o600});
   writeFileSync(join(calls,'args.json'),JSON.stringify(values),{flag:'wx',mode:0o600});
   record({phase:'started',name:'capability_call',call_id:execution.callId,arguments:args,input_versions:inputs});
   try{
    const result=await (valueMode?scripts.runScriptCapability:module.runArtifactCapability)(manifestPath,catalog.snapshot,values,{signal:execution.signal});
    writeFileSync(join(calls,'result.json'),JSON.stringify(result),{flag:'wx',mode:0o600});
    record({phase:'finished',name:'capability_call',call_id:execution.callId,arguments:args,result});
    const failures=result.receipts?.filter((receipt:any)=>receipt.status!=='succeeded')
     .map((receipt:any)=>({status:receipt.status,reason:receipt.reason}));
    const recovery=failures?.some((failure:any)=>failure.reason==='artifact_output_already_exists')?
     {argument:'output_directory',action:'choose_new_nonexistent_directory',rejected_path:args.output_directory,
      guidance:'Use another nonexistent directory under /work/outputs. Keep current input files if unchanged; do not delete or recreate the existing output directory.'}:undefined;
    return {status:result.status,result:result.result,
     current_inputs:valueMode?(result.receipts?.flatMap((receipt:any)=>receipt.backend_receipt?.value_materialization?.exported_inputs??[])??[]):callerInputs,
     failures,...(recovery?{recovery}:{})};
   }catch(error){record({phase:'failed',name:'capability_call',call_id:execution.callId,arguments:args,error:String(error)});throw error;}
  }});
}
