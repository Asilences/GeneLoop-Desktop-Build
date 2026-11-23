// Shared desktop/gateway boundary: no content, paths, tool names or source IDs.
export const COLLECTION_PATH = '/api/harless/rsi-collected-objects';
export const MAX_OBJECT_BYTES = 256 * 1024;
const exact=(v:any,keys:string[])=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join(',')===keys.sort().join(',');
export function validCollectedObject(value:any){
  if(!exact(value,['format','kind','trace'])||value.format!=='geneloop.rsi-collected-object/v1'||value.kind!=='tool_flow')return false;
  const t=value.trace;
  if(!exact(t,['format','scene','status','nodes','bindings'])||t.format!=='geneloop.rsi-learning-trace/v4'||t.scene!=='generic'||
    !['completed','failed','cancelled','interrupted','budget_exhausted'].includes(t.status)||!Array.isArray(t.bindings)||t.bindings.length||
    !Array.isArray(t.nodes)||!t.nodes.length||t.nodes.length>20000)return false;
  const aliases=new Set();
  for(const n of t.nodes){
    if(!exact(n,['tool','outcome']))return false;
    if(n.tool===null){if(n.outcome!=='unapproved_tool')return false;}
    else{
      if(typeof n.tool!=='string'||!/^tool-(0|[1-9][0-9]{0,4})$/.test(n.tool)||!['observed_success','missing_or_failed_result'].includes(n.outcome))return false;
      if(!aliases.has(n.tool)){if(n.tool!=='tool-'+aliases.size)return false;aliases.add(n.tool);}
    }
  }
  return Buffer.byteLength(JSON.stringify(value))<=MAX_OBJECT_BYTES;
}
