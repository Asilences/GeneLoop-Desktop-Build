import {artifactJobArgv} from './artifact_motif_transport.ts';
import GeneLoopShell from './geneloop_shell.ts';
import {artifactInvocation} from './artifact_motif_runtime.ts';
import {resolveExecutionAgent} from './geneloop_delegation.ts';
export default class ArtifactMotifShell extends GeneLoopShell {
 resolve(request:any):any{
  const agent=resolveExecutionAgent(this.ctx),job=agent&&artifactInvocation(agent.session.id,request.command,request.workdir);
  const spec=super.resolve(request);
  if(job)spec.artifactJob=job;
  return spec;
 }
 run(spec:any){
  if(!spec.artifactJob)return super.run(spec);
  // Use the native executor lifecycle for cancellation and stdout delivery.
  // The child is a trusted interpreter of a private versioned library, not shell text.
  const argv=artifactJobArgv(spec.artifactJob,resolveExecutionAgent(this.ctx).session.id);
  return this.runArgv(spec,argv);
 }
 start(spec:any){if(spec.artifactJob)throw Error('artifact_background_execution_requires_foreground_receipt');return super.start(spec);}
}
