/** Administrator-selected immutable skill bytes, shared by MCP and Bash. */
import {readFileSync,readdirSync,lstatSync,realpathSync} from 'node:fs';
import {resolve,join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const fileDigests=files=>JSON.stringify(Object.fromEntries(Object.entries(files).sort(([a],[b])=>a<b?-1:a>b?1:0)))
  .replace(/[\u007f-\uffff]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0'));
const project=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const target='/opt/geneloop/ppt-master';
export function pptResourceProvenance(projectRoot=project){
  const metadata=JSON.parse(readFileSync(join(projectRoot,'scenarios/ppt_master/third_party/ppt-master-desktop/PROVENANCE.json'),'utf8'));
  if(metadata.schema_version!==1||typeof metadata.bundle_sha256!=='string'||!/^[a-f0-9]{64}$/.test(metadata.bundle_sha256))
    throw Error('invalid presentation resource provenance');
  return metadata;
}
export function bundledPptRoot(projectRoot=project){
  return join(projectRoot,'.local/ppt-resources',pptResourceProvenance(projectRoot).bundle_sha256);
}
const cached=new Map();
export function pptMasterInstallation(root, projectRoot=project){
  if(!root)return null;
  const provenance=pptResourceProvenance(projectRoot),key=root+':'+provenance.bundle_sha256;
  if(cached.has(key))return cached.get(key);
  if(resolve(root)!==root || realpathSync(root)!==root || lstatSync(root).isSymbolicLink())throw Error('invalid ppt-master installation');
  const files=Object.create(null);
  const walk=(directory,prefix='')=>{
    for(const entry of readdirSync(directory,{withFileTypes:true})){
      const name=prefix+entry.name,path=join(directory,entry.name);
      if(entry.isSymbolicLink())throw Error('ppt-master installation link rejected');
      if(entry.isDirectory())walk(path,name+'/');
      else if(entry.isFile())files[name]=sha(readFileSync(path));
      else throw Error('invalid presentation resource: '+name);
    }
  };walk(root);
  const serialized=fileDigests(files);
  if(provenance.schema_version!==1||Object.keys(files).length!==provenance.file_count||sha(serialized)!==provenance.bundle_sha256)
    throw Error('bundled presentation resources changed');
  const value={source:root,target,sha256:provenance.bundle_sha256,entrySha256:files['SKILL.md'],
    scriptsSha256:sha(fileDigests(Object.fromEntries(Object.entries(files).filter(([name])=>name.startsWith('scripts/')))))};
  cached.set(key,value);return value;
}
