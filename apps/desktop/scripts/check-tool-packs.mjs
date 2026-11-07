// Real archive/download diagnostics. No model, account, registry or install writes.
import assert from 'node:assert/strict';
import {createHash,randomBytes} from 'node:crypto';
import {createServer} from 'node:http';
import {spawnSync} from 'node:child_process';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,existsSync,copyFileSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve,relative,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import {ToolPackStore,validateToolCatalog} from '../dist/tool-pack-store.js';
import {prepareInstallerCodec} from './prepare-installer-codec.mjs';
const app=fileURLToPath(new URL('../',import.meta.url));
const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-tool-packs-')));
const sha=value=>createHash('sha256').update(value).digest('hex');
let server;
try{
 const codec=await prepareInstallerCodec(app,join(root,'codec')),source=join(root,'source'),packs=join(root,'packs');
 mkdirSync(source);mkdirSync(packs);mkdirSync(join(source,'python'));
 const text=Buffer.from('中文材料与换行\n'),noise=randomBytes(768*1024);
 writeFileSync(join(source,'python','材料.txt'),text);writeFileSync(join(source,'python','binary.dat'),noise);
 const pack={id:'python',label:'诊断工具',required:true,filename:'python-0123456789abcdef.7z',files:[
  {path:'python/材料.txt',bytes:text.length,sha256:sha(text)},
  {path:'python/binary.dat',bytes:noise.length,sha256:sha(noise)},
 ]};
 const archive=join(packs,pack.filename);
 assert.equal(spawnSync(codec.path,['a','-t7z',archive,'python','-bd','-bso0','-bse2'],{cwd:source,windowsHide:true}).status,0);
 const bytes=readFileSync(archive);Object.assign(pack,{bytes:bytes.length,sha256:sha(bytes),unpackedBytes:text.length+noise.length});
 const catalog={schema:1,toolsetId:sha('fixture'),platform:process.platform,arch:process.arch,baseUrl:null,codec,packages:[pack]};
 for(const bad of ['../escape','/absolute','python/../escape','python/a:stream','python/file.']){
  const invalid=structuredClone(catalog);invalid.packages[0].files[0].path=bad;
  assert.throws(()=>validateToolCatalog(invalid));
 }
 const options=home=>({home:join(root,home),codecDirectory:join(root,'codec'),change:()=>{}});
 const local=new ToolPackStore(catalog,options('local'));local.setLocalSource(packs);await local.prepare();
 assert.equal(local.state().ready,true);assert.deepEqual(readFileSync(join(local.tools,'python','材料.txt')),text);
 assert.deepEqual(readFileSync(join(local.tools,'python','binary.dat')),noise);
 const restarted=new ToolPackStore(catalog,options('local'));assert.equal(restarted.state().ready,true);await restarted.prepare();

 // Completed partial downloads must be promoted without a failing HTTP 416.
 const completeHome=join(root,'complete');mkdirSync(join(completeHome,'downloads'),{recursive:true});
 copyFileSync(archive,join(completeHome,'downloads',pack.sha256+'.7z.part'));
 const complete=new ToolPackStore({...catalog,baseUrl:'https://tools.example.invalid/'},{...options('complete'),fetcher:()=>{throw Error('不应重复下载');}});
 await complete.prepare();assert.equal(complete.state().ready,true);

 // Real HTTP streaming, cancellation and Range continuation of an archive.
 const requests=[];
 server=createServer((req,res)=>{
  const offset=Number(req.headers.range?.match(/^bytes=(\d+)-$/)?.[1]??0);requests.push(offset);
  res.writeHead(offset?206:200,{'Content-Length':bytes.length-offset,...(offset?{'Content-Range':`bytes ${offset}-${bytes.length-1}/${bytes.length}`}:{})});
  let cursor=offset;const timer=setInterval(()=>{const end=Math.min(cursor+16384,bytes.length);res.write(bytes.subarray(cursor,end));cursor=end;if(cursor===bytes.length){clearInterval(timer);res.end();}},4);
  res.on('close',()=>clearInterval(timer));
 });
 await new Promise(done=>server.listen(0,'127.0.0.1',done));
 const httpFetch=(_url,options)=>fetch('http://127.0.0.1:'+server.address().port+'/pack',options);
 const remote={...catalog,baseUrl:'https://tools.example.invalid/'};let download,scheduled=false;
 download=new ToolPackStore(remote,{...options('network'),fetcher:httpFetch,change:()=>{if(!scheduled&&download?.state().rows[0].received>0&&download.state().busy){scheduled=true;setTimeout(()=>download.cancel(),30);}}});
 await assert.rejects(download.prepare());assert.equal(download.state().ready,false);
 const resumed=new ToolPackStore(remote,{...options('network'),fetcher:httpFetch});await resumed.prepare();
 assert.equal(resumed.state().ready,true);assert.ok(requests.some(n=>n>0),'实际发送 Range 续传');

 // A digest mismatch never reaches native extraction or activates the tools.
 const wrong=structuredClone(catalog);wrong.packages[0].sha256=sha('wrong');
 const rejected=new ToolPackStore(wrong,options('rejected'));rejected.setLocalSource(packs);
 await assert.rejects(rejected.prepare(),/校验失败/);assert.equal(rejected.state().ready,false);assert.equal(existsSync(join(rejected.tools,'python')),false);
 console.log(JSON.stringify({diagnostic:true,groups:['catalog-paths','real-7zip-unicode-and-bytes','restart','completed-partial','http-cancel-range-resume','hash-failure-before-extraction']}));
}finally{
 if(server)await new Promise(done=>server.close(done));
 const rel=relative(realpathSync(tmpdir()),root);assert.ok(rel&&!rel.startsWith('..')&&!isAbsolute(rel));rmSync(root,{recursive:true,force:true});
}
