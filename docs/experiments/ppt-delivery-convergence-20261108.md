# PPT 成品返回逻辑收敛：本机无模型验证

## 问题与范围

上一组真实对照中，普通组已有可读PPTX/PDF和逐页PNG，但额外放大图未登记，导致整包`present`被拒，最终由实验操作者取消。该失败保留在[真实对照记录](ppt-delivery-fixed-pair-20261108.md)，不追改为成功或降费。

本轮按用户要求简化交付，仅做必要本机检查，不新增制作、学习或Judge模型请求，不提交、更新PR或部署。修改属于两组共用工程底座，不是新学得Motif。

## 实现与数据流

1. `finalize_ppt`仍完成字体/格式检查、可编辑PPTX、Office PDF和逐页PNG，然后一次登记当前项目成品。完整依赖、环境核验及缓存仍在导出阶段生效。
2. 私有任务目录新增`ppt-delivery-receipts/current-<project-digest>.json`，登记本项目最后选择的成功导出；命中成功缓存时也更新登记。以此选择成品，不按mtime排序。旧任务无登记时兼容哈希回执；已有登记时不回退到旧稿，登记损坏也不复活旧回执。
3. `present`只核对已登记稿件的输入字节、源页面/备注文件集合与所选输出字节，不重新认证整个项目、导出程序或运行环境，不重新执行导出和质量评审。新增/删除页面、改图件或备注使旧稿失效；mtime、scratch和额外诊断报告不使成品失效。未变页面/预览可复用。
4. 随有效PPTX/PDF返回的附加PNG若缺失、过期、未登记或被篡改，跳过该PNG并说明，其余有效成品正常交付。单独请求不合格PNG、旧/损坏PPTX/PDF仍不能伪报成功。正式逐页Office渲染及任务完成验收继续保留。
5. Harness参数冻结，宿主不改原调用，而是在同一授权、取消信号和父调用下续接一次筛选后的原生`present`。原生下载事件与字节证明只包含实际返回文件，附加图没有伪下载条目。通用文件证明按原生结果的请求子集核验。
6. 适配Skill、提示和运行策略同步；PPT继续仅制作、编辑及交付前PDF/图片检查，不增加音视频流程。

## 版本与复现

- 分支`codex/ppt-managed-learning-20261104`，HEAD `8988de79bc97d7a7a8a4410fe0f4e91688fecc95`，含此前及本轮未提交修改。
- 最终本地配置选择PPT117/Paper119；PPT116/Paper118为中间候选，旧库保留。兼容导出保持原MCP schema、读取IR和证据，不新增训练或质量/收益晋级。
- 隔离服务器仍为PPT114/Paper116，本轮未启用修复或重启，累计账本18921未改，正式服务不变。
- Windows本机Node v24.19.0、Python 3.11，私有日志在`.local/ppt-delivery-convergence-20261108/`。

```powershell
node --experimental-strip-types --test tests/test_ppt_delivery_pipeline.mjs tests/test_geneloop_native_work.mjs tests/test_ppt_write_tool.mjs tests/test_ppt_write_runtime.mjs tests/test_ppt_execution.mjs
node --experimental-strip-types --test --test-name-pattern='native PPT completion|actual PPT adapter completion' tests/test_dsh_web_tasks.mjs
python -m pytest tests/test_ppt_preview.py tests/test_ppt_master.py -q
```

第二条诊断设置`SSS_PYTHON`为实际解释器；本机文件检查使用正常临时目录及足够权限，没有弱化产品文件检查。

## 结果与失败

| 检查 | 最终结果 |
| --- | --- |
| 交付、原生文件返回、连续程序、执行层 | 53通过，0失败 |
| 实际任务适配器：缺成品拒绝完成、交付快照冻结 | 2通过，0失败 |
| 固定预览与PPT场景/新库入口 | 23通过，1跳过 |

跳过的是当前Windows账号不能创建符号链接的用例，不表示该边界已在本机完整验收。检查使用真实本地文件与官方原生工具Runtime；诊断文件不是本轮重新制作的真实PPT，不把它们等同于模型生成、Office重新渲染或桌面UAT。按用户要求未跑全仓回归。

新增用例复现夹带缺失附加图的整包交付：仅产生一次真正交付事件，PPTX/PDF/页面图有下载证明，附加图无下载条目；源/备注变化、加页、主稿损坏、旧稿选择、伪装后缀、其他任务/过期预览继续拒绝。

中间失败也保留：受限临时目录禁止realpath/硬链接，切换正常本机权限后解决；随后发现原生输出格式化覆盖跳过说明（33通过/1失败），已改用公开post-execute阶段附加说明并通过。未包装成首跑全绿。

## 成本、结论与下一步

本轮制作、学习、Judge新增API请求均0，没有新增模型费用；本机开发/CPU/人工未折价。没有新增成本对照，不据此宣布真实请求或费用下降。

**本次“附加图阻断整包、返回阶段重复认证、旧成品选择”已在本机代码及范围检查中收敛；整套端到端链路仍不能宣称完全收敛。** 上一轮取消/重启后的普通会话改页准入400、复杂Shell收尾误拦、Judge无有效评分、内容/版式瑕疵，本轮未修复或重新验收。原生模板编辑、Mac/Windows完整本机执行及服务器启用后的真实模型行为也不由这些检查证明。

后续优先解决原会话准入错误并统一安全收尾；Judge独立排查，不触发交付循环。未经新指示，不扩跑、不PR、不部署。
