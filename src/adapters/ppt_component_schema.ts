/** Preserve page-capacity constraints alongside the existing Harness schema subset. */
import {assertSupportedJsonSchema,validateJsonSchemaValue} from '@deepseek-ai/dsh-tools';

const bounds=new Set(['minItems','maxItems','minLength','maxLength','minimum','maximum']);
/** Inline only local, nonrecursive definitions before using the Harness subset. */
export function normalizeComponentSchema(schema:any):any{
 const definitions=schema?.$defs??{};
 if(!definitions||typeof definitions!=='object'||Array.isArray(definitions))throw Error('component_schema_definitions_invalid');
 let remaining=16000;
 function expand(node:any,stack:string[]=[],depth=0):any{
  if(--remaining<0||depth>64)throw Error('component_schema_expansion_bound');
  if(!node||typeof node!=='object'||Array.isArray(node))throw Error('component_schema_object_required');
  if(Object.hasOwn(node,'$ref')){
   const match=typeof node.$ref==='string'&&/^#\/\$defs\/([^/]+)$/.exec(node.$ref);
   if(!match||/~(?![01])/.test(match[1]))throw Error('component_schema_local_reference_required');
   const name=match[1].replace(/~1/g,'/').replace(/~0/g,'~');
   if(!Object.hasOwn(definitions,name)||stack.includes(name))throw Error('component_schema_reference_missing_or_recursive');
   const annotations=Object.fromEntries(Object.entries(node).filter(([key])=>key!=='$ref'));
   if(Object.keys(annotations).some(key=>!['title','description','$comment','default'].includes(key)))throw Error('component_schema_reference_siblings_unsupported');
   return {...expand(definitions[name],[...stack,name],depth+1),...annotations};
  }
  const result:any={};
  for(const [key,value] of Object.entries(node)){
   if(key==='$defs'){
    if(depth!==0)throw Error('component_schema_nested_definitions_unsupported');
   }else if(key==='properties'){
    if(!value||typeof value!=='object'||Array.isArray(value))throw Error('component_schema_properties_invalid');
    result[key]=Object.fromEntries(Object.entries(value).map(([name,child])=>[name,expand(child,stack,depth+1)]));
   }else if(key==='items')result[key]=expand(value,stack,depth+1);
   else if(key==='oneOf'){
    if(!Array.isArray(value))throw Error('component_schema_oneOf_invalid');
    result[key]=value.map(child=>expand(child,stack,depth+1));
   }else result[key]=value;
  }
  return result;
 }
 return expand(schema);
}
function projected(schema:any):any{
 if(!schema||typeof schema!=='object'||Array.isArray(schema))throw Error('component_schema_object_required');
 const result:any={};
 for(const [key,value] of Object.entries(schema)){
  if(bounds.has(key)){
   if(typeof value!=='number'||!Number.isFinite(value)||(/(?:Items|Length)$/.test(key)&&(!Number.isSafeInteger(value)||value<0)))throw Error('component_schema_bound_invalid');
  }else if(key==='properties')result[key]=Object.fromEntries(Object.entries(value as any).map(([name,child])=>[name,projected(child)]));
  else if(key==='items')result[key]=projected(value);
  else if(key==='oneOf')result[key]=(value as any[]).map(projected);
  else result[key]=value;
 }
 return result;
}
export function assertComponentSchema(schema:any){assertSupportedJsonSchema(projected(normalizeComponentSchema(schema)));}
/** Structural constants can be bound without copying historical scientific text. */
export function bindComponentConstants(schema:any,value:any){
 if(!value||typeof value!=='object'||Array.isArray(value))return value;
 schema=normalizeComponentSchema(schema);
 const result={...value};
 for(const [name,child] of Object.entries(schema.properties??{}) as [string,any][]){
  if(!Object.hasOwn(result,name)&&Object.hasOwn(child,'const'))result[name]=child.const;
 }
 return result;
}
export function validateComponentParameters(schema:any,value:any):string[]{
 return validateNormalizedParameters(normalizeComponentSchema(schema),value);
}
function validateNormalizedParameters(schema:any,value:any):string[]{
 const shallow=projected(schema);delete shallow.oneOf;
 if(shallow.properties)shallow.properties=Object.fromEntries(Object.keys(shallow.properties).map(name=>[name,{}]));
 if(shallow.items)shallow.items={};
 const errors=validateJsonSchemaValue(shallow,value).map(String);
 if(errors.length)return errors;
 if(schema.oneOf&&schema.oneOf.filter((branch:any)=>validateNormalizedParameters(branch,value).length===0).length!==1)errors.push('component_oneOf_failed');
 if(typeof value==='number'){
  if(!Number.isFinite(value)||schema.minimum!==undefined&&value<schema.minimum||schema.maximum!==undefined&&value>schema.maximum)errors.push('component_number_bound_failed');
 }
 if(typeof value==='string'){
  const length=[...value].length;
  if(schema.minLength!==undefined&&length<schema.minLength||schema.maxLength!==undefined&&length>schema.maxLength)errors.push('component_text_capacity_failed');
 }
 if(Array.isArray(value)){
  if(schema.minItems!==undefined&&value.length<schema.minItems||schema.maxItems!==undefined&&value.length>schema.maxItems)errors.push('component_item_capacity_failed');
  if(schema.items)for(const [index,item] of value.entries())errors.push(...validateNormalizedParameters(schema.items,item).map(error=>'['+index+'].'+error));
 }else if(value&&typeof value==='object'){
  for(const [name,child] of Object.entries(schema.properties??{}))if(Object.hasOwn(value,name))errors.push(...validateNormalizedParameters(child,value[name]).map(error=>name+'.'+error));
 }
 return errors;
}
