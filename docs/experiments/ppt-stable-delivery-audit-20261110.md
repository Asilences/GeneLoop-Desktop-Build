# PPT 稳定交付审计与修复（2026-11-10）

## 当前实施状态

以下修复基于同一隔离工作区，候选PPT152/Paper154；未修改前端、正式服务和原15题结果，未提交或PR。本轮制作、Judge、RSI Builder新增模型请求均为0。下方原始审计段保留为修复前证据。

|顺序|已实施的变化|模块与入口|证据与边界|
|---|---|---|---|
|1|明确生成/改页请求不能仅凭模型文字完成；当前完整导出可由宿主直接返回；成功发布使用DSH原生`concludesTurn`结束工具循环，已看过的同版本导出可直接结束|`ppt_task_completion.ts`、`ppt_delivery_pipeline.ts`、`dsh_web_tasks.ts`|旧S01-B/S02-O两条未执行修订现均拒绝假完成；G03-O/S05-B旧完整导出可接纳。格式化工具调用仍由原生steering恢复，不解析DSML执行。不能据此保证上游始终产生有效调用。|
|2|内置写页与锁定导出器共用文字宽度/余量算法；缺参数和SHA冲突返回具体字段及当前版本；允许安全只读Shell及已有图片准备|`ppt_design_preflight.py:exporter_text_width`、`ppt_page_renderer.py`、`ppt_design.ts`、`ppt_authoring.ts`|G05-O原成功调用中的cover/bullets/two_column三类内容未改，隔离重放后实际Office导出passed，findings为空；未重跑原35页任务或模型。|
|3|提供原生文字/字号/对齐小修改，保留未选OOXML部件并实际渲染；现有原生PPT场景准入与工具页数上限统一到200|`ppt_native_edit.py`、`edit_ppt_native`、`harless_task_scope.ts`|X05-O原10页附件复制到新会话，目标第一页标题居中；仅`ppt/slides/slide1.xml`改变，其余部件逐字节不变，源文件SHA不变，PPTX/PDF/10张PNG可交付。复杂重排和非文字对象编辑仍走旧路线；只验证了这一项真实Office小修改。|
|4|提供固定素材复制/裁剪/缩放工具；外部素材尝试达到8次或距首次尝试已过90秒时，下次调用返回收敛指令；拒绝自写爬虫/后台搜图循环|`prepare_ppt_asset`、`ppt_preview_runner.py`、`ppt_asset_budget.ts`|本地素材不受该外网计数限制；同一call重复守卫不重复计数且不绕过拒绝。它是工程限流与基础稿制作指引，不保证模型必然完成基础稿，不以缺失的必需图件冒充完成。|
|5|Judge与RSI独立请求、进程、锁、日志及状态；评分继续内部显式开启；学习捕获或worker异常不能撤销有效交付；按样本隔离坏材料；备注按需而非每页强制|`harless_ppt_learning.ts`、`learn-web-ppt-tasks.py`、`ppt_workflow_learning.py`、`ppt_delivery_quality.py`|前台只保留必要的成品版本核对与不可变下载快照；后台模型费用沿原分账。负反馈仍可影响后继能力准入。未将这些固定工程路径称为学得Motif。|

### 免费验证

- Windows：相关Python43通过；Node定向48通过/2个可选Python环境项跳过，最终真实Runtime收尾检查所在交付Node31通过。随后配置本机实际Python，在原深目录下后台学习6项全部通过、无跳过，包含单路采集→认证、后继晋级→重启恢复→负反馈停用及Judge故障隔离，日志为私有`windows-learning-full.log`。
- Linux：完整`npm test`中的Python3273通过/225跳过（1367.01秒）；最终PPT152的完整Node1788通过/11跳过（115秒）；smoke、motif:check、rsi:check均通过。152与149的全部Python运行代码及测试SHA一致，复用该完整Python回归；变化的工作流契约另做相关Python83项通过。最终256项代码锁全部核对一致。
- 中间149/150的Node均出现6处失败，原日志保留：旧测试工具表缺新增接口；异步采集后旧测试立即读文件；新原生工具被误设为旧宿主的必装项。已补齐测试表、仅将PPT采集改为异步并让该测试等待后台产物、将原生工具标为宿主可选；未放宽实际工具版本和权限检查。151及152完整Node均零失败。149的`npm test`总退出码仍为1，不能将旧整条命令改称通过；完整Python及修复后的完整Node结果分别报告。
- 额外真实DSH Runtime诊断发现，在`tools/execute`包装器上添加`concludesTurn`字段会被原生Runtime归一化丢弃，先前替身测试未发现。最终改为调用原生execution的`concludeTurn()`，测试改用真实`ToolRuntime/AgentLoop`验证成功标记传播、失败不结束。未修改DSH上游核心，原诊断失败记录保留。
- 原始失败回放与实际工具/Office诊断保存在私有`.local/stable-delivery-20261110/`及服务器隔离staging的`.local/free-replay/`；原运行状态和账本未改写。
- 新收尾策略未追加付费模型端到端运行，因此不宣称已消除一切有稿后诊断、不再失败或稳定降费。实际渲染拼图做了内部非盲查看，机械通过不代表全面内容/风格合格；G05英文换行仍可能在单词内断开。Mac真实设备Office尚未验收；本轮没有改动桌面整体运行架构。

