// Follow DSH MCP's attachment admission: prove the current model's image
// capability, validate/store the whole batch, and keep the raw receipt separate
// from the model projection. Upstream API: @deepseek-ai/dsh-attachment.
import {isDeepStrictEqual} from 'node:util';
export function workflowOutput(ctx,run) {
  const projections=new WeakMap();
  return {
    output:{schema:{},render:(_args,value)=>[{type:'text',text:JSON.stringify({...value,content:value.content?.map(block=>block.type==='image'?{type:'image',mimeType:block.mimeType}:block)})}]},
    async execute(args,exec) {
      const value=await run(args,exec);if(value.isError)throw Error(JSON.stringify(value));
      const blocks=[{type:'text',text:JSON.stringify({result:value.result,artifacts:value.artifacts,execution:value.execution})}];
      const images=(value.content??[]).filter(block=>block.type==='image');
      if(images.length) {
        try {
          const store=ctx.get('attachments'),llm=ctx.get('llm'),agent=exec.agent;
          const route=agent?.session.requestHeader()?.config;
          const provider=route?.provider??agent?.options.provider,model=route?.model??agent?.options.model;
          if(!store||!llm||!provider||!model)throw Error('当前本机路由未提供图像附件能力');
          const info=await llm.resolveModelInfo(provider,model,exec.signal);
          if(!info.inputModalities?.includes('image'))throw Error('当前模型未声明图像输入能力');
          const inputs=images.map(block=>{
            if(!['image/png','image/jpeg','image/webp','image/gif'].includes(block.mimeType)||typeof block.data!=='string')throw Error('图像类型无效');
            const data=Buffer.from(block.data,'base64');if(data.toString('base64')!==block.data)throw Error('图像编码无效');
            return {data,mediaType:block.mimeType};
          });
          exec.signal.throwIfAborted();const refs=await store.saveImages(inputs);exec.signal.throwIfAborted();
          blocks.push(...refs.map(attachment=>({type:'image',attachment})));
        }catch(error){exec.signal.throwIfAborted();blocks.push({type:'text',text:'图像未进入模型：'+error.message+'。不能声称已目视核验。'});}
      }
      projections.set(exec,{value,blocks});return value;
    },
    finalizeContent(exec,result) {
      const projection=projections.get(exec);projections.delete(exec);
      if(projection&&!result.isError&&isDeepStrictEqual(result.value,projection.value))return projection.blocks;
    },
  };
}
