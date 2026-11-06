import {execFileSync} from 'node:child_process';
import {cpSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {dirname,join,basename} from 'node:path';
import {stripTypeScriptTypes} from 'node:module';

// Only tracked public implementation/configuration files. Never glob .local,
// source materials, benchmark cases, generated reports, credentials or caches.
export function stageWorkflowSource(repo,destination) {
  const areas=['src/adapters','scenarios/data_analysis','scenarios/paper_proofreading',
    'scenarios/paper-submission','scenarios/ppt_master','scenarios/research_ppt',
    'scenarios/file-management','scenarios/general','benchmarks/research_report_agent_v1','benchmarks/research_report_agent_v2','benchmarks/research_report_agent_v3'];
  const files=execFileSync('git',['ls-files','--',...areas],{cwd:repo,encoding:'utf8',windowsHide:true}).trim().split(/\r?\n/)
    .filter(path=>/\.(?:py|json|ts|md)$/.test(path)&&!/(?:^|\/)(?:tests?|cases|fixtures)(?:\/|\.)/.test(path));
  for(const extra of ['src/adapters/desktop_workflow_server.py'])if(!files.includes(extra))files.push(extra);
  for(const path of files) {
    const target=join(destination,path);mkdirSync(dirname(target),{recursive:true});cpSync(join(repo,path),target);
    if(path.startsWith('scenarios/research_ppt/ts/')&&path.endsWith('.ts')) {
      const js=join(destination,'scenarios/research_ppt/dist',basename(path,'.ts')+'.js');mkdirSync(dirname(js),{recursive:true});
      writeFileSync(js,stripTypeScriptTypes(readFileSync(join(repo,path),'utf8'),{mode:'transform'}));
    }
  }
  return files.length;
}
