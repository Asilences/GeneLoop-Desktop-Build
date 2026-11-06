// Fixed Node programs used by the unchanged Python PPT service. They resolve
// production dependencies from ASAR. The on-disk copies exist for the Python
// checkpoint's original version guard, and must match the executed bytes.
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
const [script,...args]=process.argv.slice(2);
if(!['render.js','layout-policy-cli.js','guard-cli.js'].includes(script))throw Error('Unknown native PPT program');
const target=new URL('./research-ppt/'+script,import.meta.url);
const expected=join(process.env.GENELOOP_PPT_SOURCE_ROOT,'scenarios/research_ppt/dist',script);
const sha=data=>createHash('sha256').update(data).digest('hex');
if(sha(readFileSync(target))!==sha(readFileSync(expected)))throw Error('PPT program version changed');
process.argv=[process.execPath,fileURLToPath(target),...args];
await import(target.href);
