/** Chunked browser transfer; final receipts are minted by the native owning Session. */
import {mkdirSync,mkdtempSync,writeFileSync,appendFileSync,rmSync,createReadStream} from 'node:fs';
import {join,basename} from 'node:path';
import {randomUUID,createHash} from 'node:crypto';
import {FILE_MAX_BYTES} from './geneloop_upload_limits.ts';
const CHUNK_BYTES=8*1024*1024, TTL=60*60*1000;
class UploadError extends Error {status:number;constructor(status:number,message:string){super(message);this.status=status;}}
async function bounded(request:Request,maximum:number){
 const reader=request.body?.getReader();if(!reader)return Buffer.alloc(0);
 const chunks:Buffer[]=[];let size=0;
 try{for(;;){const r=await reader.read();if(r.done)break;size+=r.value.length;
  if(size>maximum){await reader.cancel();throw new UploadError(413,'上传分块过大。');}chunks.push(Buffer.from(r.value));}}
 finally{reader.releaseLock();}
 return Buffer.concat(chunks);
}
export function createChunkedUpload(ctx:any,root:string,owns:(id:string)=>Promise<void>){
 mkdirSync(root,{recursive:true,mode:0o700});
 const directory=mkdtempSync(join(root,'instance-'));
 const uploads=new Map<string,any>();
 const remove=(id:string)=>{const row=uploads.get(id);if(row){rmSync(row.path,{force:true});uploads.delete(id);}};
 const timer=setInterval(()=>{for(const [id,row]of uploads)if(!row.busy&&Date.now()-row.touched>TTL)remove(id);},60000);timer.unref();
 return {
  async fetch(request:Request){
   const denied=ctx.connection.requestRejection(request);if(denied)return new Response('',{status:denied});
   let row:any;
   try{
    const url=new URL(request.url),action=url.searchParams.get('action'),session=url.searchParams.get('session')??'';
    await owns(session);
    if(action==='begin'){
     const body=JSON.parse((await bounded(request,4096)).toString('utf8'));
     if(typeof body.name!=='string'||!body.name||body.name.length>255||basename(body.name)!==body.name||/[\\/\x00-\x1f]/.test(body.name))throw new UploadError(400,'文件名无效。');
     if(!Number.isSafeInteger(body.bytes)||body.bytes<0||body.bytes>FILE_MAX_BYTES)throw new UploadError(413,'单文件不能超过 200 MiB。');
     const id=randomUUID(),path=join(directory,id);writeFileSync(path,'',{mode:0o600,flag:'wx'});
     uploads.set(id,{session,name:body.name,total:body.bytes,offset:0,path,touched:Date.now(),busy:false});
     return Response.json({id,chunk_bytes:CHUNK_BYTES,max_file_bytes:FILE_MAX_BYTES},{headers:{'Cache-Control':'no-store'}});
    }
    const id=url.searchParams.get('id')??'';row=uploads.get(id);
    if(!row||row.session!==session)throw new UploadError(404,'上传已失效，请重新选择文件。');
    if(row.busy)throw new UploadError(409,'该上传分块正在处理。');
    row.busy=true;row.touched=Date.now();
    if(action==='abort'){remove(id);return Response.json({cancelled:true});}
    if(action==='chunk'){
     if(row.result)throw new UploadError(409,'文件上传已经完成。');
     const offset=Number(url.searchParams.get('offset')),bytes=await bounded(request,CHUNK_BYTES);
     if(!Number.isSafeInteger(offset)||offset<0||!bytes.length)throw new UploadError(400,'分块参数无效。');
     const hash=createHash('sha256').update(bytes).digest('hex');
     // A lost response may replay only the immediately preceding exact chunk.
     if(offset===row.last?.offset&&hash===row.last.hash&&bytes.length===row.last.bytes)return Response.json({offset:row.offset});
     if(offset!==row.offset||offset+bytes.length>row.total)throw new UploadError(409,'上传位置或文件大小发生变化。');
     appendFileSync(row.path,bytes);row.last={offset,hash,bytes:bytes.length};row.offset+=bytes.length;
     return Response.json({offset:row.offset});
    }
    if(action==='complete'){
     if(row.result)return Response.json(row.result);
     if(row.offset!==row.total)throw new UploadError(409,'文件尚未上传完整。');
     const value=await ctx.fileUploads.uploadStream({sessionId:session,name:row.name,data:createReadStream(row.path),signal:request.signal});
     row.result={ok:true,value};rmSync(row.path,{force:true});return Response.json(row.result);
    }
    throw new UploadError(400,'上传操作无效。');
   }catch(error:any){return Response.json({error:{message:error instanceof UploadError?error.message:'上传失败，请重试。'}},{status:error instanceof UploadError?error.status:400});}
   finally{if(row)row.busy=false;}
  },
  dispose(){clearInterval(timer);rmSync(directory,{recursive:true,force:true});uploads.clear();}
 };
}
export function installChunkedUpload(ctx:any,output:string,owns:(id:string)=>Promise<void>){
 const service=createChunkedUpload(ctx,join(output,'upload-staging'),owns);
 ctx.effect(()=>ctx.connection.fetch.register({path:'/api/harless/uploads',methods:['POST'],requestBody:'streaming',fetch:service.fetch}));
 ctx.effect(()=>()=>service.dispose());
}
