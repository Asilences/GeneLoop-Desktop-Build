/** Read-only projection of the libraries already admitted by the owning Runtime.
 * Reuses its existing availability/learning resolvers; never certifies or executes.
 */
import {createHash} from 'node:crypto';
import {readFileSync,lstatSync,realpathSync} from 'node:fs';
import {basename,dirname,join} from 'node:path';
import type {Scene} from './harless_settings.ts';

const sha=(value:string|Uint8Array)=>createHash('sha256').update(value).digest('hex');
const isHash=(value:unknown):value is string=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const shortTool=(name:string)=>name.split('__').at(-1)!;
const labels:Record<string,string>={ppt:'PPT', 'paper-proofreading':'论文核验','research-data-analysis':'数据分析'};
function read(path:string,expected?:string){
  const stat=lstatSync(path);
  if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1||stat.size>4*1024*1024||realpathSync(path)!==path)throw Error('library_evidence_unavailable');
  const bytes=readFileSync(path);if(expected&&sha(bytes)!==expected)throw Error('library_evidence_changed');
  return {value:JSON.parse(bytes.toString('utf8')),digest:sha(bytes)};
}

export function runtimeMotifEvidence(scene:Scene,unavailable:(scene:Scene)=>string|null){
  if(!scene.runtime_library||!isHash(scene.runtime_library_sha256))throw Error('runtime_library_not_admitted');
  const library=read(scene.runtime_library,scene.runtime_library_sha256),base=dirname(scene.runtime_library);
  const reason=unavailable(scene),evidence:any[]=[];
  const ref=(kind:string,digest:string)=>{const id=sha(kind+'\0'+digest);if(!evidence.some(e=>e.id===id))evidence.push({id,kind,sha256:digest,verification_scope:'host_reverified'});return id;};
  const libraryRef=ref('library',library.digest);
  const cert=scene.certification_path&&isHash(scene.certification_sha256)?read(scene.certification_path,scene.certification_sha256):null;
  const certificateRef=cert?ref('certificate',cert.digest):null;
  const dependencies:any[]=[];let report:any=null,reportRef:string|null=null;
  // File bindings were checked by the original loader. Recheck these bytes for display.
  for(const [name,digest]of Object.entries(cert?.value.file_locks??{})){
    if(basename(name)!==name||!isHash(digest))throw Error('library_evidence_binding_invalid');
    const file=read(join(base,name),digest);ref(name==='source-evidence.json'?'source_evidence':'bound_artifact',file.digest);
    if(name==='learning-report.json'){report=file.value;reportRef=ref('learning_report',file.digest);}
    dependencies.push({kind:'artifact',name,sha256:file.digest});
  }
  const historical=scene.runtime_kind==='data_receipts_v3';
  const rows=library.value.artifacts;
  if(!Array.isArray(rows))throw Error('library_format_not_projected');
  if(!historical&&(!cert||scene.certification_scope!=='independent_trace_structure'))throw Error('library_certification_not_admitted');
  const status=reason?'invalid':historical?'registered':'certified';
  const capabilities=rows.map((row:any)=>{
    const tools=historical?[row.from_tool,row.to_tool]:row.tools;
    if(!Array.isArray(tools)||!tools.length||tools.some(t=>typeof t!=='string'||!/^mcp__[a-z0-9_]+__[a-zA-Z0-9_]+$/.test(t)))throw Error('library_tools_invalid');
    const original=historical?row.motif_id:row.certified_digest;
    if(typeof original!=='string')throw Error('library_identity_missing');
    const flows=historical?[row]:row.transfer_evidence??[];
    const tool_flow=flows.map((flow:any)=>Object.fromEntries(['from_tool','to_tool','from_field','to_param'].map(k=>{if(typeof flow[k]!=='string')throw Error('library_flow_invalid');return [k,flow[k]];})));
    const entry=scene.certified_tool_schemas?.find(s=>s.name===tools[0]);
    return {id:sha(scene.id+'\0'+original),name:tools.map(shortTool).join(' → '),kind:'tool_flow',status,in_frozen_library:status==='certified',
      version:{library_generation:null,candidate_digest:isHash(original)?original:sha(JSON.stringify(row)),certificate_digest:cert?.digest??null},
      certification:{status,native_witness_tasks:historical?null:row.validation_task_fingerprint?1:null,candidate_execution_tasks:null,negative_kinds:[],scope:scene.certification_scope??null},
      contract:{language:historical?'receipt_transfer_v3':'sss-local-ops-v1',parameters_schema:entry?.parameters??library.value.tool_schemas?.[tools[0]]??{},
        read_scope:[],write_scope:[],dependency_sha256:null,effect_contract_sha256:null,environment_sha256:null},
      dependencies,cost:{amount_usd:null,known_model_cost_usd:null,currency:'USD',basis:'capability_attribution_unknown'},
      evidence_refs:[libraryRef,...(certificateRef?[certificateRef]:[])],tools,tool_flow,
      source_task_count:historical?row.training_task_count??null:Array.isArray(row.source_task_fingerprints)?new Set(row.source_task_fingerprints).size:null};
  });
  const release=scene.learning_version??(/^[-a-z0-9]+-v\d+$/.test(basename(base))||historical?basename(base):null);
  const revisions:any[]=[];
  for(const record of Object.values(report??{}) as any[]){
    if(record&&typeof record==='object'&&typeof record.previous_release==='string'&&/^(?:paper-web|ppt-master)-v\d+$/.test(record.previous_release)&&
      isHash(record.previous_certification_sha256)&&reportRef&&!revisions.some(row=>row.label===record.previous_release))
      revisions.push({label:record.previous_release,certificate_digest:record.previous_certification_sha256,current:false,evidence_ref:reportRef});
  }
  if(release)revisions.push({label:release,certificate_digest:cert?.digest??null,current:true,evidence_ref:certificateRef??libraryRef});
  const source={kind:scene.learning_version?'account_learning':'registered',label:labels[scene.id]??scene.label,release,compatibility:reason?'unavailable':'available',unavailable_reason:reason,revisions};
  const body={format:'geneloop-motif-evidence-v2',scenario:scene.id,display_only:true,execution_authorized:false,data_origin:'runtime_admitted_library',generated_at:new Date().toISOString(),source,
    library:{generation:null,snapshot_sha256:library.digest,registry_digest:sha(JSON.stringify({scene:scene.id,library:library.digest,certificate:cert?.digest??null,release})),certified_count:capabilities.filter(c=>c.status==='certified').length},
    capabilities,runs:[],events:[],evidence,exporter:{source_sha256:sha(readFileSync(new URL('./harless_motif_catalog.ts',import.meta.url))),schema_sha256:sha(readFileSync(new URL('../../config/motif-evidence-v2.schema.json',import.meta.url))),new_model_http_requests:0}};
  return {...body,export_digest:sha(JSON.stringify({...body,generated_at:null}))};
}

export function registerMotifCatalog(ctx:any,options:{scenes:()=>readonly Scene[];unavailable:(scene:Scene)=>string|null}){
  ctx.effect(()=>ctx.connection.fetch.register({path:'/api/harless/motif-catalog',methods:['GET'],requestBody:'buffered',
    async fetch(request:Request){
      const rejected=ctx.connection.requestRejection(request);if(rejected)return new Response('Unauthorized',{status:rejected});
      if(new URL(request.url).search)return Response.json({error:'此目录不接受路径或账号参数。'},{status:400});
      const libraries=options.scenes().filter(s=>s.runtime_kind||s.rsi_unavailable_reason).map(scene=>{
        try{return {id:'runtime:'+scene.id,title:labels[scene.id]??scene.label,scene:scene.id,status:'ready',evidence:runtimeMotifEvidence(scene,options.unavailable)};}
        catch{return {id:'runtime:'+scene.id,title:labels[scene.id]??scene.label,scene:scene.id,status:'unavailable',evidence:null};}
      });
      return Response.json({format:'geneloop-runtime-motif-catalog-v1',libraries},{headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
    }}),'geneloop-runtime-motif-catalog');
}
