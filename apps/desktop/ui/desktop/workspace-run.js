import {node,button,icon} from './components.js';

const states={queued:'等待执行',preparing:'正在准备',running:'运行中',completed:'已完成',failed:'执行失败',cancelled:'已停止'};
const short=value=>value?value.slice(0,10)+'…':'未提供';
const finite=value=>typeof value==='number'&&Number.isFinite(value);
const active=task=>['queued','preparing','running'].includes(task?.status);
const money=value=>finite(value)?'$'+value.toFixed(4):'—';
const duration=task=>finite(task?.duration_ms)&&task.started_at?(task.duration_ms/1000).toFixed(task.duration_ms<10000?1:0)+'s':'—';
const panelTitle=(symbol,title,...extra)=>node('div',{class:'run-section-title'},node('h3',{},icon(symbol),title),...extra);
const hint=text=>node('p',{class:'run-empty-note'},text);
const chip=(text,tone=0)=>node('span',{class:'run-motif-chip tone-'+tone,title:text},text);

/** 仅展示原任务接口公开的计划/轨迹及工作区证据，不合成阶段、收益或执行能力。 */
export function workspaceRunView({workspace,model,viewState,onTab,onTask}){
  const tasks=workspace.tasks||[],task=tasks.find(row=>row.task_id===viewState.taskId)||tasks.find(active)||tasks[0]||null;
  const trace=Array.isArray(task?.trace)?task.trace:[];
  const used=trace.filter(row=>row.kind==='motif'&&row.status==='completed'&&(row.verified_skip===true||row.optimized===true));
  const labels=[...new Set(used.map(row=>row.label).filter(value=>typeof value==='string'))];
  const plan=Array.isArray(task?.todos)?task.todos.filter(row=>typeof row.content==='string'&&['pending','in_progress','completed'].includes(row.status)):[];
  const completed=plan.filter(row=>row.status==='completed').length;
  const sessionId=task?.session_id||workspace.nextSession?.sessionId;
  const taskTitle=task?.input_summary||workspace.nextSession?.title||'从一个新的研究任务开始';
  const status=task?(states[task.status]||'状态未提供'):workspace.nextSession?.running?'对话运行中':'暂无任务回执';
  const statusNode=()=>node('span',{class:'run-task-status '+(active(task)?'running':task?.status||'idle'),title:task?.progress?.label||status},node('i',{}),status);
  const motifBadges=()=>node('div',{class:'run-motif-badges'},labels.length?labels.map((label,i)=>chip(label,i%4)):node('span',{class:'run-muted'},'尚无已核验的 Motif 调用回执'));
  function disclosure(title,content,key,cls=''){
    const details=node('details',{class:'run-disclosure '+cls,open:viewState[key]!==false},node('summary',{},title,icon('chevron-down')),content);
    details.querySelector('summary').addEventListener('click',event=>{event.preventDefault();viewState[key]=!details.open;details.open=viewState[key];});return details;
  }
  const taskBody=node('div',{class:'run-task-body'});
  if(plan.length){
    const steps=node('ol',{class:'run-plan'});
    for(const step of plan)steps.append(node('li',{class:step.status},node('span',{class:'run-step-mark'},step.status==='completed'?icon('check'):null),node('span',{},step.content)));
    const progress=node('progress',{max:plan.length,value:completed,'aria-label':'公开计划已完成项'});
    taskBody.append(steps,node('div',{class:'run-plan-progress'},progress,node('span',{},completed+'/'+plan.length+' 项计划')));
  }else taskBody.append(hint(task?'任务尚未提供公开计划步骤。':'发送指令后，这里会显示实际任务和公开计划。'));
  const actions=node('div',{class:'run-task-actions'});
  if(sessionId)actions.append(button(['打开对话',icon('chevron-right')],()=>workspace.openSession(sessionId),'run-text-action'));
  if(workspace.previewDelivery&&workspace.resourceSession===sessionId)actions.append(button('查看交付',workspace.previewDelivery,'run-text-action'));
  if(tasks.length>1){const picker=node('select',{'aria-label':'查看任务'});for(const row of tasks)picker.append(node('option',{value:row.task_id},row.input_summary||row.task_id));picker.value=task.task_id;picker.addEventListener('change',()=>onTask(picker.value));actions.prepend(picker);}
  taskBody.append(actions);
  const taskCard=node('details',{class:'run-task-card','aria-label':'当前任务',open:viewState.planOpen!==false},
    node('summary',{class:'run-task-card-header'},node('span',{class:'run-task-emblem '+(active(task)?'running':'')},icon(task?.status==='completed'?'check':active(task)?'refresh':'document')),
      node('div',{class:'run-task-heading'},node('h3',{title:taskTitle},taskTitle),node('div',{class:'run-task-subline'},node('span',{},'Motif 回执'),motifBadges())),statusNode(),icon('chevron-down')),
    node('div',{class:'run-task-plan'},taskBody));
  taskCard.querySelector('summary').addEventListener('click',event=>{event.preventDefault();viewState.planOpen=!taskCard.open;taskCard.open=viewState.planOpen;});

  const output=node('div',{class:'run-output-log'}),visibleTrace=trace.filter(row=>['tool','motif','request'].includes(row.kind)).slice(-7);
  if(visibleTrace.length)visibleTrace.forEach((row,i)=>output.append(node('div',{class:'run-output-line'},node('span',{class:'run-line-number'},String(i+1)),node('span',{class:'run-line-state '+row.status},icon(row.status==='completed'?'check':row.status==='failed'?'close':'refresh')),node('span',{},row.label||row.tool||'任务记录'))));
  else if(model?.raw.events.length){output.append(node('p',{class:'run-output-scope'},'工作区 Motif 回执 · 未绑定为当前对话的执行步骤'));
    model.raw.events.slice(-5).forEach((event,i)=>{const cap=model.capabilities.find(row=>row.id===event.capability_id);output.append(node('div',{class:'run-output-line'},node('span',{class:'run-line-number'},String(i+1)),icon(event.kind==='fallback'?'refresh':'scenes'),node('span',{},({invoke:'执行回执',match:'匹配记录',fallback:'回退记录'})[event.kind]+' · '+cap.name)));});
  }else output.append(hint('任务执行后，真实工具记录会显示在这里。'));
  const outputBlock=node('section',{class:'run-section'},panelTitle('trace','实时输出',node('span',{class:'run-section-caption'},task?'来自当前任务':'工作区记录')),output);
  const context=node('div',{class:'run-context'},node('p',{},task?.input_summary||'从下方输入框描述研究目标，沿用当前工作区开始对话。'));
  if(task?.scene)context.append(node('span',{class:'run-context-tag'},'场景 · '+(workspace.sceneLabel?.(task.scene)||task.scene)));
  const contextBlock=disclosure(node('span',{class:'run-disclosure-title'},icon('document'),'计划与上下文'),context,'contextOpen');
  const benefit=(symbol,label,value,note)=>node('div',{class:'run-benefit'},icon(symbol),node('div',{},node('span',{},label),node('strong',{},value),node('small',{},note)));
  const benefits=node('section',{class:'run-section'},panelTitle('like','实际用量'),node('div',{class:'run-benefit-grid'},
    benefit('document','输入 Tokens',task?.stats?.input_tokens??task?.stats?.prompt_tokens??'—','原任务记录'),
    benefit('chart-column-increasing','输出 Tokens',task?.stats?.output_tokens??task?.stats?.completion_tokens??'—','原任务记录'),
    benefit('scenes','模型请求',finite(task?.stats?.model_requests)?task.stats.model_requests:'—','原任务用量')));
  const recent=workspace.sessionCount?disclosure('最近对话 · '+workspace.sessionCount,workspace.recent,'recentOpen','run-recent-conversations'):workspace.recent;
  const main=node('div',{class:'workspace-run-surface'},taskCard,outputBlock,contextBlock,benefits,recent);
  if(workspace.taskError)main.prepend(node('p',{class:'motif-error',role:'alert'},workspace.taskError));

  const info=(symbol,label,value,cls='')=>node('div',{class:'inspector-info-row'},node('span',{},icon(symbol),label),node('strong',{class:cls},value));
  const section=(symbol,title,...children)=>node('section',{class:'inspector-section'},node('h3',{},icon(symbol),title),...children);
  const inspectTask=node('div',{class:'inspector-current-task'},node('span',{class:'inspector-kicker'},'当前任务'),node('div',{},icon('document'),node('strong',{},task?taskTitle:workspace.nextSession?'尚无任务回执 · '+workspace.nextSession.title:'尚未开始任务')));
  const use=section('scenes','Motif 调用回执',motifBadges());
  const runtime=section('monitor','运行信息',info('refresh','状态',statusNode()),info('trace','已用时间',duration(task)),
    info('document','输入 Tokens',task?.stats?.input_tokens??task?.stats?.prompt_tokens??'—'),info('chart-column-increasing','输出 Tokens',task?.stats?.output_tokens??task?.stats?.completion_tokens??'—'),info('scenes','任务估费',money(task?.stats?.cost_usd)),hint('原任务用量；收益须经过同质量对照后确认。'));
  const statistic=(symbol,label,value)=>node('div',{class:'inspector-stat'},icon(symbol),node('div',{},node('small',{},label),node('strong',{},value)));
  const evolution=section('refresh','库内记录',node('div',{class:'inspector-stat-grid'},statistic('scenes','Motif 数量',model?model.capabilities.length:'—'),statistic('refresh','实际复用回执',model&&!model.raw.source?model.summary.applied:'—')),hint(model?.raw.source?'所选场景库，未作为当前工作区已使用能力统计。':'只统计当前证据源的实际回执。'));
  const route=(symbol,label,tab)=>button([icon(symbol),node('span',{},label),icon('chevron-right')],()=>onTab(tab),'inspector-route');
  const options=section('settings','证据视图',route('refresh','查看调用与回退记录','evolution'),route('scenes','查看当前能力与工具流','combination'),route('document','查看版本与认证','versions'),route('chart-column-increasing','核对任务用量','evaluation'));
  const resourceFiles=(workspace.resources||[]).filter(file=>workspace.resourceTask===task?.task_id||workspace.resourceSession===sessionId);
  const resources=section('files','相关资源');
  if(resourceFiles.length){resources.append(node('span',{class:'inspector-kicker'},workspace.resourceTask===task?.task_id?'任务交付':'此对话的交付'));
    for(const file of resourceFiles.slice(0,3))resources.append(node('a',{class:'inspector-resource',href:file.href,download:file.name,title:file.name},icon('document'),node('span',{},file.name),icon('download')));
    if(resourceFiles.length>3)resources.append(hint('共 '+resourceFiles.length+' 项交付，请在对话中查看全部。'));
  }else resources.append(hint('尚无已验证的任务交付。'));
  if(model)resources.append(route('scenes','能力来源与认证','versions'));
  const inspector=node('div',{class:'workspace-inspector-card'},node('header',{class:'workspace-inspector-header'},icon('monitor'),node('h2',{},'GeneLoop 工作区'),node('span',{title:workspace.title},workspace.title)),inspectTask,use,runtime,evolution,options,resources);
  return {main,inspector};
}
