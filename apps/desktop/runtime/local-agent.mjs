import { randomUUID } from 'node:crypto';
import { createUserMessage } from '@deepseek-ai/dsh-llm';
import { openReportWriter, openWorkspaceReader } from './local-files.mjs';
import { registerLocalFileTools } from './local-file-tools.mjs';

// Constructed by the trusted desktop worker after native directory approval.
export async function openLocalFileAgent(ctx, { directory, model, signal, onReport, sessionId = randomUUID(), resume = false, scene = 'files', media, approveVideo, onVideoPhase, ppt, legacyTools = false }) {
  if (ppt) ppt = {...ppt,nativeContext:ctx};
  const reader = openWorkspaceReader(directory);
  let writer, handle;
  try {
    writer = openReportWriter(directory);
    const options = {
      agentOptions: model,
      signal,
      setup(scope) {
        registerLocalFileTools(scope, reader, writer, onReport, scene, signal, media, approveVideo, ppt, onVideoPhase, ctx,legacyTools);
        if(legacyTools)scope.systemPrompt.section({name:'geneloop:desktop-compatibility',order:10200,
          text:'当前网关尚未声明新版场景工具协议，本轮只提供旧版本工具。若任务需要Excel、多文件静态核验或普通PPT模板编辑，请说明需要更新GeneLoop网关；不要声称已使用这些未提供的工具。现有本机工具仍可使用，不转为云端执行。'});
        if(ppt&&!legacyTools)scope.systemPrompt.section({name:'geneloop:desktop-documents',order:10200,
          text:'Office/PDF等材料先用 local_document_pin 固定版本，再用 local_document_read 分页核对。所有资料与工具在本机处理，模型通过网络调用。数据用 local_data_inspect/analyze 读取显式表格；文件整理用 local_files_export 交付副本。论文可用 local_paper_audit_sources 复用静态检查。只使用当前场景实际提供的工具，不把文本抽取称为视觉检查或把静态核验称为真实编译。'});
        if (scene === 'video' && media?.remotion) scope.systemPrompt.section({
          name:'geneloop:desktop-video',order:10210,
          text:'视频使用 local_video_render 在本机执行。复杂合成的 plan 为 {source,assets}，source 是 Remotion TSX，assets 为授权素材路径数组；简单剪辑的 plan 为时间线数组。用户未明确要求服务器执行时，不调用 hybrid_video_render。不引用外部网络素材。',
        });
        if (scene === 'chat') scope.systemPrompt.section({
          name: 'geneloop:desktop-chat', order: 10210,
          text: '你是 GeneLoop。直接回复一般问题，只在任务确实需要文件时调用已授权的本机工具。'
            + '只引用实际读取的来源，不编造文件内容，也不将用户原文件写入或移动到其他位置。',
        });
        if (scene === 'ppt' && ppt) scope.systemPrompt.section({
          name: 'geneloop:desktop-ppt-master', order: 10210,
          text: '使用 local_ppt_master_guide 读取锁定版技能入口和 Generate 工作流。'
            + '用户给出来源时先用 local_ppt_read_material 核对实际内容和版本，将所用材料摘要放进交付计划。'
            + '用户给出带字段标记的 PPTX 模板时先读取各页字段，用 local_ppt_fill_template 填写副本。'
            + '普通模板无需添加字段标记，读取 shapes 后用 local_ppt_edit_template 修改指定文本框副本。'
            + '对于静态形状和文本页面，先准备设计规格和逐页备注，再使用 local_ppt_master_export 交付。'
            + '按真实检查结果修复，分别说明机械检查和目视审阅状态。'
            + '如果需求超出当前本机工具范围，请先说明可交付的部分。',
        });
      },
    };
    handle = resume
      ? await ctx.agents.resume({ ...options, resumeSessionId: sessionId })
      : await ctx.agents.create({ ...options, sessionId, meta: { cwd: directory } });
  } catch (error) {
    writer?.close();
    reader.close();
    throw error;
  }
  const { agent } = handle;
  let closing;
  return {
    agent,
    submit(text) {
      if (closing) throw Error('本机会话已关闭。');
      if (agent.status !== 'idle') throw Error('请等待当前本机任务完成。');
      if (typeof text !== 'string' || !text.trim()) throw Error('请输入本机会话消息。');
      agent.followup(createUserMessage({ source: { kind: 'user' }, content: [{ type: 'text', text }] }));
    },
    async cancel() {
      agent.cancel({ kind: 'user' });
      await agent.whenIdle();
    },
    close() {
      // Revoke file capabilities immediately, even if Agent disposal must wait.
      if (!closing) {
        writer?.close();
        reader.close();
        closing = Promise.resolve().then(() => handle.dispose());
      }
      return closing;
    },
  };
}
