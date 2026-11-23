import {test} from 'node:test';
import assert from 'node:assert/strict';
import {buildMotifPool,filterMotifPool} from '../apps/desktop/ui/desktop/motif-pool.js';
const event={id:'event-1',kind:'invoke',status:'applied',actual_execution:true};
const cap=(id,status='certified',events=[])=>({id,name:id,status,events,version:{library_generation:1},toolFlow:[{from_tool:'read',to_tool:'write'}]});
const view=(caps,{catalog=false,kind='registered'}={})=>({raw:{scenario:'files',generated_at:'2026-11-09T00:00:00Z',...(catalog?{source:{kind,release:'v1'}}:{})},capabilities:caps});
const workspace=(id,caps)=>({workspaceId:id,status:'ready',view:view(caps)});
const runtime=(id,scene,caps,kind='registered')=>({id,scene,title:id,status:'ready',evidence:{source:{kind}},view:view(caps,{catalog:true,kind})});
test('总库去重跨工作区和跨场景的相同Motif，重复回执仅计一次',()=>{
  const pool=buildMotifPool([workspace('one',[cap('a','certified',[event])]),workspace('two',[cap('a','certified',[event])])],[runtime('ppt','ppt',[cap('a'),cap('b')])],{ready:true});
  assert.equal(pool.capabilities.length,2);assert.equal(pool.summary.applied,1);assert.equal(pool.capabilities[0].origins.length,3);assert.equal(pool.capabilities[0].reuses,1);
  assert.equal(pool.capabilities[0].tool_flow.length,1);
});
test('当前目录优先于历史工作区状态，账号学习来源优先于内置快照',()=>{
  const pool=buildMotifPool([workspace('one',[cap('a')])],[runtime('builtin','ppt',[cap('a','invalid')]),runtime('learned','ppt',[cap('a','pending_certification')],'account_learning')],{ready:true});
  assert.equal(pool.capabilities[0].status,'pending_certification');assert.equal(pool.capabilities[0].statusConflict,true);
});
test('同级同时间的状态冲突保守展示，不按数组顺序宣称已认证',()=>{
  const sources=[runtime('x','ppt',[cap('a')]),runtime('y','ppt',[cap('a','invalid')])];
  for(const rows of [sources,[...sources].reverse()])assert.equal(buildMotifPool([],rows,{ready:true}).capabilities[0].status,'invalid');
});
test('场景和来源筛选必须命中同一来源，不产生交叉误匹配',()=>{
  const pool=buildMotifPool([],[runtime('ppt','ppt',[cap('a')]),runtime('data','data',[cap('a'),cap('b')])],{ready:true});
  assert.equal(filterMotifPool(pool,{scene:'ppt',source:'data'}).capabilities.length,0);
  assert.equal(filterMotifPool(pool,{scene:'data',source:'data',query:'b'}).capabilities.length,1);
  assert.equal(pool.capabilities.length,2);
});
test('目录没有任务回执时复用未知，不能补零',()=>{
  const pool=buildMotifPool([],[runtime('ppt','ppt',[cap('a')])],{ready:true});
  assert.equal(pool.summary.applied,null);assert.equal(pool.capabilities[0].reuses,null);
  const mixed=buildMotifPool([workspace('one',[cap('b','certified',[event])])],[runtime('ppt','ppt',[cap('a')])],{ready:true});
  assert.equal(filterMotifPool(mixed,{scene:'ppt'}).summary.applied,null);
});
test('空成功响应可以为0，未加载或全部不可用保持未知',()=>{
  assert.equal(buildMotifPool([],[],{ready:true}).known,true);
  assert.equal(buildMotifPool([],[],{ready:false}).known,false);
  assert.equal(buildMotifPool([],[],{ready:true,partial:true}).known,false);
  const partial=buildMotifPool([],[runtime('ppt','ppt',[cap('a')]),{id:'missing',scene:'video',status:'unavailable'}],{ready:true});
  assert.equal(partial.known,true);assert.equal(partial.partial,true);assert.equal(partial.capabilities.length,1);
});
test('云端目录不可用时仍可读取本机结构认证及实际复用',()=>{
  const certificate='a'.repeat(64),id='motif-'+certificate.slice(0,24);
  const item={id,scene:'paper',certificate,tools:['local_document_pin','local_document_read'],witnesses:3,reuses:2};
  const pool=buildMotifPool([],[],{ready:true,partial:true,localCatalog:[item,{...item,tools:['arbitrary_command']}]});
  assert.equal(pool.known,true);
  assert.equal(pool.partial,true);
  assert.equal(pool.capabilities.length,1);
  assert.equal(pool.summary.applied,2);
  const [source]=pool.sources;
  assert.equal(source.kind,'local_learning');
  assert.equal(filterMotifPool(pool,{scene:'paper',source:source.id}).capabilities[0].id,'local:'+id);
  assert.equal(filterMotifPool(pool,{scene:'ppt',source:source.id}).capabilities.length,0);
});
