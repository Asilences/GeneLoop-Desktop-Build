// MCP framing and requests are the official SDK's; child lifetime is DSH's.
import {ReadBuffer,serializeMessage} from '@modelcontextprotocol/sdk/shared/stdio.js';

export class NativeMcpTransport {
  constructor(ctx,argv,cwd,env,signal) {Object.assign(this,{ctx,argv,cwd,env,signal});}
  async start() {
    this.signal.throwIfAborted();
    this.child=this.ctx.subprocess.spawn({argv:this.argv,cwd:this.cwd,env:this.env,signal:this.signal,
      graceMs:1000,stdio:{stdin:'pipe',stdout:'pipe',stderr:{maxBytes:65536}}});
    const buffer=new ReadBuffer();
    this.child.stdout.on('data',chunk=>{
      try {buffer.append(chunk);let message;while((message=buffer.readMessage())!==null)this.onmessage?.(message);}
      catch(error){this.onerror?.(error);this.child.terminate();}
    });
    this.child.stdin.on('error',error=>this.onerror?.(error));
    this.child.done.then(()=>this.onclose?.(),error=>{this.onerror?.(error);this.onclose?.();});
  }
  async send(message) {
    this.signal.throwIfAborted();
    if(!this.child?.stdin?.writable)throw Error('本机场景连接已关闭。');
    await new Promise((resolve,reject)=>this.child.stdin.write(serializeMessage(message),error=>error?reject(error):resolve()));
  }
  async close() {
    this.child?.terminate();
    if(this.child) {await this.child.done.catch(()=>{});await this.child.waitForExit(AbortSignal.timeout(10000));}
  }
}
