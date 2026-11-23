# PPT 后端：连续改页、收尾执行和内部评分隔离

## 范围与状态

用户要求继续收敛交付，并明确：正式用户只接收优化Agent结果，评分仅用于内部改进/查看效果；前端由另一对话负责。本轮限定后端功能，不修改页面和单结果聊天入口，不PR、不部署、不新增模型实验。上一轮[交付检查简化](ppt-delivery-convergence-20261108.md)及[真实失败记录](ppt-delivery-fixed-pair-20261108.md)保留。

工作区为`codex/ppt-managed-learning-20261104`，HEAD仍`8988de79bc97d7a7a8a4410fe0f4e91688fecc95`及未提交修改。最终本地配置为PPT119/Paper121；PPT118/Paper120为中间候选，保留但不作为最终候选。运行中的隔离Web仍PPT114/Paper116；没有切换或重启正式/隔离服务。

## 已定位并修复

### 取消、重启后同会话改页400

读取既有隔离实例的准入错误，原失败为`invalid_scene_options`。恢复任务时只与原始登记工具表比较，首次准入却加入了PPT共同交付/设计工具，因此未变化的PPT Master会话被误判为旧工具会话。旧会话降级时移除了adapter，原本有效的`slides=2,allow_output=true`随后被错误拒绝。

`dsh_web_tasks.ts`新增共用`preparedTaskScene`，首次准入和重启恢复使用相同的实际工具组合。没有放松真正的工具变化、账号、权限或新来源检查。新增用例先复现HTTP400，再验证取消后重启能继续准入、页数/输出选项及项目保持、旧取消状态不被改写。

### 收尾复制和列表查看误拦

`ppt_output_packaging.ts`识别输出目录内有限的复制、建目录、列表查看及分隔文字，由Node文件接口直接执行；不把原命令交给Shell。实际失败中出现的`cp … && ls … 2>/dev/null; echo "---"; ls …`可直接完成，受管页面仍由原执行层维护。

`ppt_write_tool.ts`只为已授权的受管任务续接这类固定输出整理。任意脚本、输入/项目目录写入、其他重定向及路径越界仍拒绝。取消、固定父目录、符号/硬链接检查保留。宿主审计记执行次数与`model_requests_inside=0`，该固定实现属于工程底座，不包装为新学得RSI能力。新文件加入共享实现签名和库源码锁。

### 评分与生产交付分离

既有两次Judge原响应各409字节，只有usage和`[DONE]`，没有正文或评分；这不是合法答案被JSON解析器漏掉，不能补造分数。

`harless_ppt_learning.ts`不再从普通Web计费配置自动继承Judge策略。只有内部显式配置`GENELOOP_PPT_REVIEW_POLICY`才启用评分；关闭时不因旧评分队列反复唤醒。正常轨迹学习策略独立保留，未拿缺评分当质量通过。

`ppt_background_review.py`将新出现的usage-only响应记为`review_unavailable`并停止自动重试，不为不存在的答案再付一次完整来源请求。已付费的历史格式重试仍可读取，真正的答案格式错误仍保留一次格式回退。旧响应、失败、评分与账单不改，评分失败不启动制作循环。本轮没有重新请求Judge，因此不声称供应商已恢复返回有效评分。

### 本机学习依赖

Windows检查发现学习子进程清理环境后无法找到已配置的用户Python依赖。保留标准Python路径及用户目录变量，凭证仍按既有白名单处理，没有全量转发环境。依赖导入问题已解决。

完整Windows学习诊断继续发现深层学习证据/临时文件超过当前Anaconda环境的路径限制；缩短夹具目录后仍有两项学习用例不通过，保留日志。未删除检查或以跳过包装通过。Linux独立副本完整执行这些学习用例通过。Windows/Mac完整学习/Office宿主仍需桌面适配验收。

## 无模型验证

| 环境与范围 | 结果 |
| --- | --- |
| Windows：交付、原生文件返回、连续程序、固定收尾、执行层 | Node 56通过 |
| Windows：准入/重启恢复、完成边界、场景及账号隔离 | Node 7通过 |
| Windows：评分开关、学习失败隔离 | Node 2通过 |
| Windows：评分协议、固定预览、PPT场景与兼容库 | Python 40通过，1符号链接权限跳过 |
| Linux：单路轨迹准入、自动认证、后继晋级、重启/负反馈/完整性及收尾 | Node 10通过 |
| Linux：内部评分协议 | Python 17通过 |

Windows为Node24.19.0/Python3.11.7，Linux为Node22.23.2/Python3.12.15。Linux在全新`ppt-backend-closure-20261108`诊断副本执行，314项源文件逐SHA核对；没有修改原运行实例。诊断样本为确定性夹具，不是新真实生成质量或降本实验。

主要命令：

```powershell
node --experimental-strip-types --test tests/test_ppt_output_packaging.mjs tests/test_ppt_write_tool.mjs tests/test_ppt_delivery_pipeline.mjs tests/test_geneloop_native_work.mjs tests/test_ppt_write_runtime.mjs tests/test_ppt_execution.mjs
node --experimental-strip-types --test --test-name-pattern='PPT Master cancelled conversation|PPT shortcut|PPT menu options|native PPT completion|actual PPT adapter completion|A scene switch|Two server-owned principals' tests/test_dsh_web_tasks.mjs
python -m pytest tests/test_ppt_background_review.py tests/test_ppt_preview.py tests/test_ppt_master.py -q
```

后两项学习专用诊断设置实际`SSS_PYTHON`，并将付费学习/评分策略显式置空；Linux另运行完整`tests/test_harless_ppt_learning.mjs`。私有命令、各轮失败及最终日志在`.local/ppt-production-closure-20261108/`。没有跑全仓回归。

## 成本、交接与结论

制作、学习、Judge新增模型请求均0；原账本仍18921，未重置。没有新增费用对照，不宣称真实净降费；开发/CPU/人工时间未折价。本次库兼容导出不改变原MCP schema/读取IR，不新增训练任务或质量/收益晋级。

后端已修复本轮已定位的连续改页准入、固定收尾误拦和评分默认启用问题；关闭评分后，Linux单路学习/认证/后继晋级诊断正常。上线前仍需使用最终源码正常重新认证原学习程序，不能手改旧停用状态或把本次范围检查当新真实任务验收。

前端及单结果入口按用户要求暂缓。交接发现：公共聊天的`presentation=single`仍用历史`baseline`存储槽，桥接`prepare`会据槽名选普通模式，不能只隐藏普通组就认定优化已启用。负责对接的对话需将PPT单结果实际任务接至优化执行，并核对task的`mode/rsi/library`；`session/prompt.mode`仍是原生queue等发送策略，不能改成execute。内部双组入口保留原模式。不在本轮改这块接线。

因此本轮可以声明后端修复及上述诊断通过，不能声明正式上线、主聊天默认优化已对接、Windows/Mac全链路通过、Judge恢复有效评分或真实费用已下降。旧真实失败与质量瑕疵全部保留。
