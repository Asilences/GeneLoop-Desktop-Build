/** Sidecar contracts only. Certification/status claims never grant execution. */
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {assertSupportedJsonSchema,validateJsonSchemaValue} from '@deepseek-ai/dsh-tools';
import {digest as legacyDigest} from '../motif_core/online_skill_runtime.mjs';
import {validateSourceProgram} from './source_program_runtime.ts';

export type CapabilityRef={id:string;sha256:string};
export type Binding={kind:'input';path:string[]}|{kind:'step';step_id:string;path:string[]}|{kind:'literal';value:any}|{kind:'object';fields:Record<string,Binding>}|{kind:'array';items:Binding[]};
export type LegacyRef={backend:'source_program'|'artifact_motif';library_sha256:string;library_digest:string;object_id:string;object_sha256:string;certificate_sha256:string};
export type CapabilityDefinition={owner:string;contract:{input_schema:any;output_schema:any;effects:string[]};implementation:{kind:'legacy';legacy_ref:LegacyRef}|{kind:'composition';steps:{id:string;capability:CapabilityRef;arguments:Binding}[];output:Binding};dependencies:CapabilityRef[]};
export type Capability=CapabilityDefinition&{format:'capability_v1';id:string;revision_sha256:string;lifecycle:'active'|'build_only'|'archived';certification:'candidate'|'certified'|'rejected';migration:'legacy'|'testing'|'canary'|'promoted'};
export type CapabilitySnapshot={format:'capability_snapshot_v1';owner:string;roots:CapabilityRef[];capabilities:Capability[];digest:string};
const schema=JSON.parse(readFileSync(new URL('../../schemas/capability-v1.schema.json',import.meta.url),'utf8'));
assertSupportedJsonSchema(schema);
const identityKeys=['owner','contract','implementation','dependencies'];
const artifactKeys=['version','source','inputs','dependencies','input_argument_indices','output_argument_index','argument_count','language','execution_policy'];
const reserved=new Set(['__proto__','prototype','constructor']);
const fail=(reason:string):never=>{throw Error('capability_'+reason);};
const hash=(value:string|Buffer)=>createHash('sha256').update(value).digest('hex');
function unicode(value:any):string {
 if(typeof value!=='string'||[...value].some(c=>c.codePointAt(0)!>=0xd800&&c.codePointAt(0)!<=0xdfff))fail('invalid_unicode');
 return value;
}
function unicodeOrder(a:string,b:string){
 const aa=[...a],bb=[...b];for(let i=0;i<Math.min(aa.length,bb.length);i++){const n=aa[i].codePointAt(0)!-bb[i].codePointAt(0)!;if(n)return n;}
 return aa.length-bb.length;
}
function tag(value:any,depth=0):any {
 if(depth>64)fail('too_deep');
 if(value===null)return ['null'];
 if(typeof value==='boolean')return ['boolean',value];
 if(typeof value==='number'){
  if(!Number.isFinite(value)||Math.abs(value)>Number.MAX_SAFE_INTEGER)fail('number_out_of_range');
  const bytes=Buffer.alloc(8);bytes.writeDoubleBE(value===0?0:value);return ['number',bytes.toString('hex')];
 }
 if(typeof value==='string')return ['string',unicode(value)];
 if(Array.isArray(value))return ['array',Array.from(value,v=>tag(v,depth+1))];
 if(value&&typeof value==='object'&&(Object.getPrototypeOf(value)===Object.prototype||Object.getPrototypeOf(value)===null))
  return ['object',Object.keys(value).sort(unicodeOrder).map(k=>[unicode(k),tag(value[k],depth+1)])];
 return fail('non_json_value');
}
/** Typed canonical JSON, Unicode scalar order and IEEE754 float64 number bytes. */
export function capabilityDigest(value:unknown){
 const encoded=JSON.stringify(tag(value));if(Buffer.byteLength(encoded)>4_000_000)fail('too_large');return hash(encoded);
}
// Hash equivalence alone does not make -0 valid wire data. Do not normalize
// original legacy bytes; reject negative zero only in new Capability records.
function wireValues(value:any){
 if(Object.is(value,-0))fail('negative_zero');
 if(Array.isArray(value)){for(const child of value)wireValues(child);}
 else if(value&&typeof value==='object'){for(const child of Object.values(value))wireValues(child);}
}
function identifier(value:any){if(typeof value!=='string'||!value.replace(/^[ \t\r\n\f\v]+|[ \t\r\n\f\v]+$/g,'')||[...value].length>256)fail('identifier_invalid');unicode(value);}
function sha(value:any){if(typeof value!=='string'||!(/^[a-f0-9]{64}$/).test(value))fail('digest_invalid');}
function shape(value:any,keys:string[]){if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).length!==keys.length||keys.some(k=>!Object.hasOwn(value,k)))fail('shape_invalid');}
function refKey(ref:any){shape(ref,['id','sha256']);sha(ref.sha256);if(ref.id!=='cap_'+ref.sha256.slice(0,24))fail('reference_invalid');return ref.id+':'+ref.sha256;}
function binding(value:any,earlier:Set<string>,depth=0){
 if(depth>32||!value||typeof value!=='object'||Array.isArray(value))fail('binding_invalid');
 switch(value.kind){
 case 'input':case 'step':
  shape(value,value.kind==='step'?['kind','path','step_id']:['kind','path']);
  if(!Array.isArray(value.path)||value.path.length>32||value.path.some((k:any)=>typeof k!=='string'||reserved.has(k)))fail('binding_path_invalid');
  if(value.kind==='step'&&!earlier.has(value.step_id))fail('binding_step_unavailable');break;
 case 'literal':shape(value,['kind','value']);capabilityDigest(value.value);break;
 case 'object':
  shape(value,['kind','fields']);if(!value.fields||typeof value.fields!=='object'||Array.isArray(value.fields)||Object.keys(value.fields).some(k=>reserved.has(k)))fail('binding_fields_invalid');
  for(const child of Object.values(value.fields))binding(child,earlier,depth+1);break;
 case 'array':shape(value,['kind','items']);if(!Array.isArray(value.items))fail('binding_items_invalid');for(const child of value.items)binding(child,earlier,depth+1);break;
 default:fail('binding_kind_invalid');
 }
}
export function capabilityIdentity(value:Capability|CapabilityDefinition){return Object.fromEntries(identityKeys.map(k=>[k,(value as any)[k]])) as CapabilityDefinition;}
export function validateCapability(value:any,expectedOwner?:string):Capability {
 capabilityDigest(value);wireValues(value);
 if(value?.format!=='capability_v1'||validateJsonSchemaValue(schema,value).length)fail('schema_invalid');
 identifier(value.owner);if(expectedOwner!==undefined&&value.owner!==expectedOwner)fail('foreign_owner');
 assertSupportedJsonSchema(value.contract.input_schema);assertSupportedJsonSchema(value.contract.output_schema);
 const effects=value.contract.effects;
 if(!effects.length||new Set(effects).size!==effects.length||effects.some((e:string)=>!['read','workspace_write','external_write','opaque'].includes(e)))fail('effects_invalid');
 const deps=value.dependencies.map(refKey);
 if(new Set(deps).size!==deps.length||JSON.stringify(deps)!==JSON.stringify([...deps].sort()))fail('dependencies_not_unique_sorted');
 const impl=value.implementation;
 if(impl.kind==='legacy'){
  const ref=impl.legacy_ref;if(!['source_program','artifact_motif'].includes(ref.backend)||deps.length)fail('legacy_backend_or_dependencies');
  identifier(ref.object_id);for(const k of ['library_sha256','library_digest','object_sha256','certificate_sha256'])sha(ref[k]);
 }else{
  if(impl.steps.length<1||impl.steps.length>64)fail('steps_invalid');const earlier=new Set<string>(),called=new Set<string>();
  for(const step of impl.steps){identifier(step.id);if(earlier.has(step.id)||reserved.has(step.id))fail('step_duplicate_or_reserved');called.add(refKey(step.capability));binding(step.arguments,earlier);earlier.add(step.id);}
  binding(impl.output,earlier);if(called.size!==deps.length||deps.some((d:string)=>!called.has(d)))fail('dependencies_do_not_match_calls');
 }
 const revision=capabilityDigest(capabilityIdentity(value));if(value.revision_sha256!==revision||value.id!=='cap_'+revision.slice(0,24))fail('identity_changed');
 return structuredClone(value);
}
export function createCapability(definition:CapabilityDefinition,states:Partial<Pick<Capability,'lifecycle'|'certification'|'migration'>>={}):Capability {
 shape(definition,identityKeys);if(Object.keys(states).some(k=>!['lifecycle','certification','migration'].includes(k)))fail('states_invalid');
 const body=structuredClone(definition);body.dependencies.sort((a,b)=>refKey(a)<refKey(b)?-1:refKey(a)>refKey(b)?1:0);
 const revision=capabilityDigest(body);
 return validateCapability({format:'capability_v1',id:'cap_'+revision.slice(0,24),revision_sha256:revision,...body,lifecycle:states.lifecycle===undefined?'build_only':states.lifecycle,certification:states.certification===undefined?'candidate':states.certification,migration:states.migration===undefined?'testing':states.migration});
}
export function capabilityRef(value:Capability):CapabilityRef{const checked=validateCapability(value);return {id:checked.id,sha256:checked.revision_sha256};}
export function validateCapabilitySnapshot(value:any,expectedOwner?:string):CapabilitySnapshot {
 capabilityDigest(value);wireValues(value);if(value?.format!=='capability_snapshot_v1'||validateJsonSchemaValue(schema,value).length)fail('snapshot_schema_invalid');
 identifier(value.owner);if(expectedOwner!==undefined&&value.owner!==expectedOwner)fail('foreign_owner');
 const roots=value.roots.map(refKey);if(!roots.length||new Set(roots).size!==roots.length||JSON.stringify(roots)!==JSON.stringify([...roots].sort()))fail('roots_not_unique_sorted');
 const capabilities:Capability[]=value.capabilities.map((c:Capability)=>validateCapability(c,value.owner)),ids=capabilities.map(c=>c.id);
 if(new Set(ids).size!==ids.length||JSON.stringify(ids)!==JSON.stringify([...ids].sort()))fail('snapshot_duplicates_or_order');
 const lookup=new Map(capabilities.map(c=>[c.id,c])),visiting=new Set<string>(),visited=new Set<string>();
 function visit(ref:CapabilityRef){
  const key=refKey(ref);if(visiting.has(key))fail('dependency_cycle');if(visited.has(key))return;
  const target=lookup.get(ref.id);if(!target||target.revision_sha256!==ref.sha256)fail('dependency_missing_or_changed');
  visiting.add(key);for(const dependency of target.dependencies)visit(dependency);visiting.delete(key);visited.add(key);
 }
 for(const ref of value.roots)visit(ref);if(visited.size!==capabilities.length)fail('snapshot_extra_capability');
 const {digest,...body}=value;if(digest!==capabilityDigest(body))fail('snapshot_changed');return structuredClone(value);
}
export function createCapabilitySnapshot(owner:string,roots:CapabilityRef[],capabilities:Capability[]):CapabilitySnapshot {
 const body={format:'capability_snapshot_v1',owner,roots:structuredClone(roots).sort((a,b)=>refKey(a)<refKey(b)?-1:refKey(a)>refKey(b)?1:0),capabilities:structuredClone(capabilities).sort((a,b)=>a.id<b.id?-1:a.id>b.id?1:0)};
 return validateCapabilitySnapshot({...body,digest:capabilityDigest(body)},owner);
}
/** Authoritative legacy mapping, preserving existing native digest semantics.
 * Exact original bytes/IDs/certificates remain unchanged. Native code locks and
 * execution authorization are still backend duties, not mapping side effects. */
