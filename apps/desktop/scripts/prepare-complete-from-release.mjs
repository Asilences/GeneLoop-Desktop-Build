// Reuse the accepted six-scene packs and add the current required privacy component.
import assert from 'node:assert/strict';
import {appendFileSync,constants,cpSync,mkdirSync,mkdtempSync,readFileSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {ToolPackStore,validateToolCatalog} from '../dist/tool-pack-store.js';
import {prepareInstallerCodec} from './prepare-installer-codec.mjs';
import {refreshCompleteSource} from './refresh-complete-source.mjs';
import {execFileSync} from 'node:child_process';
assert.equal(process.env.GITHUB_REPOSITORY,'Asilences/GeneLoop-Desktop-Build');
assert.equal(process.platform,'darwin');assert.ok(['arm64','x64'].includes(process.arch));
const app=process.cwd(),input=resolve('complete-tool-inputs/darwin-'+process.arch+'.json');
const catalog=validateToolCatalog(JSON.parse(readFileSync(input,'utf8')));
assert.equal(catalog.platform,process.platform);assert.equal(catalog.arch,process.arch);
assert.deepEqual(catalog.packages.map(p=>p.id),['workspace','python','office','browser','media','converters']);
assert.equal(catalog.baseUrl,'https://github.com/Asilences/GeneLoop-Desktop-Build/releases/download/desktop-tools-darwin-'+process.arch+'-'+catalog.toolsetId.slice(0,24)+'/');
const codecDirectory=resolve('.local/complete-codec'),codec=await prepareInstallerCodec(app,codecDirectory);
assert.equal(codec.sha256,catalog.codec.sha256);
const home=resolve('.local/complete-tools');mkdirSync(home,{recursive:true});
let last='';const start=performance.now();
const store=new ToolPackStore(catalog,{home,codecDirectory,change(){const state=JSON.stringify(store.state().rows.map(r=>[r.id,r.phase]));if(last!==state){last=state;console.log(state);}}});
await store.prepare();assert.equal(store.state().ready,true);
execFileSync('npm',['ci','--ignore-scripts','--prefix','../../scenarios/ppt_master/third_party/dsh-ppt'],{stdio:'inherit'});
// Keep the verified install reusable if this build is interrupted or retried.
const staging=mkdtempSync(join(home,'build-'));
const tools=join(staging,'tools');
cpSync(store.tools,tools,{recursive:true,verbatimSymlinks:true,mode:constants.COPYFILE_FICLONE});
const rosterPath=join(staging,'complete-source-roster.json'),roster=await refreshCompleteSource(tools,rosterPath,{preparePrivacy:true});
const record={at:new Date().toISOString(),platform:process.platform,arch:process.arch,toolsetId:roster.toolsetId,sourceInputToolset:catalog.toolsetId,
  tools,packages:catalog.packages.length,files:roster.files.length,
  bytes:roster.files.reduce((n,f)=>n+f.bytes,0),publicSourceRefreshed:true,nativeToolsUnchanged:true,privacyToolsStaged:true,seconds:(performance.now()-start)/1000,verified:true,modelRequests:0};
writeFileSync('.local/complete-tool-import.json',JSON.stringify(record,null,2)+'\n');
assert.ok(process.env.GITHUB_ENV);appendFileSync(process.env.GITHUB_ENV,'GENELOOP_DESKTOP_TOOLS_STAGE='+tools+'\nGENELOOP_COMPLETE_TOOL_CATALOG='+rosterPath+'\n');
console.log(JSON.stringify(record));
