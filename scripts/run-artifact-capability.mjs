/** Host-owned CLI for native Artifact catalog and public Capability execution. */
import {readFileSync} from 'node:fs';
import {buildArtifactCapabilities,runArtifactCapability} from '../src/adapters/artifact_capability_runtime.ts';
const args=process.argv.slice(2);
try{
 if(args[0]==='--catalog'){
  process.stdout.write(JSON.stringify(buildArtifactCapabilities(args[1],args[2],args[3])));
 }else{
  const [manifest,snapshot,input]=args;
  const controller=new AbortController();
  process.on('SIGINT',()=>controller.abort());process.on('SIGTERM',()=>controller.abort());
  const value=await runArtifactCapability(manifest,JSON.parse(readFileSync(snapshot,'utf8')),
   JSON.parse(readFileSync(input,'utf8')),{signal:controller.signal});
  process.stdout.write(JSON.stringify(value));
  if(value.status!=='succeeded')process.exitCode=1;
 }
}catch(error){console.error(error.message);process.exitCode=1;}
