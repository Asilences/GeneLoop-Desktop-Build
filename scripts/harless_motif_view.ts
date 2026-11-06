/** 现有认证导出的只读投影；不创建 Store、能力或执行权限。 */
import {open,lstat,realpath} from 'node:fs/promises';
import {constants,readFileSync} from 'node:fs';
import {isAbsolute,resolve} from 'node:path';
import {createHash} from 'node:crypto';
import Ajv2020 from 'ajv/dist/2020.js';
import {evidenceView} from '../src/adapters/motif_evidence_projection.ts';
const schema=JSON.parse(readFileSync(new URL('../config/motif-evidence-v1.schema.json',import.meta.url),'utf8'));
const check=new Ajv2020({allowUnionTypes:true}).compile(schema);
export const motifEvidenceView=(input:unknown)=>evidenceView(input,check);
type Source={accountId:string;workspaceId:string;path:string;executionLocation:'cloud'|'local'};
const validId=(value:unknown):value is string=>typeof value==='string'&&value.length>0&&value.length<=160&&!/[\x00-\x20\x7f/\\]/.test(value);
export function createMotifViewRoute(config:{sources?:Source[]}={}) {
  const sources=config.sources??[];
  if(!Array.isArray(sources)||sources.some(s=>!s||!validId(s.accountId)||!validId(s.workspaceId)||!isAbsolute(s.path)||!['local','cloud'].includes(s.executionLocation))||
    new Set(sources.map(s=>s.accountId+'\0'+s.workspaceId)).size!==sources.length)throw Error('Invalid Motif display sources');
  async function snapshot(source:Source) {
    // 只读取宿主预先配置的文件；客户端没有路径或导出注册入口。
    let file;
    try{
      const info=await lstat(source.path);
      if(!info.isFile()||info.nlink!==1||info.size>4*1024*1024||resolve(await realpath(source.path))!==resolve(source.path))throw Error('Invalid snapshot file');
      file=await open(source.path,constants.O_RDONLY|(constants.O_NOFOLLOW??0));
      const opened=await file.stat();
      if(!opened.isFile()||opened.ino!==info.ino||opened.dev!==info.dev||opened.size>4*1024*1024||opened.nlink!==1)throw Error('Snapshot changed');
      const bytes=Buffer.alloc(4*1024*1024+1),{bytesRead}=await file.read(bytes,0,bytes.length,0);
      if(bytesRead>4*1024*1024)throw Error('Snapshot too large');
      const evidence=JSON.parse(bytes.subarray(0,bytesRead).toString('utf8'));
      evidenceView(evidence,check);
      return {workspaceId:source.workspaceId,status:'ready',executionLocation:source.executionLocation,compatibility:'unverified',evidence};
    }catch{return {workspaceId:source.workspaceId,status:'unavailable',executionLocation:source.executionLocation,compatibility:'unverified',evidence:null};}
    finally{await file?.close();}
  }
  return async(req:any,res:any,user:{id:string}|null)=>{
    const url=new URL(req.url,'http://127.0.0.1');
    if(url.pathname!=='/api/harless/motif-library')return false;
    const send=(status:number,body:unknown)=>{res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff','vary':'Cookie'});res.end(JSON.stringify(body));};
    if(!user){send(401,{error:'请先登录'});return true;}
    if(req.headers['sec-fetch-site']==='cross-site'){send(403,{error:'请求来源无效'});return true;}
    if(req.method!=='GET'){res.setHeader('allow','GET');send(405,{error:'此接口仅供读取'});return true;}
    const workspaceId=url.searchParams.get('workspaceId');
    if([...url.searchParams.keys()].some(key=>key!=='workspaceId')||url.searchParams.getAll('workspaceId').length>1||workspaceId!==null&&!validId(workspaceId)){
      send(400,{error:'工作区范围无效'});return true;
    }
    const workspaces=await Promise.all(sources.filter(s=>s.accountId===user.id&&(workspaceId===null||s.workspaceId===workspaceId)).map(snapshot));
    const body={format:'geneloop-motif-catalog-v1',workspaces};
    const revision=createHash('sha256').update(JSON.stringify(body)).digest('hex');
    send(200,{...body,revision});return true;
  };
}
