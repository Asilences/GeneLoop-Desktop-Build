import {createHash} from 'node:crypto';
import {existsSync,readFileSync} from 'node:fs';
import {isAbsolute,join} from 'node:path';

export function privateSourceLocks(
 root:string,recorded:Record<string,unknown>,scene:'paper'|'ppt',
 checked:(parent:string,path:string)=>string,error:string,
){
 const path=join(root,'config/rsi-privacy-code-compat.json');
 const entries=existsSync(path)?JSON.parse(readFileSync(path,'utf8'))[`private_${scene}_document_relocations`]??{}:{};
 const original:Record<string,string>={},current:Record<string,string>={};
 for(const [name,version] of Object.entries(recorded)){
  if(!name||isAbsolute(name)||name.split(/[\\/]/).includes('..')||typeof version!=='string'||!/^[a-f0-9]{64}$/.test(version))
   throw Error(error);
  const row=Object.hasOwn(entries,name)?entries[name]:undefined;
  const relocated=row?.from_sha256===version || row?.additional_source_sha256?.includes(version);
  const source=relocated?row.path:name;
  if(typeof source!=='string'||!source||isAbsolute(source)||source.split(/[\\/]/).includes('..'))throw Error(error);
  const file=checked(root,join(root,source));
  const actual=createHash('sha256').update(readFileSync(file)).digest('hex');
  if(actual!==(relocated?row.to_sha256:version))throw Error(error);
  original[join(root,name)]=version;
  current[file]=actual;
 }
 return {original,current};
}
