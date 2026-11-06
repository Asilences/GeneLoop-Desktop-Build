import { execFile } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, realpathSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { promisify } from 'node:util';
import { inSceneScratch, publishArtifacts } from './local-artifacts.mjs';
import { readPaperPage } from './local-paper.mjs';
import { runNativeProcess } from './native-process.mjs';

const run = promisify(execFile);
const limit = (value, size) => typeof value === 'string' && value.trim() && Buffer.byteLength(value) <= size;
const guidePaths = { skill:'SKILL.md', generate:'workflows/generate-pptx.md', spec:'workflows/stages/refine-spec.md' };
const maxSourceBytes = 16 * 1024 * 1024;
const sha = bytes => createHash('sha256').update(bytes).digest('hex');

export function readPptMasterGuide(tools, section) {
  if (!Object.hasOwn(guidePaths, section)) throw Error('请选择 skill、generate 或 spec。');
  const name = guidePaths[section];
  const lock = JSON.parse(readFileSync(join(tools.sourceRoot, 'scenarios/ppt_master/skill-lock.json'), 'utf8'));
  const path = join(tools.skill, name);
  const actual = realpathSync(path);
  if ((process.platform === 'win32' ? actual.toLowerCase() !== path.toLowerCase() : actual !== path) || statSync(path).size > 64 * 1024) {
    throw Error('ppt-master 指南位置或大小无效。');
  }
  const bytes = readFileSync(path);
  if (createHash('sha256').update(bytes).digest('hex') !== lock.files[name]) throw Error('ppt-master 指南与锁定版本不符。');
  return bytes.toString('utf8');
}

function sourcesFor(reader, sources = []) {
  if (!Array.isArray(sources) || sources.length > 8) throw Error('来源最多 8 份。');
  return sources.map(source => {
    if (!source || Object.keys(source).sort().join(',') !== 'path,sha256' ||
        typeof source.path !== 'string' || !/^[0-9a-f]{64}$/.test(source.sha256)) throw Error('来源需要文件路径和摘要。');
    if (sha(reader.readBytes(source.path,maxSourceBytes)) !== source.sha256) throw Error('来源文件已变化，请重新阅读。');
    return {path:source.path,sha256:source.sha256};
  });
}

export async function pptPython(tools, scratch, signal, module, args) {
  try {
    const bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module(sys.argv.pop(1),run_name='__main__')";
    const argv = ['-E','-s','-B','-X','utf8','-c',bootstrap,tools.sourceRoot,module,...args];
    const {stdout} = tools.nativeContext
      ? await runNativeProcess(tools.nativeContext,[tools.python,...argv],scratch,signal)
      : await run(tools.python, argv, {
      cwd:tools.sourceRoot, signal, timeout:450_000, windowsHide:true, maxBuffer:2 * 1024 * 1024,
      env:{SystemRoot:process.env.SystemRoot, PATH:dirname(tools.python), TEMP:scratch, TMP:scratch,
        TMPDIR:scratch, HOME:scratch, USERPROFILE:scratch, APPDATA:scratch, LOCALAPPDATA:scratch},
    });
    return JSON.parse(stdout);
  } catch (error) {
    signal.throwIfAborted();
    try { return JSON.parse(error.stdout); } catch { throw Error('本机场景工具未完成，请检查运行依赖或输入文件。'); }
  }
}

