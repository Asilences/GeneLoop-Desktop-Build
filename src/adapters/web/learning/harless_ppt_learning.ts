/** Account-local PPT learning; the existing task runner remains the only model loop. */
import {spawn} from 'node:child_process';
import {createHash,randomUUID} from 'node:crypto';
import {appendFileSync,existsSync,lstatSync,mkdirSync,readFileSync,realpathSync,renameSync,writeFileSync} from 'node:fs';
import {dirname,isAbsolute,join,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import type {Scene} from '../account/harless_settings.ts';
import {qualityStatus} from '../../../rsi/feedback/rsi_quality.ts';
import {verifyPptStateBinding} from '../../ppt/learning/ppt_learning_evidence.ts';
import {privateSourceLocks} from './private_source_locks.ts';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..');
const hash=(bytes:any)=>createHash('sha256').update(bytes).digest('hex');
const read=(path:string)=>JSON.parse(readFileSync(path,'utf8'));
const inside=(parent:string,path:string)=>{const rel=relative(parent,path);return rel!==''&&!rel.startsWith('..')&&!isAbsolute(rel);};
function checked(parent:string,path:string){
  const full=resolve(path),stat=lstatSync(full);
  if(!inside(parent,full)||realpathSync(full)!==full||stat.isSymbolicLink()||!stat.isFile()||stat.nlink!==1)throw Error('ppt_learning_path_invalid');
  return full;
}
function write(path:string,value:any){const tmp=path+'.'+randomUUID()+'.tmp';writeFileSync(tmp,JSON.stringify(value),{mode:0o600,flag:'wx'});renameSync(tmp,path);}
function evidence(output:string,name:string,version:unknown,message:string){
 const path=checked(output,join(output,name));if(hash(readFileSync(path))!==version)throw Error(message);verifyPptStateBinding(output,path);
}
/** Normal task learning remains enabled; model scoring is an internal opt-in. */
export function pptLearningPolicies(env:NodeJS.ProcessEnv=process.env){
  return {learning:env.GENELOOP_PPT_COMPONENT_LEARNING_POLICY??env.SSS_WEB_POLICY,
    review:env.GENELOOP_PPT_REVIEW_POLICY};
}
export function createPptLearning(config:{output:string;user:string;scope:string;python?:string;resources?:any;taskIds:()=>string[];
  control?:{allowed:()=>boolean;signal:()=>AbortSignal}}){
  const output=realpathSync(config.output),store=join(output,'learning','ppt-'+hash(config.user+'\0'+config.scope));
  let running:Promise<void>|undefined,again=false;
  let reviewRunning:Promise<void>|undefined,reviewAgain=false;
  let reviewTimer:ReturnType<typeof setTimeout>|undefined;
  const enabled=Boolean(config.python);
  function ensure(){mkdirSync(store,{recursive:true,mode:0o700});if(realpathSync(store)!==store)throw Error('ppt_learning_store_redirected');}
  function status(value:any){try{ensure();write(join(store,'status.json'),value);}catch{}}
  async function run(mode:'learning'|'review'='learning'){
    if(config.control && !config.control.allowed())return;
    const taskIds=config.taskIds();
    if(config.control && !taskIds.length)return;
    const requestName=mode==='review'?'review-request.json':'request.json';
    ensure();write(join(store,requestName),{schema_version:1,output,user:config.user,scope:config.scope,task_ids:taskIds,
      automatic_structural_learning:true,command_resources:config.resources??{},worker_mode:mode});
    const {learning:configuredLearningPolicy,review:reviewPolicy}=pptLearningPolicies();
    const learningPolicy=config.control?undefined:configuredLearningPolicy;
    await new Promise<void>((done,fail)=>{
      const env:any={PATH:process.env.PATH,SSS_PYTHON:config.python,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'};
      if(config.resources?.pptMasterRoot==='/opt/geneloop/ppt-master')env.GENELOOP_PPT_MASTER_ROOT=config.resources.pptMasterRoot;
      // Preserve the configured Python runtime without inheriting arbitrary application secrets.
      for(const name of ['SYSTEMROOT','WINDIR','TMP','TEMP','TMPDIR','PYTHONPATH','HOME','USERPROFILE','APPDATA','LOCALAPPDATA',
        'GENELOOP_COMMAND_SOCKET','GENELOOP_PPT_CAPABILITY_PLAN'])if(process.env[name])env[name]=process.env[name];
      const selectedPolicy=mode==='learning'?learningPolicy:reviewPolicy;
      if(selectedPolicy){
        if(mode==='learning')env.GENELOOP_PPT_COMPONENT_LEARNING_POLICY=selectedPolicy;
        else env.GENELOOP_PPT_REVIEW_POLICY=selectedPolicy;
        if(process.env.DEEPSEEK_API_KEY)env.DEEPSEEK_API_KEY=process.env.DEEPSEEK_API_KEY;
      }
      const child=spawn(config.python!,[join(root,'scripts/learn-web-ppt-tasks.py'),'--request',join(store,requestName)],
        {cwd:root,env,stdio:['ignore','pipe','pipe'],signal:config.control?.signal(),windowsHide:true});
      let log='';child.stdout.on('data',b=>{if(log.length<128000)log+=String(b);});child.stderr.on('data',b=>{if(log.length<128000)log+=String(b);});
      const timer=setTimeout(()=>child.kill(),env.GENELOOP_PPT_COMPONENT_LEARNING_POLICY||env.GENELOOP_PPT_REVIEW_POLICY?900000:120000);child.on('error',error=>{clearTimeout(timer);fail(error);});
      child.on('close',code=>{clearTimeout(timer);try{write(join(store,mode==='review'?'review-worker-log.json':'worker-log.json'),{code,log,mode});code===0?done():fail(Error(mode==='review'?'ppt_background_review_failed':'ppt_learning_compiler_failed'));}catch(error){fail(error);}});
    });
    const queuePath=join(store,'background-review-queue.json');
    if(mode==='review'&&reviewPolicy&&existsSync(queuePath)){
      const queue=read(checked(store,queuePath));
      if(queue.pending_count>0&&Number.isFinite(queue.next_at)){
        const delay=Math.max(0,queue.next_at*1000-Date.now());
        if(delay===0)reviewAgain=true;
        else{clearTimeout(reviewTimer);reviewTimer=setTimeout(()=>manager.scheduleReview(),delay);reviewTimer.unref();}
      }
    }
  }
  const manager={
    workflow(){
      const folder=join(store,'workflows'),path=join(folder,'selected.json');
      if(!enabled||!existsSync(path)||existsSync(join(folder,'suspended.json'))||existsSync(join(store,'suspended.json')))return null;
      try{
        const pointer=read(checked(store,path));
        if(pointer.user!==config.user||pointer.scope!==config.scope||!['probation','active'].includes(pointer.phase)||
          (pointer.feedback_version??null)!==(existsSync(join(store,'feedback-version.json'))?hash(readFileSync(checked(store,join(store,'feedback-version.json')))):null)||
          typeof pointer.library!=='string'||!(/^[a-f0-9]{64}\.json$/).test(pointer.library)||
          !Object.keys(pointer.evidence_locks??{}).length)return null;
        for(const [name,version] of Object.entries(pointer.evidence_locks))evidence(output,name,version,'ppt_workflow_evidence_changed');
        const library=checked(store,join(folder,pointer.library));
        if(hash(readFileSync(library))!==pointer.sha256)return null;
        return read(library);
      }catch{return null;}
    },
    captureSingle(task:any,artifacts:any[]){
      if(!enabled||config.control&&!config.control.allowed()||task.scene?.id!=='ppt'||task.scene.ppt_execution_strategy!=='ppt_master'||task.status!=='completed')return;
      const id=task.request.task_id,session=task.request.session_id,mode=task.request.mode;
      if(!/^[a-f0-9]{32}$/.test(id)||!['baseline','execute'].includes(mode)||typeof session!=='string'||!session||
        resolve(task.output)!==join(output,'tasks',id))throw Error('ppt_single_identity_invalid');
      ensure();
      // Capture at the owning completion boundary, before another message can
      // edit the workspace. The worker never reconstructs an old mutable draft.
      const body={schema_version:1,kind:'ppt_single_delivery_v1',user:config.user,scope:config.scope,
        task_id:id,session_id:session,mode,status:task.status,snapshot_turn:'native-'+id,snapshot_lane:'baseline',
        artifacts,output_sha256:hash(JSON.stringify(artifacts))};
      const path=join(task.output,'ppt-learning-delivery.json');
      if(existsSync(path)){
        if(JSON.stringify(read(checked(output,path)))!==JSON.stringify(body))throw Error('ppt_single_delivery_changed');
      }else write(path,body);
    },
    program(){
      if(!enabled||!existsSync(join(store,'program-selected.json'))||existsSync(join(store,'program-suspended.json')))return null;
      try{
        const pointer=read(checked(store,join(store,'program-selected.json')));
        if(pointer.user!==config.user||pointer.scope!==config.scope||!['probation','active'].includes(pointer.phase)||
          (pointer.feedback_version??null)!==(existsSync(join(store,'feedback-version.json'))?hash(readFileSync(checked(store,join(store,'feedback-version.json')))):null))return null;
        if(!Object.keys(pointer.evidence_locks??{}).length)throw Error('ppt_program_evidence_missing');
        for(const [name,version] of Object.entries(pointer.evidence_locks))evidence(output,name,version,'ppt_program_evidence_changed');
        const library=checked(store,join(store,pointer.library));
        if(hash(readFileSync(library))!==pointer.library_sha256)throw Error('ppt_program_library_changed');
        if(pointer.phase==='active'){
          const path=checked(store,join(dirname(library),'evaluation.json'));
          if(hash(readFileSync(path))!==pointer.evaluation_sha256)throw Error('ppt_program_evaluation_changed');
          const evaluation=read(path),pairs=evaluation.pairs??[];
          if(pairs.length<2||new Set(pairs.map((p:any)=>p.comparison_id)).size!==pairs.length)throw Error('ppt_program_independent_pairs_missing');
          for(const pair of pairs){
            const b=pair.attempts?.baseline?.proxy_usd,o=pair.attempts?.motif?.proxy_usd;
            if(!Number.isFinite(b)||!Number.isFinite(o)||o<0||o>=b||pair.program_reuses<1)throw Error('ppt_program_cost_regression');
            for(const lane of ['baseline','motif']){
              const proof=pair.quality_records?.[lane];
              if(!proof||pair.evidence_locks?.[proof.record]!==proof.sha256)throw Error('ppt_program_quality_missing');
              const record=read(checked(output,join(output,proof.record)));
              if(qualityStatus(record,proof.binding,proof.mechanical_checks)!=='passed')throw Error('ppt_program_quality_failed');
              if(pointer.quality_cost_promoted===true&&qualityStatus(record,proof.binding,proof.required_checks)!=='passed')throw Error('ppt_program_quality_unknown');
            }
          }
        }
        let publicCapabilities:any=null;
        const publicPath=join(store,'capability','selected.json');
        if(existsSync(publicPath)){
          try{
            const value=read(checked(store,publicPath));
            if(value.owner!==config.user||value.scope!==config.scope||value.native_library_sha256!==pointer.library_sha256||
               value.native_library_digest!==pointer.library_digest)throw Error('ppt_public_capability_scope_changed');
            const snapshot=checked(store,value.snapshot.path);
            if(hash(readFileSync(snapshot))!==value.snapshot.sha256)throw Error('ppt_public_capability_snapshot_changed');
            for(const ref of value.evidence){
              const path=checked(output,ref.path);
              if(hash(readFileSync(path))!==ref.sha256)throw Error('ppt_public_capability_evidence_changed');
              verifyPptStateBinding(output,path);
            }
            publicCapabilities=value;
          }catch{/* Native certified programs remain available when public adoption fails. */}
        }
        return {...pointer,library,public_capabilities:publicCapabilities};
      }catch{return null;}
    },
    deliveryFontRules(){
      const path=join(store,'delivery-font-rules.json');
      if(!enabled||!existsSync(path)||existsSync(join(store,'suspended.json')))return [];
      try{
        const value=read(checked(store,path));
        if(value.version!==1||!Array.isArray(value.rules)||value.rules.length>16)throw Error('font_rules_invalid');
        return value.rules.filter((rule:any)=>{
          if(rule.operation!=='font_family_only_v1'||rule.requires_allow_font_fallback!==true||!['probation','active'].includes(rule.phase)||
            typeof rule.from_family!=='string'||typeof rule.to_family!=='string'||rule.from_family.length>512||rule.to_family.length>512||
            /[;:{}<>\r\n\\]/.test(rule.from_family+rule.to_family)||
            !Object.keys(rule.evidence_locks??{}).length)throw Error('font_rule_invalid');
          for(const [name,version] of Object.entries(rule.evidence_locks))evidence(output,name,version,'font_rule_evidence_changed');
          if(rule.phase==='active'&&(!Array.isArray(rule.independent_validations)||rule.independent_validations.length<2||
             new Set(rule.independent_validations.map((row:any)=>row.task_id)).size!==rule.independent_validations.length||
             new Set(rule.independent_validations.map((row:any)=>row.source_signature)).size!==rule.independent_validations.length))throw Error('font_rule_independent_validation_missing');
          return true;
        });
      }catch{return [];}
    },
    scheduleReview(){
      if(!enabled||config.control&&!config.control.allowed()||process.env.GENELOOP_PPT_LEARNING_READONLY==='1'||!pptLearningPolicies().review)return;
      clearTimeout(reviewTimer);reviewAgain=true;if(reviewRunning)return;
      reviewRunning=(async()=>{while(reviewAgain){reviewAgain=false;try{await run('review');}catch(error){
        try{ensure();write(join(store,'review-worker-status.json'),{status:'failed',reason:(error as Error).message});}catch{}
      }}})().finally(()=>{reviewRunning=undefined;});
    },
    schedule(){
      if(!enabled||config.control&&!config.control.allowed()||process.env.GENELOOP_PPT_LEARNING_READONLY==='1')return;
      manager.scheduleReview();again=true;if(running)return;running=(async()=>{while(again){again=false;try{await run('learning');}catch(error){
      status({status:'failed',reason:(error as Error).message});
      // A worker outage does not revoke a previously certified capability.
      // Explicit negative feedback and current evidence guards still do.
    }}})().finally(()=>{running=undefined;});},
    async idle(){await Promise.all([running,reviewRunning]);},
    negativeFeedback(snapshot:any){if(enabled&&snapshot?.scene==='ppt'){
      ensure();write(join(store,'suspended.json'),{reason:'negative_feedback'});
      write(join(store,'feedback-version.json'),{version:randomUUID()});manager.schedule();
    }},
    review(snapshot:any,body:any){
      if(!enabled||config.control&&!config.control.allowed())throw Error('ppt_learning_unavailable');
      const lane=snapshot?.lanes?.[body.lane],quality=body.quality;
      if(snapshot?.scene!=='ppt'||!['baseline','motif'].includes(body.lane)||!lane||lane.status!=='completed'||
        !lane.output_sha256||lane.output_sha256!==body.output_sha256||!lane.artifacts?.some((a:any)=>/\.pptx$/i.test(a.name)))throw Error('ppt_learning_review_version_changed');
      if(typeof body.allow_learning!=='boolean'||!quality||Object.keys(quality).sort().join(',')!=='scientific,usable,visual'||
        Object.values(quality).some(v=>typeof v!=='boolean')||typeof body.human_minutes!=='number'||!Number.isFinite(body.human_minutes)||body.human_minutes<0||body.human_minutes>100000)
        throw Error('ppt_learning_review_invalid');
      ensure();const journal=join(store,'reviews.jsonl');if(existsSync(journal))checked(store,journal);
      // Suspend before recording a withdrawal/negative review: the next task
      // cannot race the background worker and inherit revoked evidence.
      const veto=!body.allow_learning||Object.values(quality).includes(false);
      if(veto)write(join(store,'suspended.json'),{reason:'review_changed'});
      const event={schema_version:1,id:randomUUID(),user:config.user,scope:config.scope,comparison_id:snapshot.id,lane:body.lane,
        output_sha256:lane.output_sha256,quality,allow_learning:body.allow_learning,human_minutes:body.human_minutes,at:new Date().toISOString()};
      appendFileSync(journal,JSON.stringify(event)+'\n',{mode:0o600});
      // Change the generation after persisting the veto. An older worker can
      // never re-enable its stale snapshot even if it finishes concurrently.
      if(veto)write(join(store,'feedback-version.json'),{version:randomUUID()});
      manager.schedule();return {recorded:true,learning_allowed:body.allow_learning};
    },
    resolve(scene:Scene):Scene{
      if(!enabled||scene.id!=='ppt'||scene.ppt_execution_strategy!=='ppt_master'||!existsSync(join(store,'selected.json'))||existsSync(join(store,'suspended.json')))return scene;
      try{
        const pointer=read(checked(store,join(store,'selected.json')));
        const feedback=join(store,'feedback-version.json');
        if((pointer.feedback_version??null)!==(existsSync(feedback)?hash(readFileSync(checked(store,feedback))):null))throw Error('ppt_learning_feedback_changed');
        if(pointer.user!==config.user||pointer.scope!==config.scope||!/^round-[0-9]{4,}$/.test(pointer.round)||!['probation','active'].includes(pointer.phase))throw Error('ppt_learning_pointer_invalid');
        const folder=join(store,pointer.round),path=checked(folder,join(folder,'admission.json'));
        if(hash(readFileSync(path))!==pointer.admission_sha256)throw Error('ppt_learning_admission_changed');
        const admission=read(path),bundle=join(folder,'release'),info=admission.runtime;
        if(admission.user!==config.user||admission.scope!==config.scope)throw Error('ppt_learning_owner_changed');
        for(const [name,version] of Object.entries(admission.evidence_locks??{}))evidence(output,name,version,'ppt_learning_evidence_changed');
        if(!Object.keys(admission.evidence_locks??{}).length)throw Error('ppt_learning_evidence_missing');
        if(pointer.phase==='active'){
          const promoted=checked(folder,join(folder,'promotion.json'));
          if(hash(readFileSync(promoted))!==pointer.promotion_sha256)throw Error('ppt_learning_promotion_changed');
          const promotion=read(promoted);
          if(promotion.round!==pointer.round||hash(readFileSync(checked(folder,join(folder,'evaluation.json'))))!==promotion.evaluation_sha256||!Object.keys(promotion.evidence_locks??{}).length)throw Error('ppt_learning_evaluation_changed');
          for(const [name,version] of Object.entries(promotion.evidence_locks))evidence(output,name,version,'ppt_learning_evaluation_changed');
          const evaluation=read(join(folder,'evaluation.json'));
          for(const pair of evaluation.pairs??[])for(const lane of ['baseline','motif']){
            const proof=pair.quality_records?.[lane];
            if(!proof||pair.evidence_locks?.[proof.record]!==proof.sha256)throw Error('ppt_learning_quality_missing');
            const record=read(checked(output,join(output,proof.record)));
            if(qualityStatus(record,proof.binding,proof.mechanical_checks)!=='passed'||
              qualityStatus(record,proof.binding,proof.required_checks)!==proof.status)throw Error('ppt_learning_quality_changed');
            if(pointer.quality_cost_promoted===true&&proof.status!=='passed')throw Error('ppt_learning_quality_unknown');
          }
        }
        const entry=read(checked(bundle,join(bundle,'entry.json'))),cert=read(checked(bundle,join(bundle,'certification.json')));
        if(entry.runtime_kind!=='ppt_master_v2'||entry.scene!=='ppt'||entry.mode!=='execute'||cert.binding_policy!=='ppt_master_sources_v1'||cert.matching_policy!=='structural_only'||cert.certification_scope!=='independent_trace_structure')throw Error('ppt_learning_kind_invalid');
        const required=['library.json','online-manifest.json','task.json','tool-schemas.json','certification.json','source-evidence.json','learning-report.json'];
        if(required.some(name=>!(/^[a-f0-9]{64}$/.test(entry.files?.[name]??''))))throw Error('ppt_learning_files_missing');
        for(const [name,version] of Object.entries(entry.files)){
          if(name.includes('/')||name.includes('\\')||hash(readFileSync(checked(bundle,join(bundle,name))))!==version)throw Error('ppt_learning_release_changed');
        }
        for(const name of required.filter(n=>n!=='certification.json'))if(cert.file_locks?.[name]!==entry.files[name])throw Error('ppt_learning_file_lock_changed');
        if(!Object.keys(cert.code_locks??{}).length)throw Error('ppt_learning_code_missing');
        const locks=privateSourceLocks(root,cert.code_locks,'ppt',checked,'ppt_learning_code_changed');
        const descriptorLocks=JSON.stringify(info.certified_code_locks);
        const paths={runtime_library:'library.json',manifest:'online-manifest.json',task:'task.json',tool_schemas:'tool-schemas.json',certification_path:'certification.json'};
        for(const [key,name] of Object.entries(paths))if(info[key]!==join(bundle,name))throw Error('ppt_learning_descriptor_changed');
        if(info.runtime_kind!=='ppt_master_v2'||info.runtime_mode!=='execute'||info.runtime_library_sha256!==entry.files['library.json']||info.certification_sha256!==hash(readFileSync(join(bundle,'certification.json')))||
          info.certified_tool_schemas_sha256!==entry.files['tool-schemas.json']||JSON.stringify(info.certified_tool_schemas)!==JSON.stringify(read(join(bundle,'tool-schemas.json')))||
          ![locks.original,locks.current].some(lock=>JSON.stringify(lock)===descriptorLocks)||info.binding_policy!==cert.binding_policy||info.matching_policy!==cert.matching_policy||info.certification_scope!==cert.certification_scope||info.quality_cost_promoted!==false)throw Error('ppt_learning_descriptor_changed');
        const {rsi_unavailable_reason,...base}=scene;
        return {...base,...info,certified_code_locks:locks.current,learning_version:pointer.round,learning_phase:pointer.phase,config_sha256:hash(JSON.stringify([scene.config_sha256,pointer.admission_sha256,pointer.phase]))};
      }catch(error){status({status:'rejected',reason:(error as Error).message});return scene;}
    },
  };
  return manager;
}
