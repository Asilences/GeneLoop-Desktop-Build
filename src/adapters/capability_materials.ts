/** Native contracts are reconstructed from original certified bytes on every read. */
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {capabilityRef,capabilityDigest,createCapabilitySnapshot,mapLegacyLibrary,
 validateCapabilitySnapshot,type CapabilitySnapshot} from './capability_contract.ts';
import {buildSourceCapabilities} from './source_capability_runtime.ts';
import {buildScriptCapabilities} from './script_capability_runtime.ts';
const hash=(raw:Buffer)=>createHash('sha256').update(raw).digest('hex');
function checked(ref:any){
 const raw=readFileSync(ref.path);if(hash(raw)!==ref.sha256)throw Error('material_evidence_changed');return raw;
}
export function extendCapabilitySeed(seed:CapabilitySnapshot,index:any){
 validateCapabilitySnapshot(seed);
 if(index.owner!==seed.owner||!Array.isArray(index.materials))throw Error('material_owner_changed');
 const caps=new Map(seed.capabilities.map(c=>[c.id,c])),roots=new Map(seed.roots.map(r=>[r.id,r]));
 const catalog:any[]=[];
 for(const row of index.materials){
  if(row.owner!==seed.owner||row.format!=='capability_material_v1'||!row.evidence?.length)throw Error('material_admission_invalid');
  row.evidence.forEach(checked);const bytes=checked(row.library);
  const mapped=row.backend==='source_program'?buildSourceCapabilities(bytes,seed.owner):
   row.backend==='script_motif'?buildScriptCapabilities(row.library.path,seed.owner,row.library.sha256):
   row.backend==='artifact_motif'?{capabilities:mapLegacyLibrary(bytes,seed.owner,'artifact_motif',row.library.sha256).map(c=>({...c,certification:'certified' as const})),catalog:[]}:
   (()=>{throw Error('material_backend_unsupported');})();
  for(const c of mapped.capabilities){
   const prior=caps.get(c.id);
   if(prior&&capabilityDigest(capabilityRef(prior))!==capabilityDigest(capabilityRef(c)))throw Error('material_identity_conflict');
   // A withdrawn/archived seed cannot be resurrected by an admission record.
   if(prior)continue;
   caps.set(c.id,c);roots.set(c.id,capabilityRef(c));
  }
  catalog.push(...mapped.catalog);
 }
 return {snapshot:createCapabilitySnapshot(seed.owner,[...roots.values()],[...caps.values()]),catalog};
}
