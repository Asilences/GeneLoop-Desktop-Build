import {appendFileSync, lstatSync} from 'node:fs';
import {join} from 'node:path';
import {createRsiSharing} from '../../rsi_sharing.ts';
import {projectPlatformLearningTrace} from '../../geneloop_privacy.ts';

type Source = {output:string;scene:string;status:string;start:number | undefined};
type Config = {output:string;provider_mode?:string;rsi_sharing_endpoint?:string;learning_python?:string};

/** Shared by both task hosts; ownership is checked before exposing a source. */
export function mountRsiSharing(ctx:any,config:Config,source:(id:string)=>Promise<Source>) {
  async function available(id: string) {
    const row = await source(id);
    const input = join(row.output,'events.jsonl');
    if (row.status!=='completed' || !Number.isSafeInteger(row.start) || !lstatSync(input).isFile())
      throw Error('sharing_source_unavailable');
    return {row, input};
  }
  const sharing = createRsiSharing({endpoint:config.rsi_sharing_endpoint,allowLoopback:config.provider_mode==='mock',
    async authorize(id) { await available(id); },
    async prepare(id) {
      const {row, input} = await available(id), python = process.env.SSS_PYTHON ?? config.learning_python;
      if (!python) throw Error('sharing_source_unavailable');
      return projectPlatformLearningTrace(python,input,row.scene,row.status,row.start!,
        join(row.output,'effective-config.json'),true);
    },
    audit:event=>appendFileSync(join(config.output,'rsi-sharing-audit.jsonl'),
      JSON.stringify({time:new Date().toISOString(),...event})+'\n',{mode:0o600}),
  });
  ctx.effect(()=>{
    const release=ctx.connection.fetch.register({path:'/api/harless/rsi-sharing',methods:['GET','POST'],requestBody:'buffered',
      async fetch(request:Request) {
        const denied=ctx.connection.requestRejection(request);
        return denied?new Response('Unauthorized',{status:denied}):sharing.handle(request);
      }});
    return async()=>{sharing.dispose();await release();};
  },'harless-rsi-sharing');
}
