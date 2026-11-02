/** Private JSON protocol used by existing MCP scenes; never executes source. */
import {readFileSync} from 'node:fs';
import {decodeSourceLibrary,materializeSource,sourceCatalog,sourceProgramVersion,loadSourceForm,selectSourcePrograms} from '../src/adapters/source_program_runtime.ts';
try{
 const input=JSON.parse(readFileSync(0,'utf8'));
 if(input.operation==='resolve_form'){
  process.stdout.write(JSON.stringify(loadSourceForm(input.store,input.owner)));
 }else if(input.operation==='candidate_materialize'){
  process.stdout.write(JSON.stringify(materializeSource(input.program,input.parameters)));
 }else{
  // Old callers may still provide library:path. Task-pinned callers send their
  // captured bytes. All checks and materialization consume this one decode.
  const raw=input.library_base64===undefined?readFileSync(input.library):Buffer.from(input.library_base64,'base64');
  const {library,library_sha256}=decodeSourceLibrary(raw,{
   library_sha256:input.expected_library_sha256,library_digest:input.expected_library_digest});
  const programs=selectSourcePrograms(library,input.intent??'',input.library_scope??'all');
  if(input.operation==='catalog'){
   process.stdout.write(JSON.stringify({digest:library.digest,library_sha256,
    program_versions:programs.map(p=>sourceProgramVersion(library,library_sha256,p)),
    programs:sourceCatalog({programs},input.include_source===true)}));
  }else{
   const program=programs.find(p=>p.id===input.program_id);
   if(!program)throw Error('source_program_unknown');
   const version=sourceProgramVersion(library,library_sha256,program);
   if(input.expected_program_version!==undefined){
    const expected=input.expected_program_version;
    if(!expected||Object.keys(expected).length!==Object.keys(version).length||
       Object.keys(version).some(key=>expected[key]!==version[key]))throw Error('source_program_version_changed');
   }
   process.stdout.write(JSON.stringify({...materializeSource(program,input.parameters,input.parameter_binding??'full'),
    library_digest:library.digest,source_program_version:version,phase:'materialized'}));
  }
 }
}catch(error){
 // Schema/parser errors can include user text. Only fixed diagnostic codes cross
 // the stdio error boundary; source and supplied parameters are never echoed.
 const reason=typeof error?.message==='string'&&/^source_[a-z_]+$/.test(error.message)?error.message:'source_program_bridge_rejected';
 process.stderr.write(reason);process.exitCode=1;
}
