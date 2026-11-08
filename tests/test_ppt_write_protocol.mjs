import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {validatePptWorkflowLibrary} from '../src/adapters/ppt_workflow_runtime.ts';
import {pptWriteArguments} from '../src/adapters/ppt_write_runtime.ts';

test('Python trace compiler output is accepted unchanged by the TypeScript write interpreter',()=>{
 const code=`import json,runpy
ns=runpy.run_path('tests/test_ppt_write_learning.py')
from src.adapters.ppt_workflow_learning import discover_workflows
print(json.dumps(discover_workflows([ns['sample']('a'),ns['sample']('b')],[ns['sample']('c')],ns['CONTRACTS'],'shared-env')))`;
 const library=JSON.parse(execFileSync(process.env.SSS_PYTHON??'python',['-c',code],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));
 const role={resource_argument:'project',identity_argument:'page',revision_argument:'expected_page_sha256',version_output:['sha256']};
 const completion={success:['mechanical_status'],success_value:'passed',empty_findings:['findings'],collection:['review_pages']};
 const host={environment_sha256:'shared-env',contracts:{page:{read_only:false,schema_sha256:digest({type:'object'}),page_write:role},
   deliver:{read_only:false,schema_sha256:digest({type:'object'}),resource_argument:'project',observed_completion:completion}}};
 assert.equal(validatePptWorkflowLibrary(library,host),library);
 const program=library.programs[0];
 const built=pptWriteArguments(program,{project:'current-project',pages:[{page:'one.svg',content:{title:'Independent current content'}}]});
 assert.equal(built.writes[0].arguments.content.title,'Independent current content');
 assert.equal(built.delivery.tool,'deliver');
 assert.ok(!JSON.stringify(program.ir).includes('private scientific text'));
});
