// Bound expensive native commands across scopes of the existing DSH host.
// Task cancellation also removes queued work; no child is started after abort.
const budgets=new WeakMap();
const parallel=2;
export function acquireNativeOperation(ctx,signal) {
  signal.throwIfAborted();
  // Cordis service lookups can return a new scoped proxy on every lookup.
  // Its public root context is stable across the Agent and child scopes.
  const owner=ctx.root??ctx;
  if(!owner||typeof owner!=='object')throw Error('本机进程服务尚未就绪');
  let state=budgets.get(owner);
  if(!state){state={active:0,queue:[]};budgets.set(owner,state);}
  function drain(){
    while(state.active<parallel&&state.queue.length){
      const next=state.queue.shift();next.signal.removeEventListener('abort',next.abort);
      if(next.signal.aborted){next.reject(next.signal.reason);continue;}
      state.active++;let released=false;
      next.resolve(()=>{if(released)return;released=true;state.active--;drain();});
    }
  }
  return new Promise((resolve,reject)=>{
    const row={signal,resolve,reject,abort(){
      const index=state.queue.indexOf(row);if(index<0)return;
      state.queue.splice(index,1);signal.removeEventListener('abort',row.abort);reject(signal.reason);drain();
    }};
    state.queue.push(row);signal.addEventListener('abort',row.abort,{once:true});
    if(signal.aborted)row.abort();else drain();
  });
}
