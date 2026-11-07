# 六场景需求、实现与桌面依赖交叉核对

## 结论与版本

2026-11-08重新fetch，`origin/main=1d1e16f4bde7f980127a53ead305e0e5d8b08b86`。桌面基线为`24249cae`；本轮只新增下面记录的文件管理启动修复及范围说明，不改同伴的场景算法、Motif或隐私核心，不制作／上传安装包。

核对不只依赖交接：以当前注册项→实际server和工具函数→桌面绑定→依赖／构建入口为主，并对照相关PR正文、评论和历史说明。PPT按用户最新要求收窄；其余五场景没有发现新的“明确不需要、但桌面仍必须额外安装”的大组件。不能为了缩包把仍被当前实现调用的统计库、OCR、Office、浏览器或媒体工具删掉。

判定规则：

- 当前明确产品要求优先；同一功能后续PR与当前实现优先于早期说明。
- 单道题的禁用项只约束该题；未验证、未配置、未实现不等于负责人要求永久取消。
- 通用命令、共享工具与场景专用MCP分别核对。没有专用工具不等于通用Agent永远不能完成，但也不据此给基础工具包增加整套可选环境。

## 逐场景结果

| 场景 | 当前实际实现与桌面接线 | 保留的依赖／能力 | 不额外做的适配 |
| --- | --- | --- | --- |
| Chat | `general/server.py`两项文件工具；`general/runtime.py`四项编辑／隔离代码工具；公共Gateway按需发现Paper/Data/PPT；桌面`desktop_general.py`复用原server，只替换隔离代码后端与能力探针 | 官方DSH公共文件、搜索、代码和后台任务；获准副本；PDF读取、现有图像输入 | 不新增本地大模型、训练栈或未连接的第三方服务；不把早期“只有两项文件工具”当成现有能力上限 |
| Data | 注册的是`report-scenario.json`，不是旧`scenario.json`；`report_session.py`复用v3工作流，v3复用v2/v1实际统计、复算、绘图与排版；桌面`desktop_workflow_server.py:create('report')`直接加载它 | 17项工具；NumPy/Pandas/SciPy/Statsmodels/Matplotlib；ReportLab/PDF；显式表格与原图逐格转录 | 不打包GPU训练框架或大型表格识别模型；不插补、编造数据或增加因果结论。旧版“仅描述统计／不显著性推断”不用于裁掉当前实际回归和检验 |
| Paper | `paper_proofreading/server.py`读取真实文档、调用`paper_static_checks.py`，并复用`paper-submission/checks.py`引用取证；桌面原server＋固定原生PDF排版接缝，结构修订保留独立工具 | 20项校对／引用／审校工具＋4项修订；PDF/Office读取、来源与版本、按需外部元数据核验、PDF/Markdown报告 | 当前prompt明确“不编译、不修改原稿”；实际检查器也不执行LaTeX。无需新增TeX Live/MiKTeX、latexmk或自动投稿环境。TeX源文本经Pandoc转换与编译排版是两件事 |
| Files | `web-prompt.md`要求真实覆盖和可恢复整理；原`PlanScene`13项与`ManagementScene`27项保留；桌面只换PDF读取后端、原生确认与副本交付 | 文档/OCR、哈希、索引、分页读取、预览、整理／恢复、按实际连接发现动态工具；原件不被桌面副本流程直接覆盖 | 不扩到未授权目录，不为未连接私有MCP添装组件；不能按早期“最多六步的PlanScene”删除当前ManagementScene和全文读取 |
| Video | `web_server.py`接原`structured/server.py`与固定Remotion；桌面`local-video-workflow.mjs`对应11项工具，`local-video.mjs`／`local-remotion-entry.mjs`实际调用本机FFmpeg、Remotion、Chromium | 裁剪／拼接、模型编写TSX、标题／字幕叠加、已有音轨编辑、成片解码与抽帧、源码交付 | 当前11项实现无ASR／TTS调用，不为它加Torch/Whisper或3.68GB语音环境。`t05_captions`“不要调用语音识别”仅是该题已给文字／时码的约束，不能外推为全场景永久禁止语音功能 |
| PPT | GeneLoop自有`geneloop-ppt` Skill＋锁定PPT Master制作引擎；核心`prepare_ppt/finalize_ppt`及材料／模板工具保持 | 仅制作／编辑PPT，模板、源材料、字体、Office/PDF/逐页图预览、可编辑交付 | 用户已明确取消旁白、配音、演示视频、录屏与字幕；六个附加CLI被拒绝，不准备语音包，不新增PPT语音服务器。独立Video不受影响 |

以上均为本机工具范围。模型仍联网调用云端，不把“本机Agent”误解成安装模型权重。

### Chat与共享能力：早期限制已被后续实现替代

