/** Optional desktop integration seam. Native host owns permissions/Office/publication.
 * No child service, Python, network access, package install or model invocation here.
 */
export function createLocalPptDeckTools(host){
 if(!host?.projectRoot||!host?.imagePath||!host?.theme||!host?.render||!host?.authorize)throw Error('ppt_deck_native_host_required');
 let modules;
 const load=()=>modules??=Promise.all([import('./ppt-deck/src/adapters/ppt/authoring/ppt_deck_engine.mjs'),import('./ppt-deck/src/adapters/ppt/authoring/ppt_deck_contract.mjs')])
  .catch(error=>{modules=undefined;throw error;});
 const execute=async(args,execution,build)=>{
  host.authorize(execution);
  execution.signal?.throwIfAborted();
  const [engine]=await load();
  const root=host.projectRoot(build?args.name:args.project,build);
  const shared={root,imagePath:path=>host.imagePath(path),signal:execution.signal};
  const result=build?await engine.buildPptDeck({...shared,plan:args.plan,theme:host.theme(args.plan?.theme??'general'),
   fontFamily:host.fontFamily??(process.platform==='darwin'?'PingFang SC':process.platform==='win32'?'Microsoft YaHei':'Noto Sans CJK SC')}):
   await engine.patchPptDeck({...shared,expected_revision:args.expected_revision,edits:args.edits,append_slides:args.append_slides});
  if(result.status==='rejected')return result;
  host.authorize(execution);execution.signal?.throwIfAborted();
  const before=JSON.stringify(engine.readPptDeck(root));
  const delivery=await host.render({root,revision:result.revision,slide_count:result.slide_count,signal:execution.signal});
  host.authorize(execution);execution.signal?.throwIfAborted();
  if(JSON.stringify(engine.readPptDeck(root))!==before)throw Error('ppt_deck_changed_during_native_render');
  return {...result,...delivery};
 };
 return {async definitions(){return (await load())[1];},build:(args,execution)=>execute(args,execution,true),patch:(args,execution)=>execute(args,execution,false)};
}
