/** Fixed bridge to the existing sandbox. This worker never accepts a runner path. */
import {runCertifiedScript} from './run-certified-script.mjs';
let raw='';
for await(const chunk of process.stdin){raw+=chunk;if(Buffer.byteLength(raw)>1_000_000)throw Error('script_job_too_large');}
try{process.stdout.write(JSON.stringify(runCertifiedScript(JSON.parse(raw))));}
catch{process.stderr.write('script_native_execution_failed\n');process.exitCode=1;}
