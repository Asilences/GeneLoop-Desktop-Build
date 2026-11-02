/** Trusted task runner / offline catalog. Never invokes a model. */
import {readFileSync} from 'node:fs';
import {buildSourceCapabilities,runSourceCapability} from '../src/adapters/source_capability_runtime.ts';
const flags=new Map();
for(let index=2;index<process.argv.length;index++){
 const key=process.argv[index];
 if(key==='--catalog')flags.set(key,true);
 else {if(!key.startsWith('--')||!process.argv[index+1])throw Error('source_cli_arguments_invalid');flags.set(key,process.argv[++index]);}
}
const json=key=>JSON.parse(readFileSync(flags.get(key),'utf8'));
const controller=new AbortController();
process.on('SIGINT',()=>controller.abort());process.on('SIGTERM',()=>controller.abort());
try{
 let result;
 if(flags.has('--catalog'))result=buildSourceCapabilities(readFileSync(flags.get('--library')),flags.get('--owner'));
 else result=await runSourceCapability(flags.get('--manifest'),json('--snapshot'),json('--args'),
  {root:flags.has('--root')?json('--root'):undefined,signal:controller.signal});
 process.stdout.write(JSON.stringify(result)+'\n');
 if(result.status&&result.status!=='succeeded')process.exitCode=1;
}catch(error){
 const reason=/^(source|capability|rsi)_[a-z_]+$/.test(error?.message??'')?error.message:'source_cli_failed';
 process.stdout.write(JSON.stringify({format:'source_capability_invocation_error_v1',status:'rejected',reason})+'\n');process.exitCode=1;
}
