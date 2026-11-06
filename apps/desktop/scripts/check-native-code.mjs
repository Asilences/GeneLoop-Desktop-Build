import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync,realpathSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {runNativeCode} from '../runtime/local-code.mjs';
const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-code-'))),text='Local WASM input';
mkdirSync(join(root,'inputs'));writeFileSync(join(root,'inputs/source.txt'),text);
writeFileSync(join(root,'approved-inputs.json'),JSON.stringify({files:{'source.txt':createHash('sha256').update(text).digest('hex')}}));
try {
  const result=await runNativeCode({workspace:root,allow_output:true,program:
    'const a = await inputs.read_text({name:"source.txt"}); await outputs.write_text({name:"result.txt",text:a.text}); return {node:typeof process,require:typeof require,text:a.text};'});
  assert.equal(result.result.value.node,'undefined');assert.equal(result.result.value.require,'undefined');
  assert.equal(result.result.value.text,text);assert.equal(result.artifacts.length,1);
  await assert.rejects(runNativeCode({workspace:root,allow_output:true,program:'await inputs.read_text({name:"../outside"});'}));
  await assert.rejects(runNativeCode({workspace:root,allow_output:true,program:'await outputs.write_text({name:"../outside.txt",text:"refused"});'}));
  await assert.rejects(runNativeCode({workspace:root,allow_output:true,program:'await import("node:fs");'}));
  await assert.rejects(runNativeCode({workspace:root,allow_output:false,program:'await outputs.write_text({name:"refused.txt",text:"refused"});'}));
  console.log(JSON.stringify({runtime:'quickjs-wasm',actualExecution:true,hostApisAbsent:true,inputScope:true,outputScope:true,moduleDenied:true,readOnly:true,modelRequests:0}));
} finally {assert.equal(dirname(root),realpathSync(tmpdir()));rmSync(root,{recursive:true,force:true});}
