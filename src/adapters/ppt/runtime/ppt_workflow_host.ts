/** Shared host profile. Desktop hosts supply their own registered tool contracts. */
import {existsSync,readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {digest} from '../../../motif_core/runtime/online_skill_runtime.mjs';

const root=fileURLToPath(new URL('../../../../',import.meta.url));
export function pptWorkflowEnvironment(){
  const config=JSON.parse(readFileSync(join(root,'scenarios/ppt_master/workflow-contracts.json'),'utf8'));
  const current = digest({platform:process.platform,code_locks:Object.fromEntries(config.implementation_files.map((name:string)=>{
    if(typeof name!=='string'||name.startsWith('/')||name.split('/').includes('..')||!resolve(root,name).startsWith(resolve(root)))
      throw Error('ppt_workflow_implementation_path_invalid');
    return [name,createHash('sha256').update(readFileSync(join(root,name))).digest('hex')];
  }))});
  const policy = join(root, 'config/rsi-privacy-code-compat.json');
  const reviewed = existsSync(policy) ? JSON.parse(readFileSync(policy, 'utf8')).ppt_workflow_environment : undefined;
  return reviewed?.[current] ?? current;
}

export function pptWorkflowHost(execution:any){
  const config=JSON.parse(readFileSync(join(root,'scenarios/ppt_master/workflow-contracts.json'),'utf8'));
  const agent=execution.agent;
  return {environment_sha256:pptWorkflowEnvironment(),contracts:Object.fromEntries(Object.entries(config.tools).flatMap(([name,contract]:[string,any])=>{
    const definition=agent.ctx.tools.get(name,agent);
    // Availability is checked against the selected program's actual references
    // by validatePptWorkflowLibrary. An unrelated dormant page factory must not
    // disable a build/read continuation (desktop hosts load tools on demand).
    if(!definition?.parameters)return [];
    return [[name,{...contract,schema_sha256:digest(definition.parameters)}]];
  }))};
}
