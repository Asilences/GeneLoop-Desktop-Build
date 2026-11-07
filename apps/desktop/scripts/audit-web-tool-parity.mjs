// Inventory the actual public scene registry. Never infer parity from counts.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {workflowTools,workflowToolName} from '../runtime/native-workflow-catalog.mjs';
import {commonToolNames} from '../runtime/common-tool-catalog.mjs';
const repo=fileURLToPath(new URL('../../../',import.meta.url));
const json=path=>JSON.parse(execFileSync('git',['show','origin/main:'+path],{cwd:repo,encoding:'utf8',windowsHide:true}));
const aliases={ppt_master:'skill',paper_checks:'paper',paper_trace_rsi:'revision',research_report:'report',file_management:'files',workspace:'workspace',video_edit:'video',remotion:'video'};
const rows=[];
for(const scene of json('config/harless-scenes.json').scenes){
  for(const name of json(scene.scenario).allowed_tools){
    const match=/^mcp__(.+?)__(.+)$/.exec(name);assert.ok(match,'未识别网页工具名：'+name);
    const kind=aliases[match[1]]??(scene.adapter==='video'?'video':null),tool=match[2];
    assert.ok(workflowTools[kind]?.includes(tool),'缺少实际网页工具映射：'+name);
    rows.push({scene:scene.id,web:name,native:workflowToolName(kind,tool),implementation:kind==='video'?'apps/desktop/runtime/local-video-workflow.mjs':'original MCP via apps/desktop/runtime/local-workflows.mjs',activation:'default',source:scene.scenario});
  }
}
for(const name of json('config/geneloop-capabilities.json').tools){
  assert.ok(commonToolNames.includes(name));
  rows.push({scene:'all',web:name,native:name==='bash'?'Windows: pwsh / macOS: bash':name,implementation:'official @deepseek-ai/dsh-* via local-common.mjs',activation:'default; toolsetVersion=4',source:'config/geneloop-capabilities.json'});
}
for(const name of ['prepare_ppt','finalize_ppt'])rows.push({scene:'ppt',web:name,native:name,implementation:'desktop_ppt_pipeline.py + locked PPT Master + actual Office',activation:'ppt_master host pipeline',source:'src/adapters/ppt_delivery_pipeline.ts'});
for(const tool of workflowTools.management)rows.push({scene:'files',web:'mcp__file_management__'+tool,native:workflowToolName('management',tool),implementation:'unchanged ManagementScene over private task copies',activation:'conditional: management_graph_v3',source:'scenarios/file-management/management_tools.py'});
for(const tool of workflowTools.general)rows.push({scene:'general-provider',web:tool,native:workflowToolName('general',tool),implementation:'original general runtime; code uses native QuickJS WASM instead of Docker',activation:'dynamic workspace-runtime provider',source:'scenarios/general/runtime.py'});
for(const tool of workflowTools.gateway)rows.push({scene:'general-provider',web:tool,native:workflowToolName('gateway',tool),implementation:'original general_tools.Gateway with host-owned native provider registry',activation:'dynamic discovery',source:'src/adapters/general_tools.py'});
const record={schema_version:1,main:execFileSync('git',['rev-parse','origin/main'],{cwd:repo,encoding:'utf8'}).trim(),scope:'Tool mapping and implementation inventory, not a claim of full real-model or macOS acceptance',
  boundaries:['Native PowerShell replaces Bash on Windows; commands are not silently rewritten.','Native tools operate on explicit copies and publish outputs; user-original mutations require a separate preview/confirmation.','Model image capability is required for visual acceptance.','Account Motif programs and their Linux certification are not re-certified by this inventory.','Private production registries may add tools and must be compared separately; no production deployment is claimed.'],
  external_integrations:[{web:'create_ppt_page / account-local learned programs',owner:'Motif integration',status:'requires the account library and target-platform certification; not replaced with a fabricated native program'}],rows};
const target=resolve(repo,'docs/desktop-tool-parity.json'),render=JSON.stringify(record,null,2)+'\n';
if(process.argv.includes('--check'))assert.equal(readFileSync(target,'utf8'),render,'网页工具目录变化，请更新逐项对照');
else writeFileSync(target,render);
console.log(JSON.stringify({default_scene_tools:rows.filter(r=>r.activation==='default').length,common:20,host_ppt:2,conditional_management:27,dynamic_provider_tools:9,total_rows:rows.length,unmapped:0,quality_acceptance:false}));
