/** Structural admission only; never executes a task or repairs model output. */
import {readFileSync} from 'node:fs';
import {validateProgram} from '../src/adapters/paper_rsi_program.ts';
import {validateJevRequest} from '../src/adapters/kouri_jev.ts';
try{
 const input=JSON.parse(readFileSync(0,'utf8'));
 if(input.kind==='typed_request'){
  validateJevRequest(input.request);
  process.stdout.write(JSON.stringify({ok:true,task_tools_executed:false,candidate_modified:false})+'\n');
 }else{
 const {patch,allowed_components:allowed}=input;
 const programs=new Set(['guard','request','bind']);
 const names=new Set([...programs,'description','scope_description','training_witnesses']);
 if(!patch||typeof patch!=='object'||Array.isArray(patch)||!Object.keys(patch).length)throw Error('nonempty component patch required');
 for(const [name,value]of Object.entries(patch)){
  if(!names.has(name)||(allowed&&!allowed.includes(name)))throw Error('unrequested component: '+name);
  if(programs.has(name))validateProgram(value);
  else if(name==='training_witnesses'){
   if(!Array.isArray(value)||!value.length)throw Error('actual training witnesses required');
   for(const row of value){
    if(!row||typeof row.snapshot_id!=='string'||!row.values||typeof row.values!=='object'||Array.isArray(row.values)||
       Object.values(row.values).some(v=>!['boolean','string'].includes(typeof v)))throw Error('invalid typed training witness');
   }
  }else if(typeof value!=='string'||!value.trim())throw Error('complete metadata string required');
 }
 process.stdout.write(JSON.stringify({ok:true,task_tools_executed:false,candidate_modified:false})+'\n');
 }
}catch(error){
 process.stdout.write(JSON.stringify({ok:false,error:String(error),task_tools_executed:false,candidate_modified:false})+'\n');
 process.exitCode=1;
}
