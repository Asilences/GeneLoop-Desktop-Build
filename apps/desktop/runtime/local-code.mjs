// A fixed native replacement for the Web Docker code substrate. The DSH Agent
// is unchanged. Guest code runs inside QuickJS WASM, not Node's vm/worker with
// host privileges; only approved input and new text-output bindings are exposed.
import {getQuickJS} from 'quickjs-emscripten';
import {stripTypeScriptTypes} from 'node:module';
import {readFileSync,writeFileSync,mkdirSync,lstatSync,realpathSync} from 'node:fs';
import {resolve,join,dirname,relative,sep} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const sha=data=>createHash('sha256').update(data).digest('hex');

export async function runNativeCode(q) {
  if(!q||typeof q.program!=='string'||Buffer.byteLength(q.program)>256*1024)throw Error('code_program_limit');
  const work=realpathSync(q.workspace),inputRoot=join(work,'inputs');
  const manifest=JSON.parse(readFileSync(join(work,'approved-inputs.json'),'utf8')).files;
  const plain=(root,path)=>{
    const rel=relative(root,path);
    if(!rel||rel==='..'||rel.startsWith('..'+sep))throw Error('code_path_scope');
    for(let at=path;at!==root;at=dirname(at))if(lstatSync(at).isSymbolicLink())throw Error('code_link_refused');
    const info=lstatSync(path);if(!info.isFile()||info.nlink!==1)throw Error('code_regular_file_required');
    return path;
  };
  const source=name=>{
    if(typeof name!=='string'||!Object.hasOwn(manifest,name)||name!==name.split(/[\\/]/).at(-1))throw Error('code_input_not_approved');
    const bytes=readFileSync(plain(inputRoot,resolve(inputRoot,name)));
    if(bytes.length>20*1024*1024||sha(bytes)!==manifest[name])throw Error('code_input_changed');
    return bytes;
  };
  const QuickJS=await getQuickJS(),vm=QuickJS.newContext();
  const outputs=new Map(),logs=[];let outputBytes=0,logBytes=0,result;
  const deadline=Date.now()+10000;
  vm.runtime.setMemoryLimit(64*1024*1024);vm.runtime.setMaxStackSize(512*1024);
  vm.runtime.setInterruptHandler(()=>Date.now()>deadline);
  function invoke(kind,args) {
    if(kind==='list')return {files:Object.entries(manifest).map(([name,sha256])=>({name,sha256}))};
    if(kind==='read_text'||kind==='read_base64') {
      const bytes=source(args.name);
      return {name:args.name,sha256:manifest[args.name],...(kind==='read_text'?{text:new TextDecoder('utf-8',{fatal:true}).decode(bytes)}:{base64:bytes.toString('base64')})};
    }
    if(kind==='write_text') {
      if(q.allow_output!==true)throw Error('code_output_not_allowed');
      if(typeof args.name!=='string'||args.name.length>180||/[\\:\x00-\x1f]/.test(args.name)||
        args.name.split('/').some(x=>!x||x==='.'||x==='..')||!/\.(txt|md|json|csv|tsv)$/i.test(args.name)||typeof args.text!=='string'||outputs.has(args.name))throw Error('code_output_invalid');
      const bytes=Buffer.from(args.text);outputBytes+=bytes.length;
      if(outputBytes>2*1024*1024)throw Error('code_output_byte_limit');
      outputs.set(args.name,bytes);return {name:args.name,sha256:sha(bytes),bytes:bytes.length};
    }
    if(kind==='log') {const text=String(args);logBytes+=Buffer.byteLength(text);if(logBytes>65536)throw Error('code_log_limit');logs.push(text);return null;}
    throw Error('code_binding_not_available');
  }
  try {
    const io=vm.newFunction('__nativeIO',(kind,args)=>vm.newString(JSON.stringify(invoke(vm.getString(kind),JSON.parse(vm.getString(args))))));
    vm.setProp(vm.global,'__nativeIO',io);io.dispose();
    const prelude=`const inputs=Object.freeze({list:(a={})=>JSON.parse(__nativeIO('list',JSON.stringify(a))),
read_text:a=>JSON.parse(__nativeIO('read_text',JSON.stringify(a))),read_base64:a=>JSON.parse(__nativeIO('read_base64',JSON.stringify(a)))});
const outputs=Object.freeze({write_text:a=>JSON.parse(__nativeIO('write_text',JSON.stringify(a)))});
const console=Object.freeze({log:(...a)=>__nativeIO('log',JSON.stringify(a.map(x=>typeof x==='string'?x:JSON.stringify(x)).join(' ')))});`;
    const code=stripTypeScriptTypes('(async()=>{\n'+q.program+'\n})()',{mode:'transform'});
    const evaluated=vm.evalCode(prelude+'\n'+code,'native-task.js');
    if(evaluated.error){const error=vm.dump(evaluated.error);evaluated.error.dispose();throw Error(error?.message??'code_exception');}
    const handle=evaluated.value;
    try {
      for(;;) {
        const state=vm.getPromiseState(handle);
        if(state.type==='fulfilled') {result=vm.dump(state.value);state.value.dispose();break;}
        if(state.type==='rejected') {const error=vm.dump(state.error);state.error.dispose();throw Error(error?.message??'code_exception');}
        if(Date.now()>deadline||!vm.runtime.hasPendingJob())throw Error('code_pending_or_deadline');
        const jobs=vm.runtime.executePendingJobs(100);
        if(jobs.error){const error=vm.dump(jobs.error);jobs.error.dispose();throw Error(error?.message??'code_exception');}
      }
    }finally{handle.dispose();}
    for(const name of Object.keys(manifest))source(name);
    const destination=join(work,'outputs','code',randomUUID()),artifacts=[];
    for(const [name,bytes]of outputs) {
      const path=resolve(destination,name),rel=relative(destination,path);
      if(rel==='..'||rel.startsWith('..'+sep))throw Error('code_output_scope');
      mkdirSync(dirname(path),{recursive:true,mode:0o700});writeFileSync(path,bytes,{flag:'wx',mode:0o600});
      artifacts.push({name,path,sha256:sha(bytes),bytes:bytes.length});
    }
    const value={runtime:'typescript/quickjs-wasm',result:{value:result??null,logs},artifacts,input_sha256:manifest,program_sha256:sha(q.program),source_files_unchanged:true};
    if(Buffer.byteLength(JSON.stringify(value))>2*1024*1024)throw Error('code_result_limit');
    return value;
  } finally {vm.dispose();}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href) {
  try {if(process.argv[2]==='--capabilities') {
      const runtime=await getQuickJS(),vm=runtime.newContext();
      try {const result=vm.evalCode('1+1');if(result.error){result.error.dispose();throw Error('code_probe_failed');}
        const value=vm.dump(result.value);result.value.dispose();if(value!==2)throw Error('code_probe_failed');}
      finally{vm.dispose();}
      process.stdout.write(JSON.stringify({available:true,runtime:'typescript/quickjs-wasm'}));
    } else {let raw='';for await(const chunk of process.stdin){raw+=chunk;if(Buffer.byteLength(raw)>1024*1024)throw Error('code_request_limit');}
    process.stdout.write(JSON.stringify(await runNativeCode(JSON.parse(raw))));
    }
  }catch(error){process.stdout.write(JSON.stringify({runtime:'typescript/quickjs-wasm',result:{error:{kind:'execution_failed',message:String(error.message).slice(0,500)}},artifacts:[]}));process.exitCode=1;}
}
