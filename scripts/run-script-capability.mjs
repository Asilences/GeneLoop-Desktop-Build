/** Explicit host invocation. No default chat hook, no model call. */
import {readFileSync} from 'node:fs';
import {buildScriptCapabilities,runScriptCapability} from '../src/adapters/script_capability_runtime.ts';
const flags=new Map();
for(let i=2;i<process.argv.length;i++){const key=process.argv[i];flags.set(key,key==='--catalog'?true:process.argv[++i]);}
const json=key=>JSON.parse(readFileSync(flags.get(key),'utf8'));
const controller=new AbortController();process.on('SIGINT',()=>controller.abort());process.on('SIGTERM',()=>controller.abort());
try{
 const result=flags.has('--catalog')?buildScriptCapabilities(flags.get('--library'),flags.get('--owner')):
  await runScriptCapability(flags.get('--manifest'),json('--snapshot'),json('--args'),{signal:controller.signal});
 process.stdout.write(JSON.stringify(result)+'\n');if(result.status&&result.status!=='succeeded')process.exitCode=1;
}catch(error){process.stdout.write(JSON.stringify({status:'rejected',reason:error.message})+'\n');process.exitCode=1;}