[PR #57（peilin6）](https://github.com/jingyio/GeneLoop/pull/57)明确为Chat/PPT/Data/Paper/Files开放网络、代码执行与后台任务。当前`config/geneloop-capabilities.json`与桌面`local-common.mjs`均实际接入公共能力；`config/general-tools.json`还登记按需场景Provider。因此不能仅看`general/scenario.json`的两项工具，删去后续接通的公共能力。

网页Bubblewrap/Docker是原执行环境实现，不是本机必须捆绑的业务功能。桌面通用受限代码工具用QuickJS WASM；Windows公共命令用官方PowerShell、Mac用官方Bash。这些替换保留隔离与取消，不把未连接服务说成已可用。

### Data：当前报告工作流不等于旧CSV工具

`config/harless-scenes.json`实际指向`scenarios/data_analysis/report-scenario.json`；`report_session.py`从`benchmarks/research_report_agent_v3`注册14项原工具，再添加原图查看／转录和输入核对3项。v3真实调用v1的Pandas/SciPy/Statsmodels分析与独立复算，v2实际提供报告布局。因此旧`data_analysis/prompt.md`的窄统计范围不能作为削减当前依赖的依据。图像转录由当前模型读取原像素，不据此添装大型OCR训练／推理栈。

### Paper：静态LaTeX检查与PDF报告导出分别保留

当前`prompt.md`第1、35行明确不编译LaTeX；`paper_static_checks.py`只有源码／日志诊断，`paper-submission/checks.py`也明确不运行论文源码。桌面审校PDF走原有`document_engine`，不是TeX编译器。普通校对默认不联网、用户要求真实性核验时才取外部证据，不应因此移除arXiv/Crossref工具。

[PR #19评论](https://github.com/jingyio/GeneLoop/pull/19#issuecomment-6212107105)明确被[PR #42](https://github.com/jingyio/GeneLoop/pull/42)替代；本轮以当前多格式读取与报告实现为准，不用旧PR的未部署说明断言当前功能不存在。

### Files和共享PDF：OCR是明确要求

[PR #80（peilin6）](https://github.com/jingyio/GeneLoop/pull/80)接通逐页文字、扫描页中英文OCR和真实页图，并明确覆盖五场景。当前`geneloop_pdf.py`实际调用PyMuPDF OCR，桌面固定语言数据和`desktop_general.py:verify_native_ocr`仍保留。Files的完整读取还由`management_reading.py`记录覆盖，不能将两页预览误称全文。

本轮没有发现必须新装PaddleOCR/EasyOCR或另一套深度学习OCR的实现；保留的是现有PyMuPDF和固定中英文tessdata，不自行扩成大型可选OCR套件。

### Video：标题／字幕与语音识别不是同一个能力

实际网页工具只有素材固定、探测、源码读写、Remotion渲染、抽帧、说明和受限命令；`web-prompt.md`要求检查已有音轨。`tasks.json:t05_captions`给定字幕文字与时码。按这条实现链，只需FFmpeg/FFprobe＋Remotion/React＋Chromium，保留字幕与声音编辑，不需要ASR权重。最新主线未找到这条链的语音识别部署入口；不能由此推断同伴服务器的手工安装状态。

## 实际目录检查与附带修复

- 当前main的默认场景72条工具映射、公共20条、宿主PPT2条、条件Management27条、动态Provider9条，共130行，`audit-web-tool-parity.mjs --check`通过。它是映射清单，不是130项真实任务质量验收。
- 在隔离合成目录实际启动10组MCP，取得118项工具目录；另用实际Video注册函数构造11项工具目录，总129项，与桌面allowlist一致。两种统计维度不同，不能相加或称作129项业务任务通过。
- 文件管理`read_task/list_files`实际调用成功。Video本轮只核对目录，没有重新渲染；PPT和其他场景本轮没有发模型请求。
- 构建源副本的9个关键入口文件SHA与当前源码相同。随后只在本次审计目录复制少量运行文件做候选检查，没有覆盖现有生成工具包或安装实例。
- 发现并修复：嵌入式Python的`sitecustomize`提前导入PPT适配，缓存了安装目录中的`src/scenarios`；Management本应加载临时源码副本，结果其私有journal根检查拒绝。`local-workflows.mjs`仅对Management父进程关闭该提前导入；按需子Provider仍保留原Skill环境。原场景校验不放宽，安装目录不写入。

本轮私有证据：`.local/desktop-scene-scope-20261108/`，含GitHub只读快照、实际目录回执、修复前后错误与定向检查。首次长路径夹具失败、在未编译源码目录启动修订工具失败属于审计夹具问题，均保留记录；最终使用短路径及私有编译运行文件副本检查。

验证结果：

- `node apps/desktop/scripts/audit-web-tool-parity.mjs --check`通过，130行、未映射0。
- 实际目录探针10组MCP＋原生Video目录通过，129目录项；`catalog-receipt.json`记录实际名称，模型请求0。
- 已有`check-native-workflows.mjs --core`在短临时根通过：Management实际确认／执行／恢复、Files副本交付、硬链接越界拒绝、来源失效、Paper取证与审校PDF、Data输入检查、受限代码与动态Gateway均通过。PPT Office重渲染不在`--core`范围内。
- `npm --prefix apps/desktop run check`编译及14项通过。
- `npm test`使用`PYTEST_ADDOPTS='-x --maxfail=1'`尝试，在`test_capability_output_verifier.py`收集时因本机Anaconda的Pillow `_imaging` DLL初始化失败停止；报告1个收集错误。之后命令未退出，结束本次测试会话；Node全仓阶段未运行，不报告全仓通过。没有删除或放宽原检查。
- 第一次核心检查的长临时路径使旧Files执行回执缺失；增加先输出工具错误的断言，缩短临时根后通过。未将缩短路径的诊断外推为任意Windows路径都已验收。

## 交付边界

本轮不重新运行复杂真实模型任务，不下载新大工具，不开启Mac Actions、不消耗Mac免费额度，不触碰正式服务器。Windows目录诊断不替代Mac原生／人工验收；新Kit和最新分包的Mac验证、下一版本安装包仍按原交接推进。既有preview.19安装器与公开工具包不因本次源码修订自动改变。