function deliverPpt(receipt, output, writer, signal, onReport) {
  if (receipt.mechanical_status !== 'passed' || !Array.isArray(receipt.artifacts)) {
    if (Array.isArray(receipt.findings)) return {status:'failed',findings:receipt.findings.slice(0,20)};
    // Python filesystem errors may contain absolute paths. Keep those local.
    throw Error('本机 PPT 工具未能校验或导出该项目。');
  }
  const artifacts = ['pptx', 'pdf'].map(extension => {
    const row = receipt.artifacts.find(item => item.kind === extension);
    if (!row || typeof row.path !== 'string' || !new RegExp('^[a-z0-9_-]+\\.' + extension + '$', 'i').test(row.path)) {
      throw Error('缺少经核验的演示文稿产物。');
    }
    const path = join(output,row.path);
    if (statSync(path).size > 80 * 1024 * 1024) throw Error('演示文稿产物过大。');
    const bytes = readFileSync(path);
    if (sha(bytes) !== row.sha256) throw Error('演示文稿产物摘要校验失败。');
    return {extension,bytes};
  });
  const published = publishArtifacts(writer,onReport,signal,[...artifacts,{
    extension:'json',
    bytes:Buffer.from(JSON.stringify({...receipt,artifacts:receipt.artifacts.filter(item=>['pptx','pdf'].includes(item.kind))},null,2)),
  }]);
  return {status:'passed',execution:receipt.execution,review_status:receipt.review_status,
    pages:Array.isArray(receipt.pages)?receipt.pages.length:receipt.pages,artifacts:published};
}

export async function readPptMaterial(path, page, reader, tools, signal) {
  if (typeof path !== 'string' || !Number.isInteger(page) || page < 1) throw Error('请输入资料相对路径和正整数页码。');
  const extension = path.slice(path.lastIndexOf('.')).toLowerCase();
  if (extension === '.pdf') return readPaperPage(reader,{path,page});
  if (!['.pptx','.docx','.xlsx','.txt','.md','.csv','.tsv','.json','.tex','.bib'].includes(extension)) throw Error('支持 PDF、PPTX、DOCX、XLSX、JSON、LaTeX 和文本表格。');
  const bytes = reader.readBytes(path,maxSourceBytes);
  return inSceneScratch(async scratch => {
    const staged = join(scratch,'source'+extension);
    writeFileSync(staged,bytes,{flag:'wx'});
    const result = await pptPython(tools,scratch,signal,'scenarios.ppt_master.windows_source',['inspect',staged,'--page',String(page)]);
    if (typeof result.text !== 'string') throw Error('无法提取该资料的指定页或段。');
    return {path,page,sha256:sha(bytes),...result};
  });
}

export function createPptSourceReader(reader, tools, signal) {
  const sources = new Map();
  return {
    pin(path) {
      if (typeof path !== 'string' || !/\.(?:pdf|pptx|docx|xlsx|txt|md|csv|tsv|json|tex|bib)$/i.test(path)) {
        throw Error('请选择支持的 PPT 源材料。');
      }
      const version = sha(reader.readBytes(path, maxSourceBytes));
      if (sources.size === 24) sources.delete(sources.keys().next().value);
      const source_id = 'source-' + randomUUID().replaceAll('-', '');
      sources.set(source_id, {path, version});
      return {source_id, path, version_sha256:version};
    },
    async read(source_id, page) {
      const source = sources.get(source_id);
      if (!source) throw Error('材料凭证已失效，请重新固定来源。');
      // The extractor consumes the same bytes whose digest was checked.
      const boundReader = {
        readBytes(path, maxBytes) {
          const bytes = reader.readBytes(path, maxBytes);
          if (sha(bytes) !== source.version) throw Error('来源已变化，请重新固定。');
          return bytes;
        },
      };
      const {sha256:version_sha256, ...material} = await readPptMaterial(source.path, page, boundReader, tools, signal);
      return {...material, version_sha256};
    },
  };
}

export async function fillPptTemplate(path, version, planText, reader, writer, tools, signal, onReport) {
  if (typeof path !== 'string' || !/\.pptx$/i.test(path) || !limit(planText,128 * 1024)) throw Error('请输入 PPTX 模板和字段内容。');
  const plan = JSON.parse(planText);
  if (!plan || Object.keys(plan).some(key=>!['values','sources'].includes(key))) throw Error('无效的模板计划。');
  const bytes = reader.readBytes(path,maxSourceBytes);
  if (sha(bytes) !== version) throw Error('模板已变化，请重新读取字段。');
  const sources = sourcesFor(reader,plan.sources);
  return inSceneScratch(async scratch => {
    const staged = join(scratch,'source.pptx'), values = join(scratch,'fields.json');
    writeFileSync(staged,bytes,{flag:'wx'});
    writeFileSync(values,JSON.stringify(plan.values ?? null),{flag:'wx'});
    const receipt = await pptPython(tools,scratch,signal,'scenarios.ppt_master.windows_source',
      ['fill',staged,'--values',values,'--renderer',tools.soffice]);
    sourcesFor(reader,[{path,sha256:version}]);
    sourcesFor(reader,sources);
    return deliverPpt({...receipt,execution:(process.platform === 'win32' ? 'windows' : process.platform)+'-local-ppt-template',template:{path,sha256:version},sources},
      scratch,writer,signal,onReport);
  });
}

