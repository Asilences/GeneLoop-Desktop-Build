import { readFileSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runTypedDecision } from '../src/adapters/typed_decisions.ts';
const root=dirname(dirname(fileURLToPath(import.meta.url)));process.chdir(root);
if(existsSync(join(root,'.env')))process.loadEnvFile(join(root,'.env'));
try {
 const v=JSON.parse(readFileSync(0,'utf8'));
 const meter=async event=>{
  const r=spawnSync(process.env.SSS_PYTHON??'python3',[join(root,'scripts/decision-meter.py')],
   {input:JSON.stringify({context_file:v.meter_context,event}),encoding:'utf8',env:process.env});
  if(r.status!==0)throw Error('account meter failed: '+r.stdout);
 };
 const result=await runTypedDecision(v.packet,{provider:v.provider,recordRoot:v.record_root,
  threshold:v.threshold,config:v.config,meter});
 console.log(JSON.stringify(result));
} catch(e) {console.error(e.name==='JevError'?e.message:'typed decision local failure');process.exitCode=1;}
