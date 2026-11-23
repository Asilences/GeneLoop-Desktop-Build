/** Optional native deck bundle. Called by desktop packaging, never at runtime. */
import {mkdirSync,readFileSync,writeFileSync,copyFileSync,cpSync,existsSync} from 'node:fs';
import {join,dirname,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {stripTypeScriptTypes} from 'node:module';
import {createHash} from 'node:crypto';
export function stagePptDeck(sourceRoot,destination){
 const root=join(destination,'ppt-deck');
 if(existsSync(root))throw Error('preserve_existing_ppt_deck_bundle');
 const source=join(sourceRoot,'scenarios/ppt_master/third_party/dsh-ppt');
 const provenance=JSON.parse(readFileSync(join(source,'PROVENANCE.json'),'utf8'));
 for(const [name,expected] of Object.entries(provenance.adapted_sha256)){
  if(createHash('sha256').update(readFileSync(join(source,name))).digest('hex')!==expected)throw Error('ppt_deck_vendor_changed');
 }
 const lock=JSON.parse(readFileSync(join(source,'package-lock.json'),'utf8'));
 const dependencies=existsSync(join(source,'node_modules/@office-kit/pptx/package.json'))?join(source,'node_modules'):join(sourceRoot,'node_modules');
 for(const name of ['@office-kit/pptx','fflate']){
  const expected=lock.packages['node_modules/'+name].version;
  if(JSON.parse(readFileSync(join(dependencies,name,'package.json'),'utf8')).version!==expected)throw Error('ppt_deck_dependency_not_staged');
 }
 mkdirSync(root,{recursive:true});
 for(const name of ['ppt_deck_engine','ppt_deck_contract']){
  const target=join(root,'src/adapters/ppt/authoring',name+'.mjs');mkdirSync(dirname(target),{recursive:true});
  writeFileSync(target,stripTypeScriptTypes(readFileSync(join(sourceRoot,'src/adapters/ppt/authoring',name+'.ts'),'utf8'),{mode:'strip'})
   .replaceAll("'./ppt_deck_contract.ts'","'./ppt_deck_contract.mjs'"));
 }
 const target=join(root,'scenarios/ppt_master/third_party/dsh-ppt');mkdirSync(target,{recursive:true});
 for(const name of [...Object.keys(provenance.adapted_sha256),'PROVENANCE.json','LICENSE','package.json','package-lock.json'])copyFileSync(join(source,name),join(target,name));
 // Only the two locked pure-JS runtime packages, never the upstream plugin or updater.
 for(const name of ['@office-kit/pptx','fflate'])cpSync(join(dependencies,name),join(target,'node_modules',name),{recursive:true});
 copyFileSync(join(sourceRoot,'apps/desktop/runtime/local-ppt-deck.mjs'),join(destination,'local-ppt-deck.mjs'));
 return {engine_commit:provenance.commit,resident_services:0,dependencies:['@office-kit/pptx','fflate'],root};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
 if(!process.argv[2])throw Error('fresh desktop bundle destination required');
 console.log(JSON.stringify(stagePptDeck(fileURLToPath(new URL('../../../',import.meta.url)),resolve(process.argv[2]))));
}
