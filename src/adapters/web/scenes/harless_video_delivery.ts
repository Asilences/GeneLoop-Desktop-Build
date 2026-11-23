/** Verify the current task's decoded video and editable source. */
import {createHash} from 'node:crypto';
import {lstatSync,readFileSync,realpathSync} from 'node:fs';
import {isAbsolute,join,relative,sep} from 'node:path';

function deliveredFile(workspace:string,path:string,maxBytes:number){
 const stat=lstatSync(path);
 if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1||stat.size>maxBytes)throw Error('video_delivery_file_invalid');
 const rel=relative(workspace,realpathSync(path));
 if(!rel||rel==='..'||rel.startsWith('..'+sep)||isAbsolute(rel))throw Error('video_delivery_file_invalid');
 return stat;
}

export function readVideoDelivery(workspace:string,taskId:string,{
 maxReceiptBytes=Infinity,maxFileBytes=Infinity,
}: {maxReceiptBytes?:number;maxFileBytes?:number}={}){
 if(!/^[a-f0-9]{32}$/.test(taskId))return null;
 try{
  const root=realpathSync(workspace),directory=`outputs/video/${taskId}`,path=join(workspace,directory,'delivery.json');
  deliveredFile(root,path,maxReceiptBytes);
  const receipt=JSON.parse(readFileSync(path,'utf8'));
  if(receipt.schema_version!==1||receipt.kind!=='video-delivery-v1'||receipt.task_id!==taskId||
   receipt.full_video_decode!==true||!Array.isArray(receipt.files)||receipt.files.length!==2)return null;
  const source=directory+'/source.tsx',expected=new Set([source,directory+'/video.mp4']);
  for(const row of receipt.files){
   if(!expected.delete(row.name)||!/^[a-f0-9]{64}$/.test(row.sha256))return null;
   if(row.name===source&&row.sha256!==receipt.source_version)return null;
   const output=join(workspace,row.name),stat=deliveredFile(root,output,maxFileBytes);
   if(stat.size!==row.bytes||createHash('sha256').update(readFileSync(output)).digest('hex')!==row.sha256)return null;
  }
  return receipt;
 }catch{return null;}
}
