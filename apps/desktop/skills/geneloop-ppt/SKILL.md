---
name: geneloop-ppt
description: 制作、编辑和核验可编辑 PPTX，交付 PDF 与逐页预览；不生成配音、视频或字幕。
---

# GeneLoop PPT

仅处理演示文稿本身：理解要求和来源、参考模板、设计页面、创建或修改可编辑 PPTX、核验 PDF 与逐页图片。普通演讲备注可保留在 PPTX 内。不制作旁白音频、配音、演示视频、录屏或字幕，不调用相关脚本，不安装 Torch、Whisper、stable-ts 或 edge-tts。

1. 用 `local_ppt_master_guide` 的 `skill/generate/spec` 阅读已锁定的制作规范。上游包含更多扩展流程，本场景只采用材料、设计、模板、页面、备注和 PPTX 导出部分。
2. 核对真实来源。使用 `local_ppt_pin_source/read_source` 或 `local_ppt_read_material`；已有 PPTX 用 `local_ppt_edit_template` 修改副本，有占位字段的模板用 `local_ppt_fill_template`。
3. 新建工程放在当前任务的 `projects/`。明确 `spec_lock.md` 和 `design_spec.md` 后调用 `prepare_ppt`，根据真实 normal/bold 字体测量结果制作页面。
4. 使用已配置的 Python 和上游只读制作脚本，保留可编辑文字、真实图片、来源与 PPTX 备注。不要写用户原件。
5. 调用 `finalize_ppt`，检查真实 PDF 和逐页 PNG，必要时修订；只交付任务要求的 PPTX 及预览资料。已由工具交付的文件不再重复 `present`。

独立视频剪辑属于 GeneLoop 的视频场景；不因 PPT Master 附带的视频扩展而扩张本场景范围。
