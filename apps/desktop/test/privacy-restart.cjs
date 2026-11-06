const {app}=require('electron'),assert=require('node:assert/strict');
const {readFileSync,writeFileSync}=require('node:fs'),{join,resolve}=require('node:path'),{pathToFileURL}=require('node:url');
const fixture=JSON.parse(readFileSync(process.env.GENELOOP_RENDERER_FIXTURE,'utf8'));
assert.equal(fixture.diagnostic,true);assert.equal(fixture.privacy,true);
app.setPath('userData',join(fixture.output,'profile'));app.disableHardwareAcceleration();
let desktop;
const report={kind:'desktop-privacy-restart',ok:false,real_model_requests:0};
async function until(fn){const deadline=Date.now()+15000;while(Date.now()<deadline){if(await fn())return;await new Promise(done=>setTimeout(done,50));}throw Error('restart UI timeout');}
app.whenReady().then(async()=>{
 const {DesktopWorkspace}=await import(pathToFileURL(resolve(__dirname,'../dist/workspace.js')).href);
 desktop=new DesktopWorkspace({settings:{version:1,server:fixture.server,window:{width:1280,height:860,maximized:false}},
  settingsFile:join(fixture.output,'settings.json'),version:'privacy-restart-diagnostic',downloadsDirectory:fixture.output,allowLoopback:true});
 await desktop.ready;desktop.workspace.webContents.setBackgroundThrottling(false);
 const evaluate=code=>desktop.workspace.webContents.executeJavaScript(code);
 await until(()=>evaluate(`!document.getElementById('workspace').hidden`));
 await evaluate(`document.getElementById('account-nav').click();document.querySelector('[data-action=account-settings]').click();document.querySelector('[data-page="privacy"]').click()`);
 await until(()=>evaluate(`!!document.querySelector('[data-privacy-preview]')`));
 assert.equal(await evaluate(`!!document.querySelector('[data-privacy-consent]')`),false);
 assert.equal(await evaluate(`!!document.querySelector('[data-privacy-payload]')`),false);
 report.ok=true;
}).catch(error=>{report.error=error.message;}).finally(()=>{
 writeFileSync(join(fixture.output,'privacy-restart-summary.json'),JSON.stringify(report));
 desktop?.permitClose();app.quit();
});
