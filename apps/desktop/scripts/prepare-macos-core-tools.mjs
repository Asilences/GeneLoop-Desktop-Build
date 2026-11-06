// Incremental CI check of changed native MCP/QuickJS/OCR dependencies.
// It deliberately does not claim Office/media packaging acceptance.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdirSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {stageWorkflowSource} from './stage-workflow-source.mjs';
import {stageOcrData} from './stage-ocr-data.mjs';
import {installNativePythonDeps} from './native-python-deps.mjs';
assert.equal(process.platform,'darwin');
const app=resolve('.'),bundle=join(app,'desktop-tools-bundle');
function run(exe,args){const r=spawnSync(exe,args,{stdio:'inherit'});assert.equal(r.status,0,'native core dependency preparation failed');}
mkdirSync(bundle,{recursive:true});
run('python3',['-m','venv',join(bundle,'python')]);
const python=join(bundle,'python/bin/python3');
installNativePythonDeps(python,app);
writeFileSync(join(bundle,'python/bin/geneloop-python'),'#!/bin/sh\nexec "${0%/*}/python3" "$@"\n',{mode:0o755});
stageWorkflowSource(resolve(app,'../..'),join(bundle,'source'));
stageOcrData(join(app,'.local','ocr-data'),join(bundle,'ocr'));
console.log(JSON.stringify({native_core:true,arch:process.arch,office_packaged:false,media_packaged:false}));
