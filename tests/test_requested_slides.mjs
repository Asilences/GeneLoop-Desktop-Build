import test from 'node:test';
import assert from 'node:assert/strict';
import {requestedSlides,sceneOptions} from '../src/adapters/web/attachments/harless_task_scope.ts';
test('explicit slide count overrides the default without extracting ordinal citations',()=>{
  for(const text of ['制作3页，包含封面共3页','生成三页中文汇报','create 3 slides'])assert.equal(requestedSlides(text),3);
  assert.equal(requestedSlides('总结第3页文献'),6);
  assert.equal(requestedSlides('3页或5页，请先讨论'),6);
  assert.equal(requestedSlides('介绍研究'),6);
});

test('native PPT capacity accepts an existing 56-page deck before task submission',()=>{
 assert.equal(requestedSlides('生成56页PPT'),56);
 assert.equal(sceneOptions({slides:56,allow_output:true},{adapter:'ppt',ppt_execution_strategy:'ppt_master'}).slides,56);
 assert.throws(()=>sceneOptions({slides:201},{adapter:'ppt',ppt_execution_strategy:'ppt_master'}),/invalid_scene_options/);
});