### 后台运行与费用边界

正常路径是制作并返回当前成品，随后独立调度学习与内部可选Judge。学习请求使用`worker_mode=learning`与`.lock`，Judge使用`worker_mode=review`与`.review.lock`；Judge的重试计时器仅重启Judge。两者不会等待彼此完成，也不占用主聊天的任务完成条件。材料留存仍在会话切换前完成必要的有界快照，避免后台读取到下一版页面；快照失败排除学习，不复用不完整证据。

机械交付不等于满足全部用户内容要求或视觉/科研质量；是否需要每页备注由manifest显式`require_notes`控制，现有机械评审默认备注可选，不声称自动识别了全部自然语言备注约束。收尾或格式恢复仍失败时及时报告实际状态，不能返回旧稿冒充改页成功。真实端到端稳定性与成本效果须在后续正常使用中观察，本轮不扩跑。

## 修复前只读审计（保留原始结论）

- 范围：本地隔离工作区及真实批次`ppt-three-category-15-20261109`，PPT145前半段/PPT147后半段；不是main或正式部署的验收。仅只读代码/原轨迹分析，新增模型请求0、未打开PPT、未修改在线制作代码、未提交/PR。
- 证据：私有`final-results/creation-results-frozen.json`、`judge-results.json`、`learning-results.json`及本轮`failure-audit-20261110.json`。按任务本轮`trace_start_index`分段，原文件/状态/费用保留。
- 重要更正：上一轮8/15、6/15为客户端/任务链终态完成数，不是逐项核验后的完整交付率。S01-B、S02-O修订均只执行读取操作后将改页调用写成DSML普通文字，没有本轮导出或present，仍被标completed。此前“双方完成五题合计低15.5%”只能保留为按接口状态筛选的历史统计，不能作为已交付且同质量降本结果。

## 影响用户拿到成果的问题

