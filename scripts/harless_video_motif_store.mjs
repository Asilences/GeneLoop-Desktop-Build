/** Mount only the immutable public-runtime part of a published video form. */
import {readFileSync,readdirSync,lstatSync,realpathSync} from 'node:fs';
import {resolve,isAbsolute,join} from 'node:path';
export function fixedVideoMotifStore(value){
  if(typeof value!=='string'||!isAbsolute(value)||resolve(value)==='/'||realpathSync(value)!==resolve(value)||lstatSync(value).isSymbolicLink()||!lstatSync(value).isDirectory())throw Error('Video Motif store must be a fixed installation');
  const root=realpathSync(value);
  const read=(path)=>{const stat=lstatSync(path);if(stat.isSymbolicLink()||!stat.isFile()||stat.nlink!==1||stat.size>4000000)throw Error('Video Motif store contains an invalid runtime file');return JSON.parse(readFileSync(path,'utf8'));};
  const pointer=read(join(root,'latest.json'));
  const pattern=/^round-[a-f0-9]{24}\/(?:policy|source-library)\.json$/;
  if(!pattern.test(pointer.policy)||!pattern.test(pointer.library)||pointer.policy.split('/')[0]!==pointer.library.split('/')[0])throw Error('Video Motif pointer must select one published round');
  const round=pointer.policy.split('/')[0];
  if(readdirSync(root).sort().join('|')!==['latest.json',round].sort().join('|'))throw Error('Video Motif store contains non-runtime private evidence');
  const directory=join(root,round),stat=lstatSync(directory);
  if(stat.isSymbolicLink()||!stat.isDirectory()||realpathSync(directory)!==directory)throw Error('Video Motif round is redirected');
  const allowed=['policy.json','source-library.json','rsi-update.json','rsi-publication.json'];
  if(readdirSync(directory).sort().join('|')!==allowed.sort().join('|'))throw Error('Video Motif store must contain the complete published runtime receipt');
  for(const name of allowed)read(join(directory,name));
  return root;
}
