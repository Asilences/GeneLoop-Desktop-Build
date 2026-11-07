// No model, speech worker or network. Exercise the actual locked CLI seam.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const app=fileURLToPath(new URL('../',import.meta.url)),repo=resolve(app,'../..');
const bundle=resolve(process.env.GENELOOP_NATIVE_TOOLS??join(app,'desktop-tools-bundle'));
const python=join(bundle,process.platform==='win32'?'python/python.exe':'python/bin/geneloop-python');
const skill=join(bundle,'ppt-master'),entry=join(repo,'src/adapters/desktop_python_entry.py');
const blocked=['narration_sync','notes_to_audio','powerpoint_video','video_motion_plan','video_sound_mix','video_subtitles'];
for(const name of blocked){
  const path=join(skill,'scripts',name+'.py'),before=createHash('sha256').update(readFileSync(path)).digest('hex');
  const bootstrap='import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name="__main__")';
  const result=spawnSync(python,['-B','-X','utf8','-c',bootstrap,repo,entry,path],{
    env:{...process.env,GENELOOP_PPT_MASTER_ROOT:skill},encoding:'utf8',windowsHide:true});
  assert.notEqual(result.status,0);assert.match(result.stderr,/PPT.*制作和编辑演示文稿/);
  assert.equal(createHash('sha256').update(readFileSync(path)).digest('hex'),before);
}
for(const name of ['native-tools-requirements.txt','native-tools-constraints.txt'])
  assert.doesNotMatch(readFileSync(join(app,name),'utf8'),/^(?:torch|torchaudio|openai-whisper|stable-ts|edge-tts)(?:==|\s*$)/m);
const guide=readFileSync(join(app,'skills/geneloop-ppt/SKILL.md'),'utf8');
assert.match(guide,/不生成配音、视频或字幕/);assert.match(guide,/finalize_ppt/);
console.log(JSON.stringify({diagnostic:true,blockedPptExtensions:blocked,upstreamUnchanged:true,defaultSpeechDependencies:false,pptAuthoringGuide:true,modelRequests:0}));
