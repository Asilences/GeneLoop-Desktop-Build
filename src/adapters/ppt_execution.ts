/** Host-neutral execution. Tool bodies retain their original authorization. */
import {digest} from '../motif_core/online_skill_runtime.mjs';
import {bindComponentConstants,validateComponentParameters} from './ppt_component_schema.ts';

export type PptDispatchHost = {
  dispatch:(call:any)=>Promise<any>;
  check:()=>void;
  audit:(row:any)=>void;
};

export type PptOperation = {
  id:string;
  tool:string;
  arguments:Record<string,any>;
};

/** Sequential dispatch preserves partial progress and never retries side effects. */
export async function executePptOperations(operations:PptOperation[],execution:any,host:PptDispatchHost){
  if(!Array.isArray(operations)||!operations.length||operations.length>64)throw Error('ppt_operations_invalid');
  const ids=new Set<string>();
  for(const operation of operations){
    if(!operation||!(/^[a-zA-Z0-9_-]{1,80}$/).test(operation.id)||ids.has(operation.id)||
       typeof operation.tool!=='string'||!operation.tool||!operation.arguments||
       typeof operation.arguments!=='object'||Array.isArray(operation.arguments))throw Error('ppt_operation_invalid');
    ids.add(operation.id);
  }
  const completed:any[]=[];
  for(const operation of operations){
    execution.signal?.throwIfAborted();
    host.check();
    const callId=execution.callId+':ppt:'+operation.id;
    const call={name:operation.tool,arguments:structuredClone(operation.arguments),callId,
      rootCallId:execution.rootCallId??execution.callId,parent:execution.token,agent:execution.agent,signal:execution.signal};
    host.audit({kind:'ppt_operation_started',parent_call_id:execution.callId,call_id:callId,tool:operation.tool,
      arguments_sha256:digest(call.arguments)});
    const result=await host.dispatch(call);
    execution.signal?.throwIfAborted();
    host.check();
    completed.push({id:operation.id,call_id:callId,tool:operation.tool,result});
    host.audit({kind:'ppt_operation_finished',call_id:callId,tool:operation.tool,is_error:result.isError===true});
    if(result.isError)return {status:'failed',completed,failed_operation:operation.id};
  }
  return {status:'completed',completed};
}

/** Parameter admission precedes sandbox execution and page installation. */
export function admitPptComponent(program:any,parameters:any){
  if(!program?.component||program.certification?.passed!==true||program.certification?.component_source_equivalence?.passed!==true)
    throw Error('component_independent_certification_required');
  const bound=bindComponentConstants(program.component.parameters_schema,parameters);
  const errors=validateComponentParameters(program.component.parameters_schema,bound);
  if(errors.length)throw Error('component_parameters_invalid: '+JSON.stringify(errors));
  return {parameters:structuredClone(bound),input_sha256:digest({program:program.id,source:program.source_sha256,parameters:bound})};
}
