/** Integrated theme discovery and project setup for ordinary presentation tasks. */
import {existsSync,lstatSync,mkdirSync,readFileSync,realpathSync,renameSync,rmSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {digest} from '../../../motif_core/runtime/online_skill_runtime.mjs';
import {appendFileSync} from 'node:fs';
import {recordPptNativeAuthoring,pptNativeAuthoringGuard} from './ppt_authoring.ts';
import {pptDeckLayouts,pptDeckLanguages} from './ppt_deck_contract.ts';

const themesUrl = new URL('../../../../scenarios/ppt_master/themes.json', import.meta.url);
export function pptSkillReferences() {
  const registry=JSON.parse(readFileSync(new URL('../../../../scenarios/ppt_master/skill-sources.json',import.meta.url),'utf8'));
  if(registry.version!==1||registry.kind!=='reviewed_ppt_skill_sources'||!Array.isArray(registry.sources))throw Error('ppt_skill_corpus_version_invalid');
  const seen=new Set();
  return registry.sources.map((source:any)=>{
    if(!/^[a-z0-9-]{1,80}$/.test(source.id)||seen.has(source.id)||!['MIT','Apache-2.0'].includes(source.license)||
      !/^[a-f0-9]{40}$/.test(source.commit)||!/^[a-f0-9]{64}$/.test(source.upstream_sha256)||
      !/^scenarios\/ppt_master\/skill_sources\/[a-z0-9-]+\.md$/.test(source.adapted_path))throw Error('ppt_skill_corpus_source_invalid');
    seen.add(source.id);
    const path=new URL('../../../../'+source.adapted_path,import.meta.url);
    if(lstatSync(path).isSymbolicLink())throw Error('ppt_skill_corpus_path_invalid');
    const text=readFileSync(path,'utf8');
    return {id:source.id,adapted:true,text,sha256:createHash('sha256').update(text).digest('hex'),
      upstream_commit:source.commit,executable:false};
  });
}
export function pptThemes() {
  return JSON.parse(readFileSync(themesUrl, 'utf8'));
}

export const pptDesignTool = {
  name: 'read_ppt_design',
  description: '查看通用PPT主题卡及分别适用于build_ppt、compose_ppt_page的页型。build_ppt只需theme ID，不必再读完整配色和字体。可按category筛选，或用theme读取完整主题。component_ids按需读取本任务已认证组件契约。',
  parameters: {
    type: 'object',
    properties: {category: {type: 'string'}, theme: {type: 'string'},guide:{type:'boolean'}, component_ids: {type: 'array', items: {type: 'string'}}},
    additionalProperties: false,
  },
};
export const pptStartTool = {
  name: 'start_ppt',
  description: '根据自然语言需求创建PPT项目，适用于纯文字主题及附带资料的新稿。name为简短项目名，title为演示标题，可选theme和purpose。宿主生成规范、目录和主题参数，返回project供prepare_ppt和finalize_ppt使用。',
  parameters: {
    type: 'object',
    properties: {name: {type: 'string'}, title: {type: 'string'}, theme: {type: 'string'}, purpose: {type: 'string'}, slide_count: {type: 'integer'}},
    required: ['name', 'title'], additionalProperties: false,
  },
};
export const pptPageTool = {
  name: 'compose_ppt_page',
  description: '用内置页型生成可编辑页面。layout选cover/section/bullets/two_column/image_text/bar_chart/closing。content包含title、body文本数组（1至8项）、两列columns[{title,body}]、image本会话PNG/JPEG路径或chart{labels,values,unit}。chart最多6根柱，labels和values必须为等长平铺数组，values只接受非负有限数值，不接受字符串或嵌套series；超过6项改用独立表格页或选择主要比较，保留科学数值。source、notes随内容传入。修订必须提供当前页SHA。普通与优化任务共用，属于确定性基础工具。',
  parameters: {type:'object',properties:{project:{type:'string'},page:{type:'string'},layout:{type:'string'},
    content:{type:'object'},expected_page_sha256:{type:'string'}},required:['project','page','layout','content'],additionalProperties:false},
};

function safeLine(value: string) {
  return value.replace(/[\r\n]/g, ' ').trim();
}

export function startPptProject(task: any, args: any) {
  if (!/^[\p{L}\p{N}][\p{L}\p{N}_-]{0,79}$/u.test(args.name ?? '') ||
      typeof args.title !== 'string' || !args.title.trim() || args.title.length > 2000 ||
      args.purpose !== undefined && (typeof args.purpose !== 'string' || args.purpose.length > 4000) ||
      args.slide_count !== undefined && (!Number.isSafeInteger(args.slide_count) || args.slide_count < 1 || args.slide_count > 200))
    throw Error('ppt_project_parameters_invalid');
  const catalog = pptThemes();
  const theme = catalog.themes.find((row: any) => row.id === (args.theme ?? 'general'));
  if (!theme) throw Error('ppt_theme_unknown_use_read_ppt_design');
  const code = join(task.workspace, 'code');
  if (!existsSync(code) || realpathSync(code) !== resolve(code) || lstatSync(code).isSymbolicLink())
    throw Error('ppt_project_workspace_changed');
  const parent = join(code, 'projects');
  mkdirSync(parent, {recursive: true});
  if (realpathSync(parent) !== resolve(parent) || lstatSync(parent).isSymbolicLink()) throw Error('ppt_project_parent_changed');
  const target = join(parent, args.name), logical = '/work/projects/' + args.name;
  const identity = {version: 1, title: args.title, purpose: args.purpose ?? '', slide_count: args.slide_count ?? null, theme_id: theme.id, theme_version: digest(theme)};
  if (existsSync(target)) {
    const saved = join(target, 'geneloop-project.json');
    if (realpathSync(target) !== resolve(target) || lstatSync(target).isSymbolicLink() ||
        !existsSync(saved) || lstatSync(saved).isSymbolicLink() || lstatSync(saved).nlink !== 1 || digest(JSON.parse(readFileSync(saved, 'utf8'))) !== digest(identity))
      throw Error('ppt_project_already_exists_choose_another_name');
    return {project: logical, theme, reused_project: true, next_action: 'write_content_outline_then_prepare_ppt'};
  }
  const staging = join(parent, '.ppt-' + randomUUID());
  mkdirSync(staging, {mode: 0o700});
  try {
    for (const folder of ['svg_output', 'notes', 'images', 'sources', 'validation']) mkdirSync(join(staging, folder));
    const colorRows = Object.entries(theme.colors).map(([name, value]) => `- ${name}: ${value}`).join('\n');
    const typography = Object.entries(theme.font_sizes_pt).map(([name, value]) => `- ${name}: ${value}`).join('\n');
    const count = args.slide_count ?? 10;
    const rhythm = Array.from({length: count}, (_, i) => `- P${String(i + 1).padStart(2, '0')}: content`).join('\n');
    const lock = `<!-- ppt-master-schema: spec-lock/v1 -->\n# Execution Lock\n\n## canvas\n- viewBox: 0 0 1280 720\n- format: ppt169\n\n## communication\n- primary_language: user-request\n- audience: ${safeLine(args.purpose ?? 'general audience')}\n- objective: ${safeLine(args.title)}\n- core_message: ${safeLine(args.title)}\n- consumption_mode: live\n\n## mode\n- mode: custom\n\n## visual_style\n- visual_style: ${theme.id}\n\n## colors\n${colorRows}\n\n## typography\n- font_family: Noto Sans CJK SC\n- title_family: Noto Sans CJK SC\n- body_family: Noto Sans CJK SC\n${typography}\n\n## icons\n- library: none\n- inventory: none\n\n## page_rhythm\n${rhythm}\n\n## pptx_structure\n- mode: flat\n`;
    const design = `# ${safeLine(args.title)}\n\n## Purpose\n${safeLine(args.purpose ?? 'Presentation based on the user request.')}\n\n## Canvas\n1280 × 720, 16:9\n\n## Design\nTheme ${theme.id}. ${theme.guidance}\n\n## Typography\nFont family Noto Sans CJK SC. Sizes in pt.\n${typography}\n\n## Colors\n${colorRows}\n\n## Content outline\nWrite the task-specific page plan and source references here before preparing typography.\n`;
    writeFileSync(join(staging, 'spec_lock.md'), lock);
    writeFileSync(join(staging, 'design_spec.md'), design);
    writeFileSync(join(staging, 'geneloop-project.json'), JSON.stringify(identity, null, 2) + '\n');
    writeFileSync(join(staging, 'validation/workflow.log'), 'GeneLoop integrated project initialization\n');
    if (existsSync(target)) throw Error('ppt_project_creation_conflict');
    renameSync(staging, target);
    return {project: logical, theme, suggested_slide_count: count, requested_slide_count: args.slide_count ?? null, reused_project: false, next_action: 'write_content_outline_then_prepare_ppt'};
  } finally {
    if (existsSync(staging) && realpathSync(staging) === resolve(staging) && !lstatSync(staging).isSymbolicLink())
      rmSync(staging, {recursive: true});
  }
}

export function registerPptDesignTools(ctx: any, current: (session: string) => any, resources:any={}) {
  ctx.tools.guard?.((call:any)=>pptNativeAuthoringGuard(current(call.agent?.session?.id)?.task,call));
  const owning = (execution: any, writable = false) => {
    const value = current(execution?.agent?.session?.id), task = value?.task;
    if (task?.status !== 'running' || task.scene?.id !== 'ppt' || task.scene.ppt_execution_strategy !== 'ppt_master' || writable && task.scene_options?.allow_output !== true)
      throw Error('ppt_design_task_not_authorized');
    return value;
  };
  const output = {schema: {type: 'object'}, render: (_args: any, value: any) => [{type: 'text', text: JSON.stringify(value)}]};
  ctx.tools.register({...pptDesignTool, output, async execute(args: any, execution: any) {
    const value = owning(execution), catalog = pptThemes();
    const themes = catalog.themes.filter((row: any) => (!args.theme || row.id === args.theme) && (!args.category || row.categories.includes(args.category)));
    if (args.theme && !themes.length) throw Error('ppt_theme_unknown');
    const components = (args.component_ids ?? []).map((id: string) => {
      const program = value.context?.library.programs.find((row: any) => row.id === id && row.component);
      const published = value.publicCapabilities?.roots.find((row:any)=>row.id===id);
      if (!program&&!published) throw Error('ppt_component_not_available_in_this_task: ' + id);
      return program?{id, description: program.component.summary, parameters_schema: program.component.parameters_schema}:
        {id,parameters_schema:published.contract.input_schema.properties.parameters};
    });
    return {version: catalog.version, themes: args.theme ? themes : themes.map(({id, name, categories}: any) => ({id, name, categories})),
      layouts:['cover','section','bullets','two_column','image_text','bar_chart','closing'],components,
      layouts_for:'compose_ppt_page_only',
      native_json:{tool:'build_ppt',revision_tool:'patch_ppt',layouts:pptDeckLayouts,languages:pptDeckLanguages,
        theme_input:'theme ID only; host applies typography and colors',
        chart_fields:{kind:['column','bar','line','pie'],categories:'string[]',series:'[{name,values:number[]}]'},
        legacy_layout_names_are_not_this_interface:true},
      content_limits:{body_items:{min:1,max:8},bar_chart:{max_bars:6,flat_arrays:true,equal_lengths:true,nonnegative_numeric_values:true}},
      ...(args.guide?{guide:readFileSync(new URL('../../../../scenarios/ppt_master/design-conventions.md',import.meta.url),'utf8'),
        skill_references:pptSkillReferences()}: {})};
  }});
  ctx.tools.register({...pptStartTool, output, async execute(args: any, execution: any) {
    return startPptProject(owning(execution, true).task, args);
  }});
  ctx.tools.register({...pptPageTool,output,async execute(args:any,execution:any){
    const task=owning(execution,true).task;
    if(!args||['project','page','layout'].some(key=>typeof args[key]!=='string')||
      !args.content||typeof args.content!=='object'||Array.isArray(args.content))
      throw Error('ppt_page_arguments_invalid: project, page, layout must be TOP-LEVEL tool arguments; content contains title/body/image/source/notes only. Shape: {project:"/work/projects/name",page:"slide_03.svg",layout:"bullets",content:{title:"...",body:["..."]}}. Do not put project/page/layout inside content.');
    const {pptWorkspacePath,runPptInSession}=await import('../delivery/ppt_delivery_pipeline.ts');
    const project=pptWorkspacePath(task.workspace,args.project);
    const pagePath=join(project,'svg_output',args.page);
    if(!/^[\p{L}\p{N}_-]{1,128}\.svg$/u.test(args.page))throw Error('ppt_page_filename_invalid');
    if(existsSync(pagePath)){
      const checked=pptWorkspacePath(task.workspace,args.project+'/svg_output/'+args.page);
      const version=createHash('sha256').update(readFileSync(checked)).digest('hex');
      if(args.expected_page_sha256!==version)return {status:'rejected',error:{code:'ppt_page_version_conflict',
        current_page_sha256:version,page:args.page,next_action:'read_current_page_then_retry_with_this_sha256'},model_requests_inside:0};
    }
    const required=args.layout==='two_column'?['title','columns']:args.layout==='bar_chart'?['title','chart']:
      args.layout==='image_text'?['title','body','image']:['title'];
    const missing=required.filter(key=>args.content[key]===undefined);
    if(missing.length)return {status:'rejected',error:{code:'ppt_page_content_missing',fields:missing,layout:args.layout},model_requests_inside:0};
    const marker=JSON.parse(readFileSync(pptWorkspacePath(task.workspace,args.project+'/geneloop-project.json'),'utf8'));
    const theme=pptThemes().themes.find((row:any)=>row.id===marker.theme_id);
    if(!theme||digest(theme)!==marker.theme_version)throw Error('ppt_project_theme_changed');
    if(!['cover','section','bullets','two_column','image_text','bar_chart','closing'].includes(args.layout))throw Error('ppt_layout_unknown');
    if(!lstatSync(project).isDirectory())throw Error('ppt_project_required');
    const layout_config=JSON.parse(readFileSync(new URL('../../../../scenarios/ppt_master/page-layouts.json',import.meta.url),'utf8'));
    const result=await runPptInSession(task,{...args,operation:'compose',theme,layout_config},resources,execution.signal);
    recordPptNativeAuthoring(task,args.project,args.page,result.sha256);
    appendFileSync(join(task.output,'ppt-native-pages.jsonl'),JSON.stringify({call_id:execution.callId,
      arguments_sha256:digest(args),native_path:result.page,sha256:result.sha256,mode:'native_builtin_template'})+'\n',{mode:0o600});
    return {...result,next_action:'continue_same_authoring_path_then_finalize_ppt',
      authoring_policy:'Keep adopted pages. Revise with compose_ppt_page and current SHA; do not rebuild them with scripts. Host owns font measurement, export and preview.'};
  }});
}
