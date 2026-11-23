import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,linkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pptOutputPackagingPlan,executePptOutputPackaging} from '../src/adapters/ppt/delivery/ppt_output_packaging.ts';

test('host packaging accepts the observed output-only sequence and rejects scripts, source writes and arbitrary redirection',()=>{
 const command='cp /work/outputs/source.png /work/outputs/detail.png && ls -la /work/outputs/*.png 2>/dev/null; echo "---"; ls -la /work/outputs/export/';
 assert.equal(pptOutputPackagingPlan(command).length,4);
 for(const bad of ['cp /work/outputs/a /work/projects/deck/a; ls /work/outputs/a',
  'ls /work/outputs/*.png > /work/projects/deck/a','ls /work/outputs/*.png 2>/work/outputs/log',
  'cp /work/outputs/a /work/outputs/b; python -c "pass"','echo $(rm -rf /work)',
  'cp /work/outputs/a /work/outputs/b || touch /tmp/x','ls /work/outputs/*/*.png',
  'cp /work/inputs/a /work/outputs/b','ls /work/outputs/../projects/a','echo "---"; bash',
  'cp /work/outputs/a /work/outputs/name:stream'])assert.equal(pptOutputPackagingPlan(bad),null,bad);
});

test('host packaging uses local file APIs, honors cancellation and fails on a missing mount without looping',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-host-package-')),signal=new AbortController();
 const plan=pptOutputPackagingPlan('mkdir -p /work/outputs/final && cp /work/outputs/a.pptx /work/outputs/final/a.pptx; ls -la /work/outputs/final');
 assert.throws(()=>executePptOutputPackaging({workspace},plan,signal.signal));
 mkdirSync(join(workspace,'outputs/code'),{recursive:true});writeFileSync(join(workspace,'outputs/code/a.pptx'),'deck');
 assert.match(executePptOutputPackaging({workspace},plan,signal.signal),/final\/a.pptx/);
 assert.equal(readFileSync(join(workspace,'outputs/code/final/a.pptx'),'utf8'),'deck');
 signal.abort();assert.throws(()=>executePptOutputPackaging({workspace},plan,signal.signal));
});

test('host packaging rejects linked destinations before overwriting another file',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-host-linked-'));
 mkdirSync(join(workspace,'outputs/code'),{recursive:true});
 writeFileSync(join(workspace,'outputs/code/source.png'),'source');writeFileSync(join(workspace,'outside'),'untouched');
 linkSync(join(workspace,'outside'),join(workspace,'outputs/code/alias.png'));
 const plan=pptOutputPackagingPlan('cp /work/outputs/source.png /work/outputs/alias.png; echo "---"');
 assert.throws(()=>executePptOutputPackaging({workspace},plan,new AbortController().signal));
 assert.equal(readFileSync(join(workspace,'outside'),'utf8'),'untouched');
});
