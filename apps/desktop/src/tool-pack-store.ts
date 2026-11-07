import {createHash,randomUUID} from 'node:crypto';
import {createReadStream,createWriteStream,existsSync,lstatSync,mkdirSync,readFileSync,readdirSync,readlinkSync,realpathSync,renameSync,rmSync,writeFileSync} from 'node:fs';
import {chmod} from 'node:fs/promises';
import {dirname,isAbsolute,join,relative,resolve,sep} from 'node:path';
import {spawn} from 'node:child_process';
import {Readable,Transform} from 'node:stream';
import {pipeline} from 'node:stream/promises';

export type ToolFile={path:string;bytes:number;sha256:string;mode?:number;kind?:'symlink';target?:string};
export type ToolPack={id:string;label:string;required:boolean;filename:string;bytes:number;unpackedBytes:number;sha256:string;files:ToolFile[]};
export type ToolCatalog={schema:1;toolsetId:string;platform:string;arch:string;baseUrl:string|null;codec:{filename:string;sha256:string;version:string};packages:ToolPack[]};
export type ToolPackRow={id:string;label:string;required:boolean;bytes:number;received:number;phase:'pending'|'downloading'|'extracting'|'checking'|'ready'|'error';message?:string};
const under=(root:string,path:string)=>{const p=relative(root,path);return p!==''&&p!=='..'&&!p.startsWith('..'+sep)&&!isAbsolute(p);};
const validHash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
// Keep the filesystem prefix short for native libraries that still use Windows
// MAX_PATH. The complete digest remains in the trusted catalog and ready marker.
export function toolsetDirectory(home:string,id:string){if(!validHash(id))throw Error('工具版本无效');return resolve(home,id.slice(0,24));}
export function toolMember(root:string,name:string):string{
  if(!name||name.includes('\\')||/[\x00-\x1f<>:"|?*]/.test(name)||name.split('/').some(p=>!p||p==='.'||p==='..'||/[. ]$/.test(p)))throw Error('工具文件路径无效');
  const path=resolve(root,name);if(!under(root,path))throw Error('工具文件路径越界');return path;
}
export function validateToolCatalog(value:unknown):ToolCatalog{
  const c=value as ToolCatalog;if(!c||c.schema!==1||!validHash(c.toolsetId)||!Array.isArray(c.packages)||!c.packages.length||c.packages.length>16)throw Error('工具目录版本无效');
  if(c.platform!==process.platform||c.arch!==process.arch)throw Error('工具包与当前系统不匹配');
  if(c.baseUrl){const u=new URL(c.baseUrl);if(u.protocol!=='https:'||u.username||u.password)throw Error('工具下载地址无效');}
  if(!c.codec||!['7za.exe','7zz'].includes(c.codec.filename)||!validHash(c.codec.sha256))throw Error('工具解码器配置无效');
  const seen=new Set<string>(),ids=new Set<string>(),owners=new Map<string,string>(),root=resolve('.');
  for(const p of c.packages){
    if(!/^[a-z][a-z0-9-]{0,30}$/.test(p.id)||ids.has(p.id)||typeof p.label!=='string'||typeof p.required!=='boolean'||!validHash(p.sha256)||!new RegExp('^'+p.id+'-[a-f0-9]{16}\\.7z$').test(p.filename)||!Number.isSafeInteger(p.bytes)||p.bytes<1||!Array.isArray(p.files)||!p.files.length)throw Error('工具包信息无效');ids.add(p.id);
    let bytes=0;
    for(const f of p.files){toolMember(root,f.path);const key=f.path.toLowerCase(),prefix=f.path.split('/')[0];
      if(seen.has(key)||owners.has(prefix)&&owners.get(prefix)!==p.id||!validHash(f.sha256)||!Number.isSafeInteger(f.bytes)||f.bytes<0)throw Error('工具目录存在重复或无效文件');
      seen.add(key);owners.set(prefix,p.id);bytes+=f.bytes;
      if(f.kind==='symlink'){
        if(c.platform==='win32'||typeof f.target!=='string'||isAbsolute(f.target)||!under(root,resolve(dirname(toolMember(root,f.path)),f.target)))throw Error('工具链接越界');
      }else if(f.kind!==undefined)throw Error('工具文件类型无效');
    }
    if(bytes!==p.unpackedBytes)throw Error('工具包大小记录无效');
  }return c;
}
async function digest(path:string){const h=createHash('sha256');for await(const chunk of createReadStream(path))h.update(chunk);return h.digest('hex');}
function plainDirectory(path:string){mkdirSync(path,{recursive:true,mode:0o700});if(lstatSync(path).isSymbolicLink()||realpathSync(path).toLowerCase()!==resolve(path).toLowerCase())throw Error('工具目录不能是链接');}

export class ToolPackStore{
  readonly catalog:ToolCatalog;readonly tools:string;
  private home:string;private cache:string;private codec:string;private rows:ToolPackRow[];private abort?:AbortController;
  private change:()=>void;private fetcher:typeof fetch;private local?:string;
  constructor(catalog:unknown,options:{home:string;codecDirectory:string;change:()=>void;fetcher?:typeof fetch}){
    this.catalog=validateToolCatalog(catalog);this.home=toolsetDirectory(options.home,this.catalog.toolsetId);this.tools=join(this.home,'tools');this.cache=resolve(options.home,'downloads');this.codec=join(options.codecDirectory,this.catalog.codec.filename);
    this.change=options.change;this.fetcher=options.fetcher??fetch;plainDirectory(this.home);plainDirectory(this.cache);plainDirectory(this.tools);
    this.rows=this.catalog.packages.map(p=>({id:p.id,label:p.label,required:p.required,bytes:p.bytes,received:0,phase:this.isInstalled(p)?'ready':'pending'}));
  }
  private marker(p:ToolPack){return join(this.home,p.id+'.json');}
  private isInstalled(p:ToolPack){try{const m=JSON.parse(readFileSync(this.marker(p),'utf8'));return m.sha256===p.sha256&&p.files.every(f=>existsSync(toolMember(this.tools,f.path)));}catch{return false;}}
  state(){return {enabled:true,busy:!!this.abort,ready:this.rows.every(r=>!r.required||r.phase==='ready'),configured:!!this.catalog.baseUrl||!!this.local,localSource:!!this.local,rows:this.rows.map(r=>({...r})),downloadBytes:this.rows.reduce((n,r)=>n+r.bytes,0)};}
  setLocalSource(path:string){if(this.abort)throw Error('请先暂停当前工具准备');const s=lstatSync(path);if(!s.isDirectory())throw Error('请选择工具包所在文件夹');this.local=realpathSync(path);this.change();}
  cancel(){this.abort?.abort();}
  private update(id:string,next:Partial<ToolPackRow>){Object.assign(this.rows.find(r=>r.id===id)!,next);this.change();}
  async prepare(ids?:string[]){
    if(this.abort)throw Error('工具正在准备');const selected=ids??this.rows.map(r=>r.id);if(selected.some(id=>!this.rows.some(r=>r.id===id)))throw Error('未知工具包');
    const controller=new AbortController();this.abort=controller;this.change();
    try{for(const pack of this.catalog.packages){if(!selected.includes(pack.id))continue;
      if(this.isInstalled(pack)){this.update(pack.id,{phase:'ready',received:pack.bytes,message:undefined});continue;}
      try{await this.prepareOne(pack,controller.signal);this.update(pack.id,{phase:'ready',received:pack.bytes,message:undefined});}
      catch(error){this.update(pack.id,{phase:controller.signal.aborted?'pending':'error',message:controller.signal.aborted?'已暂停，可继续':error instanceof Error?error.message:'工具准备失败'});throw error;}
    }}finally{this.abort=undefined;this.change();}
  }
  private async archive(pack:ToolPack,signal:AbortSignal){
    const final=join(this.cache,pack.sha256+'.7z'),partial=final+'.part';
    if(existsSync(final)&&!lstatSync(final).isSymbolicLink()&&await digest(final)===pack.sha256)return final;
    if(existsSync(partial)&&lstatSync(partial).isSymbolicLink())throw Error('下载缓存包含链接');
    let offset=existsSync(partial)?lstatSync(partial).size:0;if(offset>pack.bytes){rmSync(partial);offset=0;}
    if(offset===pack.bytes){
      if(await digest(partial)===pack.sha256){if(existsSync(final))rmSync(final);renameSync(partial,final);return final;}
      rmSync(partial);offset=0;
    }
    this.update(pack.id,{phase:'downloading',received:offset,message:undefined});
    let input:Readable;
    if(this.local){const source=join(this.local,pack.filename);if(!existsSync(source))throw Error('该文件夹缺少「'+pack.label+'」工具包');input=createReadStream(source,{start:offset});}
    else{
      if(!this.catalog.baseUrl)throw Error('尚未配置下载源，请从本机导入工具包');
      const url=new URL(pack.filename,this.catalog.baseUrl.replace(/\/?$/,'/'));
      const response=await this.fetcher(url,{signal,credentials:'omit',headers:offset?{Range:'bytes='+offset+'-'}:{}});
      if(!response.ok||!response.body)throw Error('工具下载失败，请稍后重试');
      if(offset&&response.status===206){if(!response.headers.get('content-range')?.startsWith('bytes '+offset+'-'))throw Error('下载续传范围无效');}
      else if(offset){offset=0;rmSync(partial);}
      input=Readable.fromWeb(response.body as never);
    }
    let received=offset,last=0;
    const progress=new Transform({transform:(chunk:Buffer,_encoding,done)=>{received+=chunk.length;if(received>pack.bytes)return done(Error('工具包大小与版本不符'));if(Date.now()-last>150){last=Date.now();this.update(pack.id,{received});}done(null,chunk);}});
    await pipeline(input,progress,createWriteStream(partial,{flags:offset?'a':'w',mode:0o600}),{signal});
    signal.throwIfAborted();this.update(pack.id,{phase:'checking',received});
    if(received!==pack.bytes||await digest(partial)!==pack.sha256){rmSync(partial);throw Error('工具包校验失败，请重新下载');}
    if(existsSync(final))rmSync(final);renameSync(partial,final);return final;
  }
  private async prepareOne(pack:ToolPack,signal:AbortSignal){
    const archive=await this.archive(pack,signal);signal.throwIfAborted();
    if(!existsSync(this.codec)||lstatSync(this.codec).isSymbolicLink())throw Error('工具解码器缺失，请重新安装应用');
    const staging=join(this.home,'.stage-'+pack.id+'-'+randomUUID());plainDirectory(staging);
    try{
      this.update(pack.id,{phase:'extracting',received:pack.bytes});
      // Only an archive whose complete digest matches this app's pinned catalog
      // reaches the native decoder. No user-supplied archive paths are exposed.
      await new Promise<void>((done,reject)=>{
        const child=spawn(this.codec,['x','-y','-bd','-bso0','-bse2',archive,'-o'+staging],{cwd:staging,windowsHide:true,stdio:'ignore'});
        const abort=()=>child.kill();signal.addEventListener('abort',abort,{once:true});
        child.once('error',reject);child.once('close',code=>{signal.removeEventListener('abort',abort);if(signal.aborted)reject(Error('已暂停工具准备'));else if(code!==0)reject(Error('工具解压失败，请重试'));else done();});
      });
      signal.throwIfAborted();this.update(pack.id,{phase:'checking'});
      const expected=new Set(pack.files.map(f=>f.path));let count=0;
      const inspect=(folder:string)=>{for(const item of readdirSync(folder,{withFileTypes:true})){const p=join(folder,item.name);if(item.isDirectory()&&!item.isSymbolicLink())inspect(p);else{if(!expected.has(relative(staging,p).split(sep).join('/')))throw Error('工具包包含未登记文件');count++;}}};inspect(staging);
      if(count!==pack.files.length)throw Error('工具文件不完整');
      for(const f of pack.files){signal.throwIfAborted();const path=toolMember(staging,f.path),s=lstatSync(path);
        if(f.kind==='symlink'){if(!s.isSymbolicLink()||readlinkSync(path)!==f.target)throw Error('工具链接与版本不符');}
        else{if(!s.isFile()||s.isSymbolicLink()||s.nlink!==1||s.size!==f.bytes||await digest(path)!==f.sha256)throw Error('工具文件校验失败');if(process.platform!=='win32'&&f.mode!==undefined)await chmod(path,f.mode);}
      }
      for(const name of readdirSync(staging)){const from=join(staging,name),to=toolMember(this.tools,name);if(existsSync(to)){if(lstatSync(to).isSymbolicLink())throw Error('工具目标包含链接');rmSync(to,{recursive:true,force:true});}renameSync(from,to);}
      writeFileSync(this.marker(pack),JSON.stringify({sha256:pack.sha256}),{mode:0o600});
      if(this.catalog.packages.filter(p=>p.required).every(p=>this.isInstalled(p)))writeFileSync(join(this.home,'ready.json'),JSON.stringify({toolsetId:this.catalog.toolsetId}),{mode:0o600});
    }finally{if(under(this.home,staging)&&existsSync(staging)&&!lstatSync(staging).isSymbolicLink())rmSync(staging,{recursive:true,force:true});}
  }
}
