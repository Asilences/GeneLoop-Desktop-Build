import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {EventEmitter} from 'node:events';

test('桌面网关允许原生图片和子智能体结构化结果，拒绝远程图片及越权工具', {skip:!process.features?.typescript}, async()=>{
  const {createDesktopModelRoute,DESKTOP_MODEL_PATH}=await import('../scripts/harless_desktop_model.mjs');
  const control=createServer((req,res)=>{req.resume();res.end('{}');});
  await new Promise(resolve=>control.listen(0,'127.0.0.1',resolve));
  let forwarded=0;
  const route=createDesktopModelRoute({
    config:{desktopLocalModel:{accountIds:['fixture']},apiKey:'fixture',memberPolicy:{control_token:'fixture'},
      upstreamBrokerPort:control.address().port,upstreamControlPort:control.address().port},
    json:(res,status,body)=>Object.assign(res,{status,body}),requireOrigin:()=>true,sessionHash:()=> 'fixture',isSessionActive:()=>true,
    readBounded:req=>Buffer.from(JSON.stringify(req.input)),
    forward:()=>{forwarded++;return Object.assign(new EventEmitter(),{destroy(){}});},
  });
  try {
    const lease=new EventEmitter();
    await route.handle({method:'POST',headers:{},input:{scene:'ppt'}},lease,DESKTOP_MODEL_PATH+'/lease',{id:'fixture'});
    assert.equal(lease.status,200); assert.equal(lease.body.toolsetVersion,4);
    const headers={authorization:'Bearer '+lease.body.token};
    const image={type:'image_url',image_url:{url:'data:image/png;base64,aW1hZ2U='}};
    const input={model:'deepseek-flash',stream:true,messages:[{role:'user',content:[{type:'text',text:'检查实际页面'},image]}],
      tools:[{type:'function',function:{name:'structured_output',parameters:{type:'object'}}}]};
    const accepted=new EventEmitter();
    await route.handle({method:'POST',headers,input},accepted,DESKTOP_MODEL_PATH+'/v1/chat/completions');
    assert.equal(forwarded,1); accepted.emit('close');
    for(const invalid of [
      {...input,messages:[{role:'user',content:[{type:'image_url',image_url:{url:'https://private.example/image.png'}}]}]},
      {...input,messages:[{role:'user',content:[{type:'file',file_id:'private-file'}]}]},
      {...input,messages:[{role:'user',content:[{type:'image_url',image_url:{url:'data:image/png;base64,abc'}}]}]},
      {...input,messages:[{role:'tool',content:[image]}]},
      {...input,tools:[{type:'function',function:{name:'arbitrary_server_command'}}]},
    ]) {
      const rejected=new EventEmitter();
      await route.handle({method:'POST',headers,input:invalid},rejected,DESKTOP_MODEL_PATH+'/v1/chat/completions');
      assert.equal(rejected.status,400); assert.equal(forwarded,1);
    }
    await route.handle({method:'DELETE',headers},new EventEmitter(),DESKTOP_MODEL_PATH+'/lease');
  } finally {route.close();control.closeAllConnections();await new Promise(resolve=>control.close(resolve));}
});
