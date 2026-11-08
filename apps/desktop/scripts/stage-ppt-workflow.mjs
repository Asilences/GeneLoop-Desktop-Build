/** Stage the same certified executor used by the server into a desktop bundle. */
import {mkdirSync,readFileSync,writeFileSync,copyFileSync,existsSync,readdirSync} from 'node:fs';
import {join,dirname,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {stripTypeScriptTypes} from 'node:module';

export const pptWorkflowSourceFiles=['src/adapters/ppt_execution.ts','src/adapters/ppt_workflow_runtime.ts','src/adapters/ppt_write_runtime.ts','src/adapters/ppt_component_schema.ts',
    'src/motif_core/online_skill_runtime.mjs','src/motif_core/approved_plan_continuation.generated.mjs',
    'src/motif_core/source_dereference.generated.mjs','src/motif_core/LICENSE','src/motif_core/PROVENANCE.md'];

export function stagePptWorkflow(sourceRoot,destination){
  const entries=[];
  for(const name of pptWorkflowSourceFiles){
    const relative=name.slice(4).replace(/\.ts$/,'.mjs');
    const target=join(destination,'ppt-shared',relative);
    let bytes=readFileSync(join(sourceRoot,name));
    if(name.endsWith('.ts'))bytes=Buffer.from(stripTypeScriptTypes(bytes.toString('utf8'),{mode:'strip'})
      .replaceAll("'./ppt_execution.ts'","'./ppt_execution.mjs'")
      .replaceAll("'./ppt_write_runtime.ts'","'./ppt_write_runtime.mjs'")
      .replaceAll("'./ppt_component_schema.ts'","'./ppt_component_schema.mjs'"));
    mkdirSync(dirname(target),{recursive:true});
    if(existsSync(target)&&!readFileSync(target).equals(bytes))throw Error('preserve_existing_ppt_workflow_bundle');
    writeFileSync(target,bytes);
    entries.push({source:name,path:'ppt-shared/'+relative,sha256:createHash('sha256').update(bytes).digest('hex')});
  }
  const adapter='apps/desktop/runtime/local-ppt-workflow.mjs';
  copyFileSync(join(sourceRoot,adapter),join(destination,'local-ppt-workflow.mjs'));
  entries.push({source:adapter,path:'local-ppt-workflow.mjs',sha256:createHash('sha256').update(readFileSync(join(destination,'local-ppt-workflow.mjs'))).digest('hex')});
  // The native host may keep the same JSON schema while changing behavior.
  // Bind its already staged modules as well as the shared interpreter.
  for(const name of readdirSync(destination).filter(name=>name.endsWith('.mjs')).sort()){
    if(entries.some(row=>row.path===name))continue;
    entries.push({source:'desktop-native-host',path:name,sha256:createHash('sha256').update(readFileSync(join(destination,name))).digest('hex')});
  }
  writeFileSync(join(destination,'ppt-workflow-bundle.json'),JSON.stringify({version:1,files:entries},null,2));
  return entries;
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
  const root=fileURLToPath(new URL('../../../',import.meta.url));
  if(!process.argv[2])throw Error('a fresh desktop bundle destination is required');
  console.log(JSON.stringify({staged:stagePptWorkflow(root,resolve(process.argv[2])).length}));
}
