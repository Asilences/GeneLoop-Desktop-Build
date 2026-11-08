/** Shared host profile. Desktop hosts supply their own registered tool contracts. */
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {digest} from '../motif_core/online_skill_runtime.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
export function pptWorkflowEnvironment(){
  const config=JSON.parse(readFileSync(join(root,'scenarios/ppt_master/workflow-contracts.json'),'utf8'));
  return digest({platform:process.platform,code_locks:Object.fromEntries(config.implementation_files.map((name:string)=>{
    if(typeof name!=='string'||name.startsWith('/')||name.split('/').includes('..')||!resolve(root,name).startsWith(resolve(root)))
      throw Error('ppt_workflow_implementation_path_invalid');
    return [name,createHash('sha256').update(readFileSync(join(root,name))).digest('hex')];
  }))});
}

export function pptWorkflowHost(execution:any){
  const config=JSON.parse(readFileSync(join(root,'scenarios/ppt_master/workflow-contracts.json'),'utf8'));
  const agent=execution.agent;
  return {environment_sha256:pptWorkflowEnvironment(),contracts:Object.fromEntries(Object.entries(config.tools).map(([name,contract]:[string,any])=>{
    const definition=agent.ctx.tools.get(name,agent);
    if(!definition?.parameters)throw Error('ppt_workflow_host_tool_missing');
    return [name,{...contract,schema_sha256:digest(definition.parameters)}];
  }))};
}
