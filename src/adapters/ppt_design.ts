/** Integrated theme discovery and project setup for ordinary presentation tasks. */
import {existsSync,lstatSync,mkdirSync,readFileSync,realpathSync,renameSync,rmSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import {digest} from '../motif_core/online_skill_runtime.mjs';
import {appendFileSync} from 'node:fs';

const themesUrl = new URL('../../scenarios/ppt_master/themes.json', import.meta.url);
export function pptThemes() {
  return JSON.parse(readFileSync(themesUrl, 'utf8'));
}

export const pptDesignTool = {
  name: 'read_ppt_design',
  description: '查看通用PPT主题卡。可按category筛选，或用theme读取完整配色和页型。component_ids读取本任务已认证组件的完整参数契约，按需读取即可。',
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
  description: '用内置页型生成可编辑页面。layout选cover/section/bullets/two_column/image_text/bar_chart/closing。content包含title、body文本数组、两列columns[{title,body}]、image本会话PNG/JPEG路径或chart{labels,values,unit}，以及source、notes。修订必须提供当前页SHA。普通与优化任务共用，属于确定性基础工具。',
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
      ...(args.guide?{guide:readFileSync(new URL('../../scenarios/ppt_master/design-conventions.md',import.meta.url),'utf8')}:{})};
  }});
  ctx.tools.register({...pptStartTool, output, async execute(args: any, execution: any) {
    return startPptProject(owning(execution, true).task, args);
  }});
  ctx.tools.register({...pptPageTool,output,async execute(args:any,execution:any){
    const task=owning(execution,true).task;
    const {pptWorkspacePath,runPptInSession}=await import('./ppt_delivery_pipeline.ts');
    const project=pptWorkspacePath(task.workspace,args.project);
    const marker=JSON.parse(readFileSync(pptWorkspacePath(task.workspace,args.project+'/geneloop-project.json'),'utf8'));
    const theme=pptThemes().themes.find((row:any)=>row.id===marker.theme_id);
    if(!theme||digest(theme)!==marker.theme_version)throw Error('ppt_project_theme_changed');
    if(!['cover','section','bullets','two_column','image_text','bar_chart','closing'].includes(args.layout))throw Error('ppt_layout_unknown');
    if(!lstatSync(project).isDirectory())throw Error('ppt_project_required');
    const layout_config=JSON.parse(readFileSync(new URL('../../scenarios/ppt_master/page-layouts.json',import.meta.url),'utf8'));
    const result=await runPptInSession(task,{...args,operation:'compose',theme,layout_config},resources,execution.signal);
    appendFileSync(join(task.output,'ppt-native-pages.jsonl'),JSON.stringify({call_id:execution.callId,
      arguments_sha256:digest(args),native_path:result.page,sha256:result.sha256,mode:'native_builtin_template'})+'\n',{mode:0o600});
    return result;
  }});
}
