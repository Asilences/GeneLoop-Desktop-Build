// Completes a staged tool bundle on the target operating system. Build hosts
// download dependencies; installed applications do not install them on demand.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {prepareNativeExtras} from './prepare-native-extras.mjs';
const app=fileURLToPath(new URL('../',import.meta.url)),bundle=join(app,'desktop-tools-bundle');
const python=join(bundle,process.platform==='win32'?'python/python.exe':'python/bin/geneloop-python');
prepareNativeExtras(python,bundle);
const result=spawnSync(python,['-B',join(app,'scripts/prepare-native-speech.py'),join(bundle,'speech')],{stdio:'inherit',env:process.env});
assert.equal(result.status,0,'随包字幕组件构建失败，不能发布为完整工具版');
