import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,mkdtempSync,writeFileSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import Ajv2020 from 'ajv/dist/2020.js';
import {runtimeMotifEvidence,registerMotifCatalog} from '../src/adapters/harless_motif_catalog.ts';
import {evidenceView} from '../src/adapters/motif_evidence_projection.ts';
import {loadedProductMotifScenes} from './helpers/product_motif_scenes.mjs';
const scenes=loadedProductMotifScenes();
const ajv=new Ajv2020({allowUnionTypes:true});
const check=ajv.compile(JSON.parse(readFileSync(new URL('../config/motif-evidence-v2.schema.json',import.meta.url))));

test('原加载器准入的实际 Paper/PPT/Data 库可直接投影，费用未知且旧库不伪造认证',()=>{
  const original=scenes.map(s=>readFileSync(s.runtime_library));
  const projected=scenes.map(s=>runtimeMotifEvidence(s,()=>null));
  assert.deepEqual(projected.map(e=>e.capabilities.length),[2,1,10]);
  for(const [i,data]of projected.entries()){
    const view=evidenceView(data,check);
    assert.equal(data.execution_authorized,false);assert.equal(data.display_only,true);
    assert.equal(view.summary.savings,null);assert.equal(view.runs.length,0);assert.equal(view.summary.applied,0);
    assert.ok(view.capabilities.every(c=>c.cost==='未知'&&c.toolFlow.length>0));
    assert.equal(JSON.stringify(data).includes(scenes[i].runtime_library),false,'不导出物理路径');
    assert.deepEqual(readFileSync(scenes[i].runtime_library),original[i],'展示不写原件');
    assert.equal(runtimeMotifEvidence(scenes[i],()=>null).export_digest,data.export_digest,'轮询时间不改变内容修订');
  }
  assert.equal(evidenceView(projected[0],check).summary.certified,2);
  assert.ok(projected[0].source.revisions.some(row=>!row.current),'原学习报告提供兼容来源版本');
  assert.equal(projected[0].source.revisions.filter(row=>row.current).length,1);
  assert.equal(evidenceView(projected[2],check).summary.certified,0);
  assert.equal(evidenceView(projected[2],check).summary.registered,10);
});

test('原宿主的代码或权限拒绝结果使展示失效，不自行重新认证',()=>{
  const data=runtimeMotifEvidence(scenes[0],()=> 'runtime_bundle_certification_invalid');
  assert.equal(evidenceView(data,check).summary.invalid,2);
  assert.equal(data.source.compatibility,'unavailable');
  assert.ok(data.capabilities.every(c=>c.version.certificate_digest!==null),'保留原证书引用而非伪造新证书');
  assert.equal(data.library.certified_count,0);
});

test('读取实际库后字节变化失败关闭，账号学习来源与共享注册库分开',()=>{
  const temp=realpathSync(mkdtempSync(join(realpathSync(tmpdir()),'motif-runtime-')));
  try{
    const path=join(temp,'library.json');writeFileSync(path,'{}');
    assert.throws(()=>runtimeMotifEvidence({...scenes[0],runtime_library:path},()=>null),/changed/);
    const data=runtimeMotifEvidence({...scenes[0],learning_version:'round-0001'},()=>null);
    assert.equal(data.source.kind,'account_learning');assert.equal(data.source.release,'round-0001');
  }finally{rmSync(temp,{recursive:true,force:true});}
});

test('Runtime目录使用既有账号认证，不接收账号和文件路径，不跨宿主混合账号库',async()=>{
  function host(rows){let route;const ctx={effect:fn=>fn(),connection:{requestRejection:req=>req.headers.has('x-test-auth')?undefined:401,fetch:{register:value=>{route=value;return()=>{};}}}};
    registerMotifCatalog(ctx,{scenes:()=>rows,unavailable:()=>null});return route;}
  const route=host(scenes),url='https://fixture.example/api/harless/motif-catalog';
  assert.equal((await route.fetch(new Request(url))).status,401);
  assert.equal((await route.fetch(new Request(url+'?path=private',{headers:{'x-test-auth':'1'}}))).status,400);
  const response=await route.fetch(new Request(url,{headers:{'x-test-auth':'1'}}));
  assert.equal(response.headers.get('cache-control'),'no-store');
  assert.equal((await response.json()).libraries.length,3);
  const isolated=await host([scenes[1]]).fetch(new Request(url,{headers:{'x-test-auth':'1'}}));
  assert.deepEqual((await isolated.json()).libraries.map(r=>r.scene),['paper-proofreading']);
});
