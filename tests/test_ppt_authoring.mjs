import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,symlinkSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {recordPptNativeAuthoring,pptNativeAuthoringGuard,releasePptNativeAuthoring} from '../src/adapters/ppt/authoring/ppt_authoring.ts';

function fixture(mode='baseline'){
 const workspace=mkdtempSync(join(tmpdir(),'ppt-authoring-'));
 mkdirSync(join(workspace,'code/projects/deck/svg_output'),{recursive:true});
 writeFileSync(join(workspace,'code/projects/deck/svg_output/slide_01.svg'),'first successful page');
 return {workspace,status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},request:{mode},scene_options:{allow_output:true}};
}
const call=(name,args)=>({name,arguments:args});
test('adopted native pages remain owned across task restart in both arms',()=>{
 for(const mode of ['baseline','execute']){
  const task=fixture(mode),file=join(task.workspace,'code/projects/deck/svg_output/slide_01.svg');
  assert.equal(pptNativeAuthoringGuard(task,call('bash',{command:'python3 /tmp/build_pages.py'})),undefined);
  recordPptNativeAuthoring(task,'/work/projects/deck','slide_01.svg','a'.repeat(64));
  for(const path of ['/work/projects/deck/svg_output/slide_01.svg',file,'projects/deck/svg_output/slide_01.svg'])
   assert.match(pptNativeAuthoringGuard({...task},call('write',{file_path:path})),/当前SHA/);
  assert.match(pptNativeAuthoringGuard(task,call('bash',{command:'cd /tmp && python3 build_pages.py 2>&1'})),/批量重建/);
  assert.equal(readFileSync(file,'utf8'),'first successful page');
  assert.equal(pptNativeAuthoringGuard(task,call('compose_ppt_page',{project:'/work/projects/deck',expected_page_sha256:'a'.repeat(64)})),undefined);
  assert.equal(pptNativeAuthoringGuard(task,call('write',{file_path:'/work/projects/deck/svg_output/special_02.svg'})),undefined);
  for(const name of ['prepare_ppt','finalize_ppt','present','read','grep','inspect_ppt_region'])
   assert.equal(pptNativeAuthoringGuard(task,call(name,{})),undefined);
  assert.equal(pptNativeAuthoringGuard(task,call('bash',{command:'ls -la /work/projects/deck'})),undefined);
  assert.equal(pptNativeAuthoringGuard(task,call('bash',{command:'echo hello'})),undefined);
  assert.equal(pptNativeAuthoringGuard(task,call('bash',{command:'cat /work/projects/deck/design_spec.md'})),undefined);
  assert.equal(pptNativeAuthoringGuard(task,call('bash',{command:'head -n 40 /work/projects/deck/spec_lock.md'})),undefined);
  assert.equal(pptNativeAuthoringGuard(task,call('bash',{command:'ls -la /work/projects/deck/svg_output/ /work/projects/deck/images/'})),undefined);
  assert.match(pptNativeAuthoringGuard(task,call('bash',{command:'ls /work/projects/deck/../other/'})),/当前SHA/);
  assert.match(pptNativeAuthoringGuard(task,call('bash',{command:'ls /work/projects/deck/; python3 /tmp/build_pages.py'})),/当前SHA/);
 }
});
test('an explicitly admitted program fallback also releases native policy and keeps pages',()=>{
 const task=fixture('execute'),path=join(task.workspace,'code/projects/deck/svg_output/slide_01.svg');
 recordPptNativeAuthoring(task,'/work/projects/deck','slide_01.svg','c'.repeat(64));
 releasePptNativeAuthoring(task,'/work/projects/deck');
 assert.equal(readFileSync(path,'utf8'),'first successful page');
 assert.equal(pptNativeAuthoringGuard(task,call('write',{file_path:'/work/projects/deck/svg_output/slide_01.svg'})),undefined);
});
test('native authoring markers reject redirection and do not affect other scenes',()=>{
 const task=fixture();recordPptNativeAuthoring(task,'/work/projects/deck','slide_01.svg','b'.repeat(64));
 assert.match(pptNativeAuthoringGuard(task,call('edit',{file_path:'/work/projects/deck/validation/native-authoring.json'})),/当前SHA/);
 const command='cp /work/outputs/page.png /tmp/preview.png';
 assert.equal(pptNativeAuthoringGuard(task,call('bash',{command})),undefined);
 if(process.platform!=='win32'){
  mkdirSync(join(task.workspace,'command-tmp'),{recursive:true});
  symlinkSync(join(task.workspace,'code/projects/deck/svg_output/slide_01.svg'),join(task.workspace,'command-tmp/preview.png'));
  assert.match(pptNativeAuthoringGuard(task,call('bash',{command})),/当前SHA/);
 }
 assert.equal(pptNativeAuthoringGuard({...task,scene:{id:'chat'}},call('bash',{command:'python3 /tmp/build_pages.py'})),undefined);
});