export async function editPptTemplate(path, version, planText, reader, writer, tools, signal, onReport) {
  if(typeof path!=='string'||!/\.pptx$/i.test(path)||!limit(planText,128*1024))throw Error('需要 PPTX 模板和文本框修改计划。');
  const plan=JSON.parse(planText);
  if(!plan||Object.keys(plan).some(key=>!['edits','sources'].includes(key)))throw Error('无效的模板编辑计划。');
  const bytes=reader.readBytes(path,maxSourceBytes);
  if(sha(bytes)!==version)throw Error('模板已变化，请重新读取。');
  const sources=sourcesFor(reader,plan.sources);
  return inSceneScratch(async scratch=>{
    const staged=join(scratch,'source.pptx'),values=join(scratch,'edits.json');
    writeFileSync(staged,bytes,{flag:'wx'});writeFileSync(values,JSON.stringify(plan.edits??null),{flag:'wx'});
    const result=await pptPython(tools,scratch,signal,'scenarios.ppt_master.windows_source',
      ['edit',staged,'--values',values,'--renderer',tools.soffice]);
    sourcesFor(reader,[{path,sha256:version}]);sourcesFor(reader,sources);
    return deliverPpt({...result,execution:process.platform+'-local-ppt-edit',template:{path,sha256:version},sources},scratch,writer,signal,onReport);
  });
}

export async function exportPptMaster(planText, writer, tools, signal, onReport, reader) {
  if (!limit(planText, 16 * 1024 * 1024)) throw Error('演示文稿计划超出大小限制。');
  const plan = JSON.parse(planText);
  if (!plan || Object.keys(plan).some(key=>!['pages','spec','sources'].includes(key)) || !limit(plan.spec, 64 * 1024) ||
      !Array.isArray(plan.pages) || plan.pages.length < 1 || plan.pages.length > 30 ||
      plan.pages.some(page => !page || Object.keys(page).sort().join(',') !== 'notes,svg' ||
        !limit(page.svg, 512 * 1024) || !limit(page.notes, 64 * 1024))) throw Error('需要包含设计规格和逐页 SVG、演讲备注的计划。');
  const sources = sourcesFor(reader,plan.sources);
  return inSceneScratch(async scratch => {
    const project = join(scratch, 'project');
    const output = join(scratch, 'delivery');
    mkdirSync(join(project, 'svg_output'), {recursive:true});
    mkdirSync(join(project, 'notes'));
    writeFileSync(join(project, 'spec_lock.md'), plan.spec, {flag:'wx'});
    for (const [index, page] of plan.pages.entries()) {
      const name = 'slide-' + String(index + 1).padStart(3, '0');
      writeFileSync(join(project, 'svg_output', name + '.svg'), page.svg, {flag:'wx'});
      writeFileSync(join(project, 'notes', name + '.md'), page.notes, {flag:'wx'});
    }
    const receipt = await pptPython(tools,scratch,signal,'scenarios.ppt_master.windows_delivery',
      ['--project',project,'--output',output,'--ppt-master',tools.skill,'--soffice',tools.soffice,'--desktop-job']);
    sourcesFor(reader,sources);
    return deliverPpt({...receipt,execution:(process.platform === 'win32' ? 'windows' : process.platform)+'-local-ppt-master',sources},output,writer,signal,onReport);
  });
}
