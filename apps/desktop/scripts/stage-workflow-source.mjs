import {execFileSync} from 'node:child_process';
import {cpSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {dirname,join,basename} from 'node:path';
import {stripTypeScriptTypes} from 'node:module';

// Only tracked public implementation/configuration files. Never glob .local,
// source materials, benchmark cases, generated reports, credentials or caches.
export function stageWorkflowSource(repo,destination) {
  const areas=['src/adapters','src/motif_core','src/semantic_inputs.py','scenarios/data_analysis','scenarios/paper_proofreading',
    'scenarios/paper-submission','scenarios/ppt_master','scenarios/research_ppt',
    'scenarios/file-management','scenarios/general','benchmarks/research_report_agent_v1','benchmarks/research_report_agent_v2','benchmarks/research_report_agent_v3'];
  const files=execFileSync('git',['ls-files','--',...areas],{cwd:repo,encoding:'utf8',windowsHide:true}).trim().split(/\r?\n/)
    .filter(path=>/\.(?:py|json|ts|md)$/.test(path)&&!/(?:^|\/)(?:tests?|cases|fixtures)(?:\/|\.)/.test(path));
  for(const extra of ['src/motif_core/LICENSE','src/motif_core/PROVENANCE.md','src/adapters/desktop_workflow_server.py','src/adapters/desktop_general.py','src/adapters/desktop_ppt_pipeline.py','src/adapters/desktop_skill_runtime.py','src/adapters/desktop_python_entry.py','src/adapters/desktop_native_providers.py'])if(!files.includes(extra))files.push(extra);
  for(const path of files) {
    const target=join(destination,path);mkdirSync(dirname(target),{recursive:true});cpSync(join(repo,path),target);
    if(path.startsWith('scenarios/research_ppt/ts/')&&path.endsWith('.ts')) {
      const js=join(destination,'scenarios/research_ppt/dist',basename(path,'.ts')+'.js');mkdirSync(dirname(js),{recursive:true});
      writeFileSync(js,stripTypeScriptTypes(readFileSync(join(repo,path),'utf8'),{mode:'transform'}));
    }
  }
  const paperRoot=join(repo,'motif-libraries/paper');
  const entry=JSON.parse(readFileSync(join(paperRoot,'entry.json'),'utf8'));
  const target=join(destination,'motif-libraries/paper');mkdirSync(target,{recursive:true});
  for(const name of ['entry.json',...Object.keys(entry.files)]){
    if(name!==basename(name))throw Error('论文修订发布文件名无效');
    cpSync(join(paperRoot,name),join(target,name));
  }
  for(const name of ['config/geneloop-capabilities.json','config/general-tools.json','config/harless-scenes.json']){
    const target=join(destination,name);mkdirSync(dirname(target),{recursive:true});cpSync(join(repo,name),target);
  }
  cpSync(join(repo,'src/adapters/desktop_sitecustomize.py'),join(destination,'sitecustomize.py'));
  return files.length;
}
