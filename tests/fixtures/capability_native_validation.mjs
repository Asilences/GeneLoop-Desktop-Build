/** Synthetic library admission cases; no stored program executes. */
import {createHash} from 'node:crypto';
import {digest} from '../../src/motif_core/online_skill_runtime.mjs';
import {validateSourceProgram} from '../../src/adapters/source_program_runtime.ts';
const cases=[
 ['duplicate_required',{type:'object',properties:{x:{type:'integer'}},required:['x','x']},'const x=__GENELOOP_PARAMETERS__;'],
 ['scalar_input',{type:'number'},'const x=__GENELOOP_PARAMETERS__;'],
 ['oversize_template',{type:'object'},'x'.repeat(100001)+'__GENELOOP_PARAMETERS__'],
];
const fixtures=cases.map(([name,schema,template])=>{
 const identity={format:'parameterized_source_program_v1',language:'javascript',template,parameters_schema:schema};
 const sha=digest(identity),program={...identity,id:'source_'+sha.slice(0,24),status:'certified',certification:{program_identity:sha,source_equivalent:true}};
 const body={format:'source_program_library_v1',programs:[program]},raw=JSON.stringify({...body,digest:digest(body)});
 let accepted=true;try{validateSourceProgram(program);}catch{accepted=false;}
 return {name,raw,sha:createHash('sha256').update(raw).digest('hex'),native_accepted:accepted};
});
process.stdout.write(JSON.stringify(fixtures));
