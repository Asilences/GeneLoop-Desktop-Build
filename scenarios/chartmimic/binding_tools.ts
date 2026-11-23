/** Certification input IO only: actual JSON roles, no renderer or value filling. */
import {readFileSync,writeFileSync,renameSync,realpathSync,lstatSync,existsSync,appendFileSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

export const name='chartmimic-current-json-binding';
export const inject=['tools'];
const sha=(raw:Buffer|string)=>createHash('sha256').update(raw).digest('hex');
const wireSchema=(schema:any):any=>{
 if(!schema||typeof schema!=='object'||Array.isArray(schema))return schema;
 const result=Object.fromEntries(Object.entries(schema).map(([key,value])=>[key,
  key==='properties'?Object.fromEntries(Object.entries(value as any).map(([name,child])=>[name,wireSchema(child)])):
  key==='items'?wireSchema(value):value]));
 if(result.type==='array'&&!Object.hasOwn(result,'items'))result.items={};
 return result;
};
export function apply(ctx:any){
 const directory=realpathSync(process.env.GENELOOP_CHART_RUN!);
 const workspace=realpathSync(process.env.GENELOOP_CHART_WORKSPACE!);
 const code=realpathSync(join(workspace,'code'));
 if(code!==join(workspace,'code'))throw Error('chart_binding_target_changed');
 const raw=readFileSync(process.env.GENELOOP_CHART_BINDING!);
 if(sha(raw)!==process.env.GENELOOP_CHART_BINDING_SHA256)throw Error('chart_binding_spec_changed');
 const spec=JSON.parse(raw.toString('utf8'));
 const files=spec.files;
 if(spec.format!=='chartmimic_current_json_binding_v1'||!Array.isArray(files)||!files.length||
    new Set(files.map((f:any)=>f.role)).size!==files.length||new Set(files.map((f:any)=>f.path)).size!==files.length||
    files.some((f:any)=>!/^\/work\/[A-Za-z0-9_-]+\.json$/.test(f.path)||!/^[a-z][a-z0-9_]{0,63}$/.test(f.role)))throw Error('chart_binding_spec_invalid');
 const record=(row:any)=>appendFileSync(join(directory,'native-tools.jsonl'),JSON.stringify(row)+'\n',{mode:0o600});
 ctx.tools.register({name:'submit_binding',
  description:'Submit the CURRENT JSON value for every declared input role. The host validates the original input schemas and writes the fixed JSON files. Supply all current chart data and settings yourself; no placeholders, scripts or rendering. Validation errors are returned for you to correct.',
  parameters:wireSchema(spec.parameters),
  output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(value)}]},
  async execute(args:any,execution:any){
   if(!/^[A-Za-z0-9_-]{1,160}$/.test(execution.callId))throw Error('chart_binding_call_id_invalid');
   const require=createRequire(join(process.env.GENELOOP_CHART_RUNTIME!,'package.json'));
   const sdk=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-tools')).href);
   const errors=sdk.validateJsonSchemaValue(spec.parameters,args).map(String);
   if(errors.length){
    const result={status:'invalid',errors};
    record({phase:'finished',name:'submit_binding',call_id:execution.callId,arguments:args,result});return result;
   }
   const prepared=[];
   for(const file of files){
    const path=join(code,file.path.slice('/work/'.length));
    if(realpathSync(join(workspace,'code'))!==code||existsSync(path)&&(!lstatSync(path).isFile()||lstatSync(path).isSymbolicLink()))throw Error('chart_binding_target_changed');
    let text;
    try{text=JSON.stringify(args[file.role],(_key,value)=>{
     if(typeof value==='number'&&!Number.isFinite(value)||value===undefined||['bigint','function','symbol'].includes(typeof value))throw Error('non_json_value');
     return value;
    },2)+'\n';}catch(error){
     const result={status:'invalid',errors:['strict_JSON_value_required:'+String(error)]};
     record({phase:'finished',name:'submit_binding',call_id:execution.callId,arguments:args,result});return result;
    }
    prepared.push({file,path,text});
   }
   const written=[];
   for(const [index,{file,path,text}] of prepared.entries()){
    const temporary=join(code,'.binding-'+execution.callId+'-'+index+'.tmp');
    writeFileSync(temporary,text,{flag:'wx',mode:0o600});renameSync(temporary,path);
    written.push({role:file.role,path:file.path,sha256:sha(readFileSync(path)),bytes:Buffer.byteLength(text)});
   }
   const result={status:'written',files:written};
   record({phase:'finished',name:'submit_binding',call_id:execution.callId,arguments:args,result});return result;
  }});
}
