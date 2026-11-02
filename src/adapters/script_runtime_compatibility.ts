/** Host-owned compatibility policy. Historical compiler hashes stay provenance;
 * execution changes require an exact, reviewed old -> current hash pair.
 * A library or model proposal cannot supply exceptions.
 */
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const root=fileURLToPath(new URL('../../',import.meta.url));
const hash=(raw:Buffer)=>createHash('sha256').update(raw).digest('hex');
export const scriptProvenanceLocks=new Set([
 'scripts/learn-script-motifs.py','src/adapters/script_motif_compiler.py',
 'src/adapters/script_dataflow_compiler.py','scripts/certify-script-motifs.mjs',
]);
export function assertScriptRuntimeCompatibility(locks:Record<string,string>,paths:string[]){
 if(!locks||typeof locks!=='object')throw Error('script_runtime_changed');
 const policy=JSON.parse(readFileSync(join(root,'config/script-runtime-compatibility.json'),'utf8'));
 if(policy.version!==1||!Array.isArray(policy.transitions))throw Error('script_compatibility_policy_invalid');
 for(const path of paths){
  const recorded=locks[path];
  if(typeof recorded!=='string'||!/^[a-f0-9]{64}$/.test(recorded))throw Error('script_runtime_changed');
  if(scriptProvenanceLocks.has(path))continue;
  const current=hash(readFileSync(join(root,path)));
  if(current===recorded)continue;
  if(!policy.transitions.some((row:any)=>row.path===path&&row.from_sha256===recorded&&row.to_sha256===current))
   throw Error('script_runtime_changed');
 }
}
