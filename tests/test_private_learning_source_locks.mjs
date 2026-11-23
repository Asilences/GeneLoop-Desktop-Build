import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdirSync,mkdtempSync,readFileSync,realpathSync,rmSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {createPaperLearning} from '../src/adapters/web/learning/harless_paper_learning.ts';
import {createPptLearning} from '../src/adapters/web/learning/harless_ppt_learning.ts';

const root=resolve(import.meta.dirname,'..');
const read=path=>JSON.parse(readFileSync(path,'utf8'));
const write=(path,value)=>writeFileSync(path,JSON.stringify(value));
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const fileHash=path=>hash(readFileSync(path));
const policy=read(join(root,'config/rsi-privacy-code-compat.json'));

for(const {name,create,scene,runtimeKind,bindingPolicy} of [
 {name:'paper',create:createPaperLearning,scene:'paper-proofreading',runtimeKind:'paper_document_read_v1',bindingPolicy:'approved_uploaded_reads_v1'},
 {name:'ppt',create:createPptLearning,scene:'ppt',runtimeKind:'ppt_master_v2',bindingPolicy:'ppt_master_sources_v1'},
]){
 test(`${name} restores exact private source locks using the original or verified descriptor`,t=>{
  const output=realpathSync(mkdtempSync(join(tmpdir(),'private-learning-locks-')));
  t.after(()=>rmSync(output,{recursive:true,force:true}));
  const user='owner',scope='1'.repeat(64),round='round-0001';
  const ppt=name==='ppt',store=join(output,'learning',(ppt?'ppt-':'')+hash(user+'\0'+scope));
  const report=join(store,round),bundle=join(report,'release');
  mkdirSync(bundle,{recursive:true});
  const evidence=join(output,'witness.json');write(evidence,{recorded:true});
  const schemas=[{name:'diagnostic_native_read'}];
  const files=['library.json','online-manifest.json','task.json','tool-schemas.json','source-evidence.json','learning-report.json'];
  for(const file of files)write(join(bundle,file),file==='tool-schemas.json'?schemas:{});
  const fileLocks=Object.fromEntries(files.map(file=>[file,fileHash(join(bundle,file))]));
  const rows=Object.entries(policy[`private_${name}_document_relocations`]);
  assert.ok(rows.length);
  const historical=Object.fromEntries(rows.map(([path,row])=>[path,row.from_sha256]));
  const previousAbsolute=Object.fromEntries(rows.map(([path,row])=>[join(root,path),row.from_sha256]));
  const currentAbsolute=Object.fromEntries(rows.map(([,row])=>{
   const path=join(root,row.path);assert.equal(fileHash(path),row.to_sha256);
   return [path,row.to_sha256];
  }));
  const certificatePath=join(bundle,'certification.json'),admissionPath=join(report,'admission.json');
  function seal(codeLocks,descriptorLocks){
   const certification={schema_version:1,scene,matching_policy:'structural_only',binding_policy:bindingPolicy,
    certification_scope:'independent_trace_structure',file_locks:fileLocks,code_locks:codeLocks};
   write(certificatePath,certification);
   write(join(bundle,'entry.json'),{scene,runtime_kind:runtimeKind,mode:'execute',
    files:{...fileLocks,'certification.json':fileHash(certificatePath)}});
   write(admissionPath,{user,scope,evidence_locks:{'witness.json':fileHash(evidence)},runtime:{
    runtime_kind:runtimeKind,runtime_mode:'execute',runtime_library:join(bundle,'library.json'),
    runtime_library_sha256:fileLocks['library.json'],manifest:join(bundle,'online-manifest.json'),
    task:join(bundle,'task.json'),tool_schemas:join(bundle,'tool-schemas.json'),
    certification_path:certificatePath,certification_sha256:fileHash(certificatePath),
    certified_tool_schemas:schemas,certified_tool_schemas_sha256:fileLocks['tool-schemas.json'],
    certified_code_locks:descriptorLocks,matching_policy:certification.matching_policy,
    binding_policy:bindingPolicy,certification_scope:certification.certification_scope,quality_cost_promoted:false,
   }});
   write(join(store,ppt?'selected.json':'latest.json'),{user,scope,round,phase:'probation',admission_sha256:fileHash(admissionPath)});
  }
  const config={output,user,scope,python:process.execPath,taskIds:()=>[]};
  const manager=create(config),base={id:scene,ppt_execution_strategy:'ppt_master',config_sha256:'base'};
  for(const descriptor of [previousAbsolute,currentAbsolute]){
   seal(historical,descriptor);
   const before=[fileHash(certificatePath),fileHash(admissionPath)];
   const next=manager.resolve(base);
   assert.equal(next.learning_version,round,next===base?read(join(store,'status.json')).reason:undefined);
   assert.deepEqual(next.certified_code_locks,currentAbsolute);
   assert.deepEqual([fileHash(certificatePath),fileHash(admissionPath)],before);
   assert.equal(create({...config,user:'other'}).resolve(base),base);
  }
  const first=rows[0][0];
  seal(historical,{...previousAbsolute,[join(root,first)]:'f'.repeat(64)});
  assert.equal(manager.resolve(base),base);
  seal({...historical,[first]:'f'.repeat(64)},{...previousAbsolute,[join(root,first)]:'f'.repeat(64)});
  assert.equal(manager.resolve(base),base);
 });
}
