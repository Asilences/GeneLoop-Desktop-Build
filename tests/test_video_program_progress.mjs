import test from 'node:test';
import assert from 'node:assert/strict';
import {createTaskProgress,taskToolLabel} from '../src/adapters/harless_task_progress.ts';
test('video program reuse is visible without claiming a skipped model request',()=>{
 const progress=createTaskProgress();progress.audit({kind:'published_program_library_loaded'});progress.audit({kind:'video_program_reused'});
 const trace=progress.snapshot().trace;assert.equal(trace.length,2);assert.equal(trace[0].optimized,false);assert.equal(trace[1].optimized,true);assert.equal(trace[1].verified_skip,false);assert.match(trace[1].label,/视频程序/);
 assert.equal(taskToolLabel('mcp__remotion__reuse_cut_demo'),'复用视频程序并渲染');
});
