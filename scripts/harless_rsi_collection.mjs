import {createHash,randomUUID} from 'node:crypto';
import {mkdirSync,readdirSync,lstatSync,readFileSync,writeFileSync,realpathSync,unlinkSync} from 'node:fs';
import {join} from 'node:path';
import {COLLECTION_PATH,MAX_OBJECT_BYTES,validCollectedObject} from '../apps/desktop/src/rsi-object.ts';
const hash=b=>createHash('sha256').update(b).digest('hex');
const uuid=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const reply=(res,status,data)=>{res.writeHead(status,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify(data));};
/** Authenticated receiver. A durable exclusive record is the receipt, including after a lost response. */
export function createRsiCollectionRoute({dataDir,authorize,now=Date.now}){
 const root=join(dataDir,'rsi-collected');mkdirSync(root,{recursive:true,mode:0o700});
 const read=path=>{const st=lstatSync(path);if(!st.isFile()||st.isSymbolicLink()||st.nlink!==1||st.size>MAX_OBJECT_BYTES+4096||realpathSync(path)!==path)throw Error('invalid_record');return JSON.parse(readFileSync(path,'utf8'));};
 return async(req,res,user)=>{
  const url=new URL(req.url,'https://gateway.invalid');
  if(url.pathname!==COLLECTION_PATH)return false;
  if(!user?.id){reply(res,401,{error:'login_required'});return true;}
  if(url.searchParams.size>1||[...url.searchParams.keys()].some(k=>k!=='object_id')){reply(res,400,{error:'invalid_query'});return true;}
  const account=join(root,hash(user.id));mkdirSync(account,{recursive:true,mode:0o700});
  if(realpathSync(account)!==account)throw Error('invalid_collection_directory');
  const receipt=row=>({object_id:row.object_id,sha256:row.sha256,receipt_id:row.receipt_id,accepted:true});
  if(req.method==='GET'){
   const id=url.searchParams.get('object_id');
   if(!uuid.test(id??'')){reply(res,400,{error:'invalid_object_id'});return true;}
   try{reply(res,200,receipt(read(join(account,id+'.json'))));}catch(e){reply(res,e.code==='ENOENT'?404:503,{error:e.code==='ENOENT'?'not_found':'receipt_unavailable'});}return true;
  }
  if(req.method!=='POST'){reply(res,405,{error:'method_not_allowed'});return true;}
  if(url.search||!authorize(req)||!req.headers['content-type']?.startsWith('application/json')){reply(res,403,{error:'origin_or_content_type_invalid'});return true;}
  const id=req.headers['x-geneloop-object-id'],digest=req.headers['x-geneloop-object-sha256'];
  if(!uuid.test(id??'')||typeof digest!=='string'||! /^[a-f0-9]{64}$/.test(digest)){reply(res,400,{error:'invalid_object_identity'});return true;}
  let size=0,chunks=[];
  for await(const chunk of req){size+=chunk.length;if(size>MAX_OBJECT_BYTES){reply(res,413,{error:'object_too_large'});req.resume();return true;}chunks.push(chunk);}
  const bytes=Buffer.concat(chunks);let object;
  try{object=JSON.parse(bytes.toString('utf8'));}catch{reply(res,400,{error:'invalid_object'});return true;}
  if(hash(bytes)!==digest||!validCollectedObject(object)){reply(res,422,{error:'object_rejected'});return true;}
  const path=join(account,id+'.json');
  try{const previous=read(path);reply(res,previous.sha256===digest?200:409,previous.sha256===digest?receipt(previous):{error:'object_identity_conflict'});return true;}catch(e){if(e.code!=='ENOENT')throw e;}
  // Retention is enforced at admission, without touching account data outside this directory.
  const files=readdirSync(account).filter(n=>uuid.test(n.slice(0,-5))&&n.endsWith('.json'));
  for(const name of files){const path=join(account,name);if(lstatSync(path).mtimeMs+30*86400000<now())unlinkSync(path);}
  if(readdirSync(account).length>=1000){reply(res,429,{error:'collection_capacity'});return true;}
  const row={object_id:id,sha256:digest,receipt_id:randomUUID(),accepted_at:now(),object};
  try{writeFileSync(path,JSON.stringify(row),{flag:'wx',mode:0o600,flush:true});}
  catch(e){if(e.code!=='EEXIST')throw e;const previous=read(path);reply(res,previous.sha256===digest?200:409,previous.sha256===digest?receipt(previous):{error:'object_identity_conflict'});return true;}
  reply(res,201,receipt(row));return true;
 };
}
