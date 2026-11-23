import {randomUUID,createHash} from 'node:crypto';
import {runPrivacyWorker} from './privacy_worker_pool.ts';

/** Opaque handles preserve private reader lookups across redacted tool replies.
 * This table is scoped to one learning host and is never written or exported.
 */
export function createLearningPrivacyBoundary(options:{onBind?:(binding:{field:string;alias:string;source_sha256:string})=>void}={}) {
  const fields=new Set(['run_id','call_id','packet_id']), forward=new Map<string,string>(), backward=new Map<string,string>();
  const arrays=new Map<string,string>();
  for(const field of fields){arrays.set(field+'s',field);arrays.set('source_'+field+'s',field);}
  function identifier(key:string,item:string,expose:boolean):string {
    const original=backward.get(key+'\0'+item);
    if(expose){
      if(original!==undefined)return item;
      const identity=key+'\0'+item;
      if(!forward.has(identity)){
        if(forward.size>=20000)throw Error('geneloop_privacy_rejected');
        const alias='private-'+randomUUID();
        options.onBind?.({field:key,alias,source_sha256:createHash('sha256').update(item).digest('hex')});
        forward.set(identity,alias);backward.set(key+'\0'+alias,item);
      }
      return forward.get(identity)!;
    }
    if(original===undefined&&item.startsWith('private-'))throw Error('geneloop_privacy_rejected');
    return original??item;
  }
  function walk(value:any,expose:boolean):any {
    if(Array.isArray(value))return value.map(row=>walk(row,expose));
    if(!value||typeof value!=='object')return value;
    return Object.fromEntries(Object.entries(value).map(([key,item])=>{
      if(fields.has(key)&&typeof item==='string')return [key,identifier(key,item,expose)];
      const field=arrays.get(key);
      if(field&&Array.isArray(item)&&item.every(row=>typeof row==='string'))
        return [key,item.map(row=>identifier(field,row,expose))];
      return [key,walk(item,expose)];
    }));
  }
  return {resolve:(value:any)=>walk(value,false),show:(value:any)=>privacyLearningView(walk(value,true))};
}

/** Error replies are learning content too. Never expose a worker's raw stack. */
export async function safeLearningError(error:unknown):Promise<Error> {
  let message='geneloop_privacy_rejected';
  try {
    const original=error instanceof Error?error.message:String(error);
    if(original!==message)message=(await privacyLearningView({message:original})).message;
  } catch {}
  const safe=Error(message);safe.stack=undefined;return safe;
}

/** All online learning readers use the same local Presidio/Gitleaks worker. */
export async function privacyLearningView(value: unknown, options: {python?: string; publication?: boolean;signal?:AbortSignal} = {}): Promise<any> {
  const python = options.python ?? process.env.SSS_PYTHON;
  if (!python) throw Error('geneloop_privacy_rejected');
  let body:string|undefined;
  try{body=JSON.stringify(value);}catch{throw Error('geneloop_privacy_rejected');}
  if (typeof body !== 'string' || Buffer.byteLength(body) > 32*1024*1024) throw Error('geneloop_privacy_rejected');
  return runPrivacyWorker(python,options.publication?'publication':'learning',JSON.parse(body),options.signal);
}

export async function projectPlatformLearningTrace(python: string,input: string,scene: string,
  status: string,start: number,catalog: string,share = false,signal?:AbortSignal): Promise<string> {
  return JSON.stringify(await runPrivacyWorker(python,'project',{input,scene,status,start,catalog,share},signal));
}
