// Actual copied application and its native resources. No model calls.
import assert from 'node:assert/strict';
import {existsSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const resources=resolve(process.argv[2]),output=resolve(process.argv[3]);mkdirSync(output,{recursive:true});
const runtime=join(resources,'geneloop-runtime.asar'),tools=join(resources,'geneloop-tools');
assert.equal(existsSync(join(resources,'tool-packs.json')),false);
const manifest=JSON.parse(readFileSync(join(tools,'manifest.json'),'utf8'));
assert.equal(manifest.platform,process.platform);assert.equal(manifest.arch,process.arch);assert.equal(manifest.profile.scope,'six-scenes-ppt-authoring');
assert.equal(existsSync(join(tools,'speech')),false);assert.ok(existsSync(join(tools,'skills/geneloop-ppt/SKILL.md')));
const req=createRequire(pathToFileURL(join(runtime,'local-worker.mjs')));
const env={...process.env,ELECTRON_RUN_AS_NODE:'1',GENELOOP_NATIVE_RUNTIME:runtime,GENELOOP_NATIVE_TOOLS:tools,
 GENELOOP_NATIVE_SOURCE_ROOT:join(tools,'source'),GENELOOP_OFFICE_NODE:process.execPath,PYTHONDONTWRITEBYTECODE:'1'};
const results=[];
for(const [name,file,args]of [['core','check-native-workflows.mjs',['--core']],['ppt','check-native-ppt.mjs',[]],['video','check-native-remotion.mjs',[]]]){
 const source=readFileSync(join('scripts',file),'utf8').replace(/from '(@deepseek-ai\/[^']+|pptxgenjs|sharp)'/g,(_,name)=>'from '+JSON.stringify(pathToFileURL(req.resolve(name)).href));
 const script=join(output,'installed-'+file);writeFileSync(script,source);
 const start=performance.now(),run=spawnSync(process.execPath,[script,...args],{env,encoding:'utf8',windowsHide:true,timeout:240000});
 writeFileSync(join(output,name+'.log'),run.stdout+run.stderr);
 results.push({name,exit:run.status,seconds:(performance.now()-start)/1000,error:run.error?.message??null});
 writeFileSync(join(output,'summary.json'),JSON.stringify({at:new Date().toISOString(),version:JSON.parse(readFileSync(join(resources,'app.asar/package.json'))).version,
  platform:process.platform,arch:process.arch,distribution:'complete',installedResources:resources,postInstallToolPreparation:false,modelRequests:0,results},null,2)+'\n');
 assert.equal(run.status,0,name+': '+run.stdout+run.stderr);console.log(JSON.stringify(results.at(-1)));
}
