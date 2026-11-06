import { readFileSync } from 'node:fs';
import { extname, join } from 'node:path';
import type { Session } from 'electron';
import { sameServer } from './policy.ts';
type RequestWithOrigin = Request & { readonly initiatorOrigin?: string };
type Options = { session: Session; server: string; assets: string; ui: string; fail: (message: string) => void };
const FILES = ['app.js','api.js','conversation.js','components.js','lucide-icons.js','composer.js','scene-picker.js','panels.js','comparison.js','deliveries.js','desktop.css','motif-library.css','motif-library.js','workspace-run.js','motif-evidence.js','motif-example.json'];
const TYPES: Record<string,string> = {'.json':'application/json; charset=utf-8','.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml'};
/** 独立桌面页面与服务器API的传输边界；不读取、组合或执行服务器网页。 */
export class LocalFrontendHost {
  readonly served = {local:0,network:0,localScripts:[] as string[],networkScripts:[] as string[]};
  private installed=false;
  private options: Options;
  constructor(options:Options){this.options=options;}
  install():void{this.options.session.protocol.handle(new URL(this.options.server).protocol.slice(0,-1),request=>this.fetch(request));this.installed=true;}
  dispose():void{if(this.installed)this.options.session.protocol.unhandle(new URL(this.options.server).protocol.slice(0,-1));this.installed=false;}
  private local(file:string,method:string):Response{
    this.served.local++;const socket=new URL(this.options.server);socket.protocol=socket.protocol==='https:'?'wss:':'ws:';
    return new Response(method==='HEAD'?null:new Uint8Array(readFileSync(file)),{headers:{'content-type':TYPES[extname(file)]||'application/octet-stream','cache-control':'no-store','x-geneloop-desktop-resource':'local','x-content-type-options':'nosniff','content-security-policy':`default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self' ${socket.origin}; frame-src blob:; base-uri 'none'; form-action 'none'`}});
  }
  async fetch(request:RequestWithOrigin):Promise<Response>{
    const {server,ui,assets,session}=this.options;
    if(!sameServer(request.url,server))return new Response('External request denied',{status:403});
    const origin=new URL(server).origin,supplied=request.headers.get('origin');
    if((request.initiatorOrigin!==undefined&&request.initiatorOrigin!==origin)||(supplied!==null&&supplied!==origin)||request.headers.get('sec-fetch-site')==='cross-site'||(!['GET','HEAD','OPTIONS'].includes(request.method)&&request.initiatorOrigin===undefined&&supplied===null))return Response.json({error:'请求来源无效'},{status:403});
    const path=new URL(request.url).pathname;
    try{
      if(['GET','HEAD'].includes(request.method)){
        if(['/','/login','/register','/account','/starting'].includes(path))return this.local(join(ui,'index.html'),request.method);
        if(path==='/assets/geneloop-spiral.svg')return this.local(join(assets,'geneloop-spiral.svg'),request.method);
        const file=FILES.find(name=>path==='/desktop/'+name);
        if(file){if(/\.(js|css)$/.test(file))this.served.localScripts.push(path);return this.local(join(ui,file),request.method);}
      }
      if(!path.startsWith('/api/'))return new Response('Desktop resource not found',{status:404});
      const headers=new Headers(request.headers);if(request.initiatorOrigin!==undefined)headers.set('origin',request.initiatorOrigin);
      const remember=headers.get('x-geneloop-remember-login')==='1'&&request.method==='POST'&&
        request.credentials!=='omit'&&['/api/account/login','/api/account/register'].includes(path);
      headers.delete('x-geneloop-remember-login');
      this.served.network++;
      const remote=await session.fetch(request,{headers,credentials:request.credentials==='omit'?'omit':'include',bypassCustomProtocolHandlers:true,
        ...(remember?{redirect:'error' as const}:{})});
      const next=new Headers(remote.headers);for(const key of ['content-encoding','content-length','transfer-encoding','connection','keep-alive'])next.delete(key);
      if(remember&&remote.ok){
        const issued=next.getSetCookie().find(cookie=>cookie.startsWith('harless_sess='));
        const value=issued?.match(/^harless_sess=([A-Za-z0-9_-]{30,100});/)?.[1];
        if(issued&&value&&!/;\s*(max-age|expires|domain)=/i.test(issued)){
          try{
            await session.cookies.set({url:server,name:'harless_sess',value,path:'/',httpOnly:true,
              secure:origin.startsWith('https:'),sameSite:'lax',expirationDate:Math.floor(Date.now()/1000)+7*86400});
            await session.cookies.flushStore();
            next.delete('set-cookie');
            for(const cookie of remote.headers.getSetCookie())if(cookie!==issued)next.append('set-cookie',cookie);
          }catch{ /* 登录本身已成功，存储不可用时保留服务器响应。 */ }
        }
      }
      return new Response(remote.body,{status:remote.status,statusText:remote.statusText,headers:next});
    }catch{return Response.json({error:{code:'desktop/network',message:'服务器暂时无法连接，请检查网络后重试。'}},{status:503});}
  }
}
