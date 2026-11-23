import test from 'node:test';
import assert from 'node:assert/strict';
import {pptAssetBudget} from '../src/adapters/ppt/delivery/ppt_asset_budget.ts';
const task=()=>({status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},stats:{}});
test('asset hunting has a finite common fallback while local composition and source tools remain available',()=>{
 for(const mode of ['baseline','execute']){
  const t={...task(),request:{mode}};
  for(let i=0;i<8;i++)assert.equal(pptAssetBudget(t,{name:'web_fetch',callId:'url-'+i},1000),undefined);
  assert.match(pptAssetBudget(t,{name:'web_fetch',callId:'ninth'},1000),/基础稿/);
  assert.match(pptAssetBudget(t,{name:'web_fetch',callId:'ninth'},1000),/基础稿/,'Repeated guard evaluation must preserve a refusal');
  assert.equal(t.stats.ppt_external_asset_attempts,8);
  assert.equal(t.stats.ppt_asset_fallback,true);
  for(const name of ['read','read_image','compose_ppt_page','finalize_ppt','prepare_ppt_asset'])
   assert.equal(pptAssetBudget(t,{name},999999),undefined);
 }
});
test('a second long-delayed attempt and script retry loops cannot stall the deck',()=>{
 const t=task();pptAssetBudget(t,{name:'web_search',callId:'one'},1000);
 assert.match(pptAssetBudget(t,{name:'web_search',callId:'two'},92000),/收敛点/);
 assert.match(pptAssetBudget(task(),{name:'bash',arguments:{command:'python3 -c "import requests; for i in range(100): requests.get(url)"'}}),/批量爬虫/);
 assert.equal(pptAssetBudget(task(),{name:'bash',arguments:{command:'echo hello'}}),undefined);
});
