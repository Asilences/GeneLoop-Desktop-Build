/** Typed-job admission diagnostics, no model or production service invocation. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {tmpdir} from 'node:os';
import {preparePptProgramJob} from '../src/adapters/ppt_program_broker.ts';

test('program broker rejects arbitrary source requests and foreign job files',()=>{
 const output=mkdtempSync(join(tmpdir(),'ppt-broker-')),foreign=mkdtempSync(join(tmpdir(),'other-account-'));
 const file=join(foreign,'job.json');writeFileSync(file,'{}');
 assert.throws(()=>preparePptProgramJob({output},{operation:'run',session:'session-'+ '1'.repeat(36),file,source:'arbitrary'}),/owner/);
 assert.throws(()=>preparePptProgramJob({output},{operation:'certify',file}),/owning account/);
 assert.throws(()=>preparePptProgramJob({output},{operation:'eval',file}),/unsupported/);
});

test('certification cannot use Execute tasks without owning single-task completion evidence',()=>{
 const output=mkdtempSync(join(tmpdir(),'ppt-broker-cert-'));
 const folder=join(output,'learning','ppt-'+'a'.repeat(64),'program-'+'b'.repeat(24));mkdirSync(folder,{recursive:true});
 const rows=[1,2].map(i=>({task_id:String(i).repeat(32),scene:'ppt',workspace:output,candidates:[]}));
 for(const row of rows){
  const dir=join(output,'tasks',row.task_id);mkdirSync(dir,{recursive:true});
  writeFileSync(join(dir,'task-state.json'),JSON.stringify({status:'completed',mode:'execute',scene:'ppt'}));
  writeFileSync(join(dir,'effective-config.json'),JSON.stringify({provider_mode:'real'}));
 }
 const file=join(folder,'candidates.json');writeFileSync(file,JSON.stringify(rows));
 assert.throws(()=>preparePptProgramJob({output},{operation:'certify',file}),/ordinary program witness/);
});


test('native workflow certification uses only the owning learner and a fixed executable',()=>{
 const output=mkdtempSync(join(tmpdir(),'ppt-native-cert-')),user='private-owner',scope='a'.repeat(64);
 const store=join(output,'learning','ppt-'+createHash('sha256').update(user+'\0'+scope).digest('hex'));
 const folder=join(store,'workflows/certification','b'.repeat(64));mkdirSync(folder,{recursive:true});
 writeFileSync(join(store,'request.json'),JSON.stringify({user,scope}));
 const file=join(folder,'plan.json');writeFileSync(file,JSON.stringify({kind:'ppt_native_workflow_certification',user,scope}));
 const options={output,python:'approved-python',node:'approved-node',resources:{projectRoot:'approved'}};
 const job=preparePptProgramJob(options,{operation:'workflow-certify',file});
 assert.equal(job.argv[0],'approved-node');assert.ok(job.argv[2].endsWith('certify-ppt-workflow.mjs'));
 assert.equal(job.env.SSS_PYTHON,'approved-python');assert.equal(job.env.KOURI_API_KEY,undefined);
 assert.throws(()=>preparePptProgramJob(options,{operation:'workflow-certify',file,source:'user-supplied'}),/invalid workflow/);
 writeFileSync(file,JSON.stringify({kind:'ppt_native_workflow_certification',user:'foreign',scope}));
 assert.throws(()=>preparePptProgramJob(options,{operation:'workflow-certify',file}),/owner changed/);
});