|优先级|问题与实际证据|代码位置|修复方向与边界|
|---|---|---|---|
|P0|假完成：S01-B、S02-O修订未执行却completed|`ppt_delivery_pipeline.ts:pptTaskAcceptance`、`ppt_master_recovery.ts:createPptMasterRecovery`、`dsh_web_tasks.ts:finish`|明确区分生成/编辑请求和纯讨论；绑定用户本轮请求、选定稿件及期望修改。没有实际修改/新交付不能成功；“无需修改”须说明依据。格式恢复不能仅依赖`ppt_work_started`，仍不从DSML文本直接执行代码。|
|P0|有稿不收尾：G03-O已有15页passed导出却继续素材查看，S05-B已有6页passed导出仍反复finalize、路径错误和修订，最终超时|`ppt_delivery_pipeline.ts`、`dsh_web_tasks.ts`、`ppt_master_recovery.ts`|宿主管理唯一当前稿和最后成功版本；完成必要预览后固定续接交付。后续修改必须有具体未解决缺陷；旧版可提供为明确标记的草稿，不能当本轮已完成成果。|
|P0|页面渲染器与导出检查不一致：G05两侧35页均被溢出拦截；内置compose分别79/78次，工具错误44/42次，重复出现修订SHA错误|`ppt_page_renderer.py:render_page`、`ppt_design.ts`、`ppt_delivery_runner.py:run_delivery`|统一字体/换行/宽度计算与导出检查，在写页时预检；返回结构化字段错误与可信当前版本，不让模型读Traceback猜参数。脚本处理可验证换行/几何问题；保留关键数值，不静默删除内容或无限缩字号。|
|P0|保护过宽：采用任一内置页后，大量Bash调用统一拒绝，G02最终连`echo hello`也被拒；G03-O素材裁剪受阻|`ppt_authoring.ts:pptNativeAuthoringGuard`|按目标路径、读写行为保护采用页；源图准备、只读查看与输出处理分开授权，提供固定图像处理入口。不能简单全面放开Shell或取消版本检查。|
|P0|原PPT小修改走整稿SVG往返：X01耗137/172请求，X04/X05反复字体/多行标题/原生结构诊断；X05-O曾生成edited.pptx，随后又导入原稿研究roundtrip|`scenarios/ppt_master/SKILL.md`原PPT入口、`ppt_delivery_pipeline.ts`|普通文字替换、标题大小写、对齐和字号优先原生OOXML定向编辑并核对非目标部分；只有确需复杂重排时使用SVG往返。原生编辑用对应校验/导出，不强迫Generate准备流程。|
|P0|输入契约冲突：X03原稿56页，两组0模型即HTTP400，运行日志为`invalid_scene_options`。sceneOptions只允许slides<=30，制作引擎可到200|`harless_task_scope.ts:sceneOptions/requestedSlides`、`dsh_web_tasks.ts`准入|已有PPT页数取原稿，不挪用新建页数参数；统一前后端页数容量。真不支持时提交前明确说明，不能返回泛化400后让用户等待。|
|P0|无阶段预算/降级交付：G02-O反复搜图，续接195请求后人为停止，仅1页；G03-B主要停在图片筛选|PPT任务调度与素材工具；实验`deadline_watch.py`不属于产品能力|先形成完整基础稿，再在限定素材尝试内增强。外网失败优先原附件/本地资源/文字图表；不伪造科研图件。超时应进入明确恢复或基础稿交付，实验直接取消不是产品兜底。|
|P1|后台材料异常阻塞全批学习：X02原稿13页仅4个notes部分，保留原稿应合法；inspect_delivery却强制每页备注，advance_workflow_learning未隔离单份材料异常|`ppt_delivery_quality.py:inspect_delivery`、`ppt_workflow_learning.py:advance_workflow_learning`|按生成/编辑及用户是否要求备注验收；学习按样本排除和记录错误，不冻结其他来源。Judge/学习不影响下载或任务交付。|
|P1|宿主/上游故障：前半段两次Node -11，后半段PPT抓取已隔离；50次制作请求缺usage，10次Judge仅usage无有效内容|`ppt_web_fetch.ts`、公共模型入口、任务恢复|当前隔离修复后批次跑完，不能宣称原生崩溃根因已定位。持久化阶段/已完成页，按原会话恢复；模型故障有界重试。Judge缺评分不变成制作失败。|

## 已有修复与未闭环

旧G01-O和X01-B/O的终态误判已由PPT147任务级最终稿选择修复，并用原始证据免费回放验证；不回写旧失败。该修复不等于完整交付收敛：G04-O仍存在导出后改源、最终DSML文本化且没有新交付；原生编辑回退目前仅核对本轮present字节和文件头，尚不能证明文件可完整解析、PDF与PPTX一致或指定页修改正确。

本轮Judge10请求/已知配置估费USD0.0988374，无有效分数；本批学习尝试被备注检查打断，无本批新增认证成功结论。页面素材入队不等于新能力通过。原学得修订程序只在S01-O实际执行一次、段内模型0；这不能承担上述通用工程失败恢复。

## 建议实施顺序

1. 先修“假完成”和唯一稿件/版本收尾；以原S01/S02/G03/G04/S05轨迹做无模型回放，不重跑15题。
2. 对齐页面布局计量、结构化参数错误与版本传递；细化保护边界，让工具承担确定性修复。
3. 将原生PPT的小修改从SVG重制链拆出，统一输入容量和对应交付验收。
4. 增加素材阶段限时、最后成功稿与基础稿恢复；科研事实/必需图缺失必须明确，不能靠假造成果达标。
5. 再恢复按样本隔离的学习及内部可选Judge。基础工程通道可靠后，RSI学习轨迹中的采用条件和有效恢复分支；手写兜底不称RSI。

验收看实际输出与请求绑定：新稿可解析、可编辑、页数/关键内容符合要求；改页有实际操作及新版本，非目标页保持；导出后无缺陷不继续返工；外图服务不可用仍可完成不依赖该外图的基础表达。坏输入/必需来源缺失/上游持续不可用不可声称100%完成，须及时说明。新稿基础交付、满足全部要求及可选增强应分别记录。