export function mapLegacyLibrary(raw:string|Buffer,owner:string,backend:'source_program'|'artifact_motif',expectedSha256:string):Capability[]{
 const bytes=typeof raw==='string'?Buffer.from(raw):raw;sha(expectedSha256);
 if(!Buffer.isBuffer(bytes)||bytes.length>4_000_000||hash(bytes)!==expectedSha256)fail('legacy_bytes_changed');
 const rawText=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
 const library=JSON.parse(rawText);capabilityDigest(library);
 const {digest,...body}=library;
 if(!['source_program','artifact_motif'].includes(backend)||digest!==legacyDigest(body)||!Array.isArray(library.programs))fail('legacy_library_invalid');
 if(backend==='source_program'&&library.format!=='source_program_library_v1'||backend==='artifact_motif'&&(library.kind!=='witnessed_artifact_program_library'||library.version!==1))fail('legacy_format_invalid');
 const ids=new Set(),result:Capability[]=[];
 for(const p of library.programs){
  if(ids.has(p.id))fail('legacy_duplicate');ids.add(p.id);
  const keys=backend==='source_program'?['format','language','template','parameters_schema']:artifactKeys;
  if(keys.some(k=>!Object.hasOwn(p,k)))fail('legacy_identity_missing');
  const identity=Object.fromEntries(keys.map(k=>[k,p[k]])),objectSha256=legacyDigest(identity),certificate=p.certification;
  if(!certificate||typeof certificate!=='object'||Array.isArray(certificate)||certificate.source_equivalent!==true)fail('legacy_certificate_missing');
  let inputSchema:any;
  if(backend==='source_program'){
   validateSourceProgram(p);
   if(p.status!=='certified'||certificate.program_identity!==objectSha256)fail('legacy_identity_changed');
   inputSchema=p.parameters_schema;
  }else{
   if(p.id!=='artifact_'+objectSha256.slice(0,24)||p.language!=='python'||p.execution_policy!=='fresh_output_network_disabled_v1'||p.source_sha256!==hash(p.source)||certificate.program_sha256!==objectSha256||certificate.passed!==true||typeof certificate.distinct_inputs!=='number'||certificate.distinct_inputs<2)fail('legacy_identity_changed');
   inputSchema={type:'object',properties:{inputs:{type:'array',items:{type:'string'}},output:{type:'string'}},required:['inputs','output'],additionalProperties:false};
  }
  result.push(createCapability({owner,contract:{input_schema:inputSchema,output_schema:{type:'object'},effects:['workspace_write']},implementation:{kind:'legacy',legacy_ref:{backend,library_sha256:expectedSha256,library_digest:digest,object_id:p.id,object_sha256:objectSha256,certificate_sha256:legacyDigest(certificate)}},dependencies:[]},{migration:'legacy'}));
 }
 return result;
}
