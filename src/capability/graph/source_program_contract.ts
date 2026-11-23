/** Validate and identify source program definitions. */
import {assertSupportedJsonSchema} from '@deepseek-ai/dsh-tools';
import {digest} from '../../motif_core/runtime/online_skill_runtime.mjs';

export const parameterToken='__GENELOOP_PARAMETERS__';
export function sourceProgramIdentity(program:any){
 return Object.fromEntries(['format','language','template','parameters_schema'].map(key=>[key,program[key]]));
}
export function validateSourceProgram(program:any){
 if(program?.format!=='parameterized_source_program_v1'||!['tsx','javascript'].includes(program.language)||
   typeof program.template!=='string'||Buffer.byteLength(program.template)>100000||program.template.split(parameterToken).length!==2||
   program.id!=='source_'+digest(sourceProgramIdentity(program)).slice(0,24)||program.parameters_schema?.type!=='object')throw Error('source_program_changed');
 assertSupportedJsonSchema(program.parameters_schema);
 return program;
}
