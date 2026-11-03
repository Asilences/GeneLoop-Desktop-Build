/** Real standalone account-page script, with an isolated DOM/API harness. No production writes. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
const html=readFileSync(new URL('../src/adapters/harless_account.html',import.meta.url),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const flush=async()=>{for(let n=0;n<8;n++)await new Promise(resolve=>setImmediate(resolve));};
function fixture(fetcher, clipboard){
  const elements=new Map(), requests=[];
  for(const match of html.matchAll(/id="([^"]+)"/g))elements.set(match[1],{hidden:true,value:'',textContent:'',disabled:false,style:{},events:{},
    classList:{toggle(){}},addEventListener(name,fn){this.events[name]=fn;},querySelector(){return {disabled:false};},select(){this.selected=true;}});
  const document={getElementById:id=>{assert.ok(elements.has(id),id);return elements.get(id);},body:{dataset:{},toggleAttribute(){}},title:''};
  const location={pathname:'/account',search:'',origin:'https://test.invalid',replace(){}};
  const fetch=async(url,options)=>{requests.push({url,options});return fetcher(url,options);};
  runInNewContext(script,{document,location,fetch,matchMedia:()=>({matches:false,addEventListener(){}}),localStorage:{getItem(){return null;}},
    navigator:{clipboard},URL,URLSearchParams,FormData,setTimeout,alert(){}});
  return {elements,requests,$:id=>elements.get(id)};
}

test('standalone account page creates and copies a shared code, with explicit replace/cancel controls',async()=>{
  let posts=0;const copies=[];
  const f=fixture((url,options)=>url.endsWith('/me')?Response.json({user:{role:'owner',username:'owner',displayName:'Owner',createdAt:0}}):
    options.method==='GET'?Response.json({invitation:{exists:false}}):
    (++posts===1?Response.json({code:'html-shared-fixture',invitation:{exists:true,id:'html-shared-id',createdAt:10,useCount:0}}):Response.json({error:'当前密码不正确'},{status:403})),
    {writeText:async text=>copies.push(text)});
  await flush();assert.equal(posts,0);assert.equal(f.$('shared-invite-form').hidden,false);
  f.$('shared-invite-pass').value='owner-password';await f.$('shared-invite-form').events.submit({preventDefault(){}});
  assert.equal(f.$('shared-invite-code').value,'html-shared-fixture');assert.equal(f.$('shared-invite-result').hidden,false);
  assert.deepEqual(JSON.parse(f.requests.at(-1).options.body),{currentPassword:'owner-password',replace:false});
  await f.$('shared-invite-copy').onclick();assert.deepEqual(copies,['html-shared-fixture']);
  f.$('shared-invite-replace').onclick();assert.equal(f.$('shared-invite-warning').hidden,false);assert.equal(posts,1);
  f.$('shared-invite-cancel').onclick();assert.equal(f.$('shared-invite-form').hidden,true);assert.equal(posts,1);
  f.$('shared-invite-replace').onclick();await f.$('shared-invite-form').events.submit({preventDefault(){}});
  assert.equal(JSON.parse(f.requests.at(-1).options.body).replace,true);assert.match(f.$('shared-invite-error').textContent,/当前密码不正确/);
  assert.equal(f.$('shared-invite-code').value,'html-shared-fixture');assert.equal(f.$('shared-invite-result').hidden,false);
});

test('standalone page preserves an existing shared code after unavailable clipboard and retries metadata safely',async()=>{
  let reads=0;
  const f=fixture((url,options)=>url.endsWith('/me')?Response.json({user:{role:'owner',username:'owner',displayName:'Owner',createdAt:0}}):
    ++reads===1?Response.json({error:'连接暂时中断'},{status:503}):Response.json({invitation:{exists:true,id:'existing-shared-id',createdAt:11,useCount:4}}));
  await flush();assert.equal(f.$('shared-invite-form').hidden,true);assert.equal(f.$('shared-invite-retry').hidden,false);
  await f.$('shared-invite-retry').onclick();assert.match(f.$('shared-invite-state').textContent,/已成功注册 4 个账号/);
  assert.equal(f.$('shared-invite-code').value,'');assert.equal(f.$('shared-invite-result').hidden,true);
  assert.equal(f.requests.filter(x=>x.options.method==='POST').length,0);
});

test('standalone account page does not request owner invitation metadata for a member',async()=>{
  const f=fixture(()=>Response.json({user:{role:'member',username:'member',displayName:'Member',createdAt:0}}));
  await flush();assert.equal(f.$('invite-section').hidden,true);assert.equal(f.requests.length,1);
  assert.match(html,/<details><summary>单次邀请码（可选）<\/summary>/);
  assert.match(html,/向管理员获取统一邀请码，可供多人注册/);
});
