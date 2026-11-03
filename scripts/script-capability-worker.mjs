/** Fixed bridge to the existing sandbox. This worker never accepts a runner path. */
import {runCertifiedScript} from './run-certified-script.mjs';
import {scriptWorkerFailure,SCRIPT_FAILURE_FRAME} from '../src/adapters/script_worker_failure.mjs';
let raw='';
for await(const chunk of process.stdin){raw+=chunk;if(Buffer.byteLength(raw)>1_000_000)throw Error('script_job_too_large');}
try{process.stdout.write(JSON.stringify(runCertifiedScript(JSON.parse(raw))));}
catch(error){process.stderr.write(SCRIPT_FAILURE_FRAME+JSON.stringify(scriptWorkerFailure(error))+'\n');process.exitCode=1;}
