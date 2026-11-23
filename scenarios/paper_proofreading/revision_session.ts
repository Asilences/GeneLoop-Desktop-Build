/** Published structural reference audit and edit programs over a private task copy. */
import {createHash} from 'node:crypto';
import {existsSync,readFileSync,writeFileSync,mkdirSync,lstatSync,readdirSync,realpathSync,renameSync} from 'node:fs';
import {join,resolve,relative,isAbsolute,sep} from 'node:path';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';
import {validateJsonSchemaValue} from '@deepseek-ai/dsh-tools';
import {runTraceTool,validateTraceCandidate} from '../../src/adapters/trace_rsi_program.ts';
import {digest} from '../../src/adapters/paper_rsi_program.ts';
import {applyPublishedRevision,renderRevisionMarkdown} from '../../src/adapters/report_patch_protocol.ts';
const sha=(v:Uint8Array)=>createHash('sha256').update(v).digest('hex');
const ROOT=resolve(fileURLToPath(new URL('../../',import.meta.url)));
const revisionSources={
  'audit-program.json':'94fb613036b0450ec893853b929b12a782f1c5cd722d693add81c59f5bdf3407',
  'patch-program.json':'0eb7527ba697c787ce2ebc1843f50ff339865e301f97a6349ce138db3760d333',
  'tool-schemas.json':'97b95b1970a46363c6178918509e4caa9b01e8141a7691861605ca685b14c117',
} as const;
export function revisionTools(work:string,privateRoot?:string){
  work=realpathSync(work);const scope=realpathSync(privateRoot??process.env.HARLESS_PRIVATE_ROOT??join(ROOT,'.local')),rel=relative(scope,work);
  if(!scope.split(sep).includes('.local')||isAbsolute(rel)||rel.startsWith('..')||!work.endsWith('/work')&& !work.endsWith('\\work'))throw Error('private_session_workspace_required');
  const revision=join(ROOT,'scenarios/paper_proofreading/revision');
  function revisionSource(name:keyof typeof revisionSources):Buffer {
    const bytes=readFileSync(join(revision,name));
    if(sha(bytes)!==revisionSources[name])throw Error('paper_program_changed');
    return bytes;
  }
  const audit=JSON.parse(revisionSource('audit-program.json').toString('utf8'));
  const patch=JSON.parse(revisionSource('patch-program.json').toString('utf8'));
  const schemas=JSON.parse(revisionSource('tool-schemas.json').toString('utf8'));
  validateTraceCandidate(audit);validateTraceCandidate(patch);
  const directory=join(work,'outputs/paper');mkdirSync(directory,{recursive:true,mode:0o700});
  const path=join(directory,'report-state.json');
  function save(v:any){writeFileSync(path+'.tmp',JSON.stringify(v),{mode:0o600});renameSync(path+'.tmp',path);}
  function guard(){
    for(const name of Object.keys(revisionSources) as (keyof typeof revisionSources)[])revisionSource(name);
    const approved=JSON.parse(readFileSync(join(work,'approved-inputs.json'),'utf8')).files;
    if(JSON.stringify(Object.keys(approved).sort())!==JSON.stringify(readdirSync(join(work,'inputs')).sort()))throw Error('paper_source_set_changed');
    for(const [name,hash]of Object.entries(approved)){
      const p=join(work,'inputs',name),st=lstatSync(p);
      if(!st.isFile()||st.isSymbolicLink()||st.nlink!==1||sha(readFileSync(p))!==hash)throw Error('paper_source_changed');
    }
    return digest(approved);
  }
  function state(){
    const source=guard();
    if(!existsSync(path)){
      const approved=JSON.parse(readFileSync(join(work,'approved-inputs.json'),'utf8')).files;
      const input=Object.keys(approved).find(n=>n.endsWith('.json'));
      const supplied=input?JSON.parse(readFileSync(join(work,'inputs',input),'utf8')):{};
      const report=supplied.report??supplied;
      save({source,report:Array.isArray(report.references)?report:{references:[]},before:Array.isArray(report.references)?report:{references:[]},
        catalog_cited_records:supplied.catalog_cited_records??[],catalog_query_items:supplied.catalog_query_items??[],citation_issues:supplied.citation_issues??[]});
    }
    const st=lstatSync(path);if(!st.isFile()||st.isSymbolicLink()||st.nlink!==1||st.size>192000)throw Error('private_report_required');
    const value=JSON.parse(readFileSync(path,'utf8'));if(value.source!==source)throw Error('paper_report_source_changed');
    return value;
  }
  function receipt(value:any){const hash=digest(value.report);return{input_id:'trace-input-'+digest([work,value.source,hash]),report_sha256:hash,source_version:value.source,scope:'structural_revision_only_unverified_bibliography'};}
  function call(name:string,args:any){
    const value=state(),r=receipt(value);
    if(name==='read_task_state')return{...r,report:value.report,source_records:value.catalog_cited_records,query_items:value.catalog_query_items,
      note:'仅校对本任务副本中的参考条目结构，不认证文献真实性。普通PDF/LaTeX校对使用 paper_checks。'};
    if(name==='apply_revision_plan'){
      if(args.report_sha256!==r.report_sha256)throw Error('stale_report_write');
      const result=applyPublishedRevision(value.report,args.plan,patch);value.report=result.report;save(value);guard();return receipt(value);
    }
    if(args.input_id!==r.input_id)throw Error('unknown_or_stale_input_id');
    // The learned audit has a narrow frozen schema. Project its structural
    // fields while preserving every original field in state and exported text.
    // The patch verifier independently preserves all fields outside the plan.
    const auditReport=(report:any)=>({scope:report.scope??'uploaded_structure_only_unverified',
      citation_issues:report.citation_issues??value.citation_issues,
      references:report.references.map((row:any)=>{
        const names=Object.keys(audit.input_schema.properties.before_report.properties.references.items.properties);
        const projected=Object.fromEntries(names.filter(key=>row[key]!==undefined).map(key=>[key,row[key]]));
        return{...projected,key:row.key??'',arxiv_id:row.arxiv_id??'',status:row.status??'未提供；需核验'};
      })});
    const input={catalog_cited_records:value.catalog_cited_records,catalog_query_items:value.catalog_query_items,citation_issues:value.citation_issues,
      triage_references:value.report.references.map((row:any)=>({key:row.key??'',arxiv_id:row.arxiv_id??''})),
      before_report:auditReport(value.before),after_report:auditReport(value.report)};
    const errors=validateJsonSchemaValue(audit.input_schema,input);if(errors.length)throw Error('invalid_reference_context: '+errors.slice(0,3).join(';'));
    const output=runTraceTool(audit,input);guard();
    if(name==='triage_revision_audit')return{...r,output};
    if(name==='export_revision_report'){
      const md=renderRevisionMarkdown(value.before,value.report,output);
      const destination=join(directory,'revision-report.md');
      if(existsSync(destination)){const st=lstatSync(destination);if(!st.isFile()||st.isSymbolicLink()||st.nlink!==1)throw Error('private_artifact_required');}
      writeFileSync(destination+'.tmp',md,{mode:0o600});renameSync(destination+'.tmp',destination);
      return{...r,artifact_name:'revision-report.md',artifact_sha256:sha(Buffer.from(md)),output};
    }
    throw Error('unknown_tool');
  }
  const tools=schemas.map((row:any)=>({name:row.name.replace('mcp__paper_trace_rsi__',''),description:row.name.endsWith('read_task_state')?'Read the current private reference report and version. No authenticity claim.':
    row.name.endsWith('apply_revision_plan')?'Apply the model-selected bounded reference plan to a new task copy; preserve other fields.':row.name.endsWith('triage_revision_audit')?'Run the existing learned audit program on the current versioned reference report.':'Export the current reviewed structural report as Markdown in this task only.',inputSchema:row.parameters}));
  return{tools,call};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const api=revisionTools(process.argv[2]),lines=createInterface({input:process.stdin});
  lines.on('line',line=>{
    let req:any;try{req=JSON.parse(line);}catch{return;}if(req.id===undefined)return;
    let result:any;
    try{
      if(req.method==='initialize')result={protocolVersion:req.params?.protocolVersion??'2024-11-05',capabilities:{tools:{}},serverInfo:{name:'paper-trace-rsi',version:'1'}};
      else if(req.method==='tools/list')result={tools:api.tools};
      else if(req.method==='tools/call'){const value=api.call(req.params.name,req.params.arguments??{});result={content:[{type:'text',text:JSON.stringify(value)}],structuredContent:value};}
      else result={};
    }catch(error:any){result={isError:true,content:[{type:'text',text:error.message}]};}
    process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:req.id,result})+'\n');
  });
}
