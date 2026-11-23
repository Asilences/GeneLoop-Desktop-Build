import {createHash} from 'node:crypto';
import {lstatSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

/** Bind the built-in engine to the approved, persistent conversation workspace. */
export async function openNativePptDeck(common,tools,sessionId,signal) {
  const {createLocalPptDeckTools}=await import(pathToFileURL(tools.deck).href);
  const themes=JSON.parse(readFileSync(join(tools.sourceRoot,'scenarios/ppt_master/themes.json'),'utf8')).themes;
  const project=/^projects\/[\p{L}\p{N}][\p{L}\p{N}_-]{0,79}$/u;
  const authorize=execution=>{
    signal.throwIfAborted();
    execution.signal.throwIfAborted();
    if(execution.agent?.session.id!==sessionId)throw Error('本机 PPT 会话授权已变化。');
  };
  const deck=createLocalPptDeckTools({
    authorize,
    projectRoot(name,build) {
      const path=build?'projects/'+name:name;
      if(!project.test(path))throw Error('PPT 工程标识无效。');
      return common.resolvePath(path);
    },
    imagePath(path) {
      if(typeof path!=='string'||!/^(?:inputs|projects|outputs)\/.+\.(?:png|jpe?g)$/i.test(path)||
        path.includes('\\')||path.split('/').some(part=>!part||part==='.'||part==='..'))throw Error('PPT 图件须来自当前会话。');
      const file=common.resolvePath(path),stat=lstatSync(file);
      if(!stat.isFile()||stat.nlink!==1)throw Error('PPT 图件须为独立普通文件。');
      return file;
    },
    theme(name) {
      const theme=themes.find(row=>row.id===name);
      if(!theme)throw Error('未知 PPT 主题。可使用 general。');
      return theme;
    },
    async render({root,revision,slide_count,signal}) {
      const bytes=readFileSync(join(root,'deck.pptx'));
      const source_sha256=createHash('sha256').update(bytes).digest('hex');
      const delivery=await common.ppt('native_render',{project:root,source_sha256,slide_count},signal);
      return {...delivery,revision};
    },
  });
  const {pptDeckBuildTool,pptDeckPatchTool}=await deck.definitions();
  let busy=false;
  const execute=async (args,execution,build)=>{
    authorize(execution);
    if(busy)throw Error('当前会话已有 PPT 操作在运行。');
    busy=true;
    try {
      const current={...execution,signal:AbortSignal.any([signal,execution.signal])};
      const value=await (build?deck.build(args,current):deck.patch(args,current));
      const project=build?'projects/'+args.name:args.project;
      if(value.status==='rejected')return {...value,project};
      const {output,result,...metadata}=value;
      const receipt={...metadata,...result,project};
      authorize(current);
      if(result.mechanical_status!=='passed')return receipt;
      return {...receipt,published:common.publishPpt(output,receipt,current.signal)};
    } finally {busy=false;}
  };
  const output={schema:{type:'object'},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]};
  return [
    {...pptDeckBuildTool,output,execute:(args,exec)=>execute(args,exec,true)},
    {...pptDeckPatchTool,output,execute:(args,exec)=>execute(args,exec,false)},
  ];
}
