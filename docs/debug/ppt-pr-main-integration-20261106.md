# PPT Agent PR前审核与main整合

- 范围：将通用PPT执行与交付、页面学习及写页轨迹候选接线整理为可评审分支。不是部署，不将未认证的写页能力宣传为真实RSI成功。
- 基线：`origin/main=cdc3a6a9c048f0c6e6ee222e649de1ad9292c143`。本轮快照`7b6307a9`，分支`codex/ppt-managed-learning-20261104`。原正式服务、107隔离实例、私有成品和账本不变。
- 主线核对：PR159公共RSI默认私有、分享预览和脱敏；PR160 Kouri模型目录与路由；PR157文档分类及PR158协作要求均保留。首次查询时无开放PR；后续出现PR161（库界面）和PR162（公共脱敏），均未擅自并入。未合入桌面本机Runtime仅作参考，未应用过期补丁。

## 审核与修复

1. 原生Skill改为GeneLoop精简入口；设计/内容判断留给模型，字体、参数、文件版本和Office交付走共用执行层。baseline共用交付底座，优化工具只向Execute开放。
2. 仅有页面组件时不再展示`execute_ppt_program/release_ppt_program`；必须有实际认证写页程序。此处消除无效接口试用，不强迫使用不适用组件。
3. 保留main中的`privacy_projection=True`和默认私有策略。公共RSI兼容表仅更新已核对的`learn-web-ppt-tasks.py`与`dsh_web_tasks.ts`精确当前哈希；旧认证哈希及未知版本拒绝保留。
4. 原始PPT82/Paper84的library、online manifest、task、schema和source evidence各五份文件逐字节保留。新PPT108/Paper110绑定当前源码226/263项代码锁，兼容导出0模型请求、0训练任务、无质量/收益晋级。Paper仅因共享运行时变化同步兼容库。
5. 审核发现9个代码/配置文件在Windows使用CRLF，Git检出为LF后会令原始字节代码锁失效。已统一为仓库LF并重导出候选，旧CRLF候选保留私有。暂存区实际Git字节核对226/263项全部一致。
6. 66套未追踪中间库、旧107/109候选及未接通桌面补丁移到忽略的`.local/pr-prep-20261106/`，不进入最终PR文件差异。main原有历史库不删除。

## 验证

- Windows正常权限：`node --experimental-strip-types --test tests/test_ppt_component_tool.mjs`，6通过。受限环境曾阻止文件原子替换，正常权限复验通过，未删除守卫。
- 导出：`python scripts/reexport-ppt-managed-compat.py --ppt-agent-delivery-learning --write --update-registry --validation-record docs/debug/ppt-pr-main-integration-20261106.md`。生成108/110，原schema和online program一致，当前全部代码锁匹配。
- Linux：合并后的公开源码同步全新隔离目录。`npm test`中的Python全量为3142通过、220跳过、49警告、1失败（1379.71秒）；唯一失败为成员命名空间夹具仍期待原版Skill正文。改为逐字核对GeneLoop适配正文，保留原版资源只读/不变及账户隔离检查后，该文件定向复测1通过（12.30秒）。未重复全量Python，不能将定向通过改写成全量重跑全绿。
- 最终LF代码的Node全量1725通过、11跳过、0失败（118.05秒）；续接生成检查、最终108/110实际加载、smoke（41.22秒）、motif:check（33.47秒）及rsi:check（9.49秒）均退出0。源码包SHA256：`169366dafe328812398945eccca8d29e4dca4fc34d72bc349ea560af13e22784`。不提交模型任务，不调用付费API。完整回归源码与最终Git内容只存在上述9文件换行及重新绑定的兼容库字节差异；回归后单独检查最终LF版本库加载，避免重复全量测试。
- 旧107的Python2512/Node1692结果只作为历史记录，不能替代本次整合检查。

## 已知边界与回退

真实连续写页/修订认证程序仍为0；本次没有独立B/O降费数字。现有只读续接和页面组件与新写入IR应分别评价。Windows共享模块诊断不等于完整桌面产品，Mac原机/本机写入宿主及平台认证未完成。正式Kouri文件/图像/模型能力和计价验收仍沿main未完成边界，不在本PR补做昂贵实验。

学习与Judge费用单列，原失败记录不改；详见[本轮实验收尾](../experiments/ppt-write-workflow-20261106-results.md)。回退须将源码、登记配置和配套兼容库成套恢复；不重置账本或改写旧pointer。正式运维仅用统一service入口。


## 发布与桌面接手

已推送`8865e12b`并创建[PR #163](https://github.com/jingyio/GeneLoop/pull/163)供桌面版审阅。GitHub连接器创建操作返回403，改用本机既有GitHub登录调用官方API成功，凭证不展示、不写入报告。未合并main或发布服务。

后续PR161新增库界面和登记版本、PR162扩展公共学习副本脱敏，会改变共享适配器或代码锁。合并者需保留三者语义，按最终源码重导出兼容库；不能直接选某一侧旧登记路径或放宽哈希守卫。桌面宿主仍负责本机工具实现与权限，共享执行器只续接受支持的已认证操作。

最终验证日志与原失败记录保留在私有`.local/pr-prep-20261106/integrated-validation/`。最终只修改一处测试预期及本交接说明，未改变已核对的运行时代码锁。GitHub PR与本地/服务器检查分别报告，不将本次检查冒充远端CI成功。
