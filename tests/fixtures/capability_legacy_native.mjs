/** Synthetic native legacy bytes, including JSON spellings Python digests differ on. */
import {digest} from '../../src/motif_core/online_skill_runtime.mjs';
import {createHash} from 'node:crypto';
import {mapLegacyLibrary} from '../../src/adapters/capability_contract.ts';
const identity={format:'parameterized_source_program_v1',language:'javascript',template:'const x=__GENELOOP_PARAMETERS__;',parameters_schema:{type:'object',properties:{weight:{type:'number',default:0.1}},additionalProperties:false}};
const id=digest(identity);
const program={...identity,id:'source_'+id.slice(0,24),status:'certified',certification:{source_equivalent:true,program_identity:id,elapsed_seconds:1,fraction:0.1,'𐀀':1,'':2}};
const body={format:'source_program_library_v1',programs:[program],elapsed_seconds:1,fraction:0.1,description:'𐀀 unicode string'};
const raw=JSON.stringify({...body,digest:digest(body)}).replaceAll('"elapsed_seconds":1,','"elapsed_seconds":1.0,');
const sha=createHash('sha256').update(raw).digest('hex');
process.stdout.write(JSON.stringify({raw,sha,mapped:mapLegacyLibrary(raw,'owner','source_program',sha)}));
