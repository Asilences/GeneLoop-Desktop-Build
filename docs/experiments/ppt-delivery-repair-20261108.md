# PPT 交付完成判定与预览误拦修复

- 日期：2026-11-08；工作分支 `codex/ppt-managed-learning-20261104`，基于 `8988de79` 的未提交候选。
- 范围：修复 [上一组真实任务](ppt-cache-enabled-pair-20261107.md) 发现的预览误拦与缺成品仍报完成。保留全部失败、旧版、费用和评分；不新增模型请求、不扩跑制作实验、不更新 PR、不部署。

## 问题与实现

1. 优化稿选中组件后，正常图片裁剪与 `/tmp` 整理被统一 Bash 限制拒绝。新增双方共用的 `inspect_ppt_region`：只读当前任务有效导出回执中的 PNG，按原图像素裁剪/放大，宿主生成新预览并返回图片；PPT、原图和页面源码保持不变。转换由固定执行器完成，没有内部模型请求。受管组件继续禁止任意 Python、越权写页与静默弃用重做；仅额外放行字面量输出图片复制到本会话 `/tmp`，以及该目录的创建和只读列举。
2. 普通组只有 SVG 源文件仍被标记完成。现在记录本轮开始时的项目版本和制作动作，结束时校验完整、有效且与当前源码/备注/依赖相符的宿主导出回执；缺 PPTX/PDF/逐页 PNG、导出失败、成品损坏或新增项目未导出均转为失败，不纳入成功轨迹学习。纯讨论和未改稿的演讲稿请求仍可正常结束。冻结交付快照失败也须报告失败。

代码：`src/adapters/ppt_delivery_pipeline.ts`、`ppt_preview_runner.py`、`ppt_write_tool.ts`、`dsh_web_tasks.ts`；适配说明：`scenarios/ppt_master/{SKILL.md,prompt.md,runtime-policy.md}`。共同工具不是新学得 Motif，不算 RSI 发现成果。

## 验证记录

- 首次诊断暴露原生 schema 不支持 `minimum/maximum`，已改为支持的枚举约束；原失败日志保留。
- 首次 Windows 范围回归存在旧源码版本锁失配、三项附件视觉链诊断失败，以及新增夹具未显式授权输出的问题。输出权限保持显式授权；夹具已纠正，不通过放宽产品权限规避失败。
- 最终范围结果如下，全部为无模型诊断，非新效果实验。原始诊断保存在 `.local/ppt-delivery-repair-20261108/`，不进入 Git。

| 环境/检查 | 结果 |
| --- | --- |
| Linux：交付、写入保护、完整聊天任务三个Node测试文件 | 146通过，2跳过，0失败；109.84秒 |
| Linux：真实PNG转换Python测试 | 15通过；0.86秒（含启动） |
| Linux：`npm run motif:check` | 通过；32.34秒，固定Provider诊断不计为真实模型调用 |
| Linux：现有隔离执行器→固定PNG裁剪→原生读图→会话临时复制 | 通过；90×60新图、1个原生图片块、原图SHA不变，内部模型请求0 |
| Windows：相同三个Node文件 | 143通过，2跳过，3失败；133.02秒 |
| Windows：真实PNG转换Python测试 | 14通过，1项符号链接权限跳过 |

Linux独立副本为服务器私有目录`.local/ppt-delivery-repair-20261108`，使用既有Python3.12/Node22环境和依赖安装，没有启动新Web或切换现有实例。源码包3768个公共文件在解包后逐SHA核对；锁定PPT113/Paper115可以加载，原MCP schema及学得读取IR不变。制作、学习、Judge新增请求与费用均0，原累计账本不变。

Windows三项失败是：附件准备进度未进入视觉阶段两项、PDF历史视觉证据一项。同一批在Linux通过；另用合成PDF做最小无模型诊断，当前Windows指定解释器的受限子进程返回`pdf_text_extractor_unavailable`，没有发生视觉调用。父进程的PyMuPDF来自用户级Python311包目录且配置了`PYTHONPATH`；运行入口隔离环境未保证这套依赖可加载。未为变绿放宽子进程环境、权限或删除检查，保留为Windows环境未完成项。预览执行诊断另暴露两个夹具问题（每次返回新owner对象、原生session缺`requestHeader`），纠正夹具后通过；产品身份守卫未放宽。

最短无模型复现：

```text
python -m pytest tests/test_ppt_preview.py -q
node --experimental-strip-types --test tests/test_ppt_delivery_pipeline.mjs tests/test_ppt_write_tool.mjs tests/test_dsh_web_tasks.mjs
npm run motif:check
```

Node范围回归需设置`SSS_PYTHON`为对应项目解释器；测试夹具仅使用本机模拟端点。未再跑全仓回归，最后验证以此范围为准；本轮没有真实生成/同会话改页复验，不能宣布全部平台交付成功或稳定省费。

## 边界与回退

本轮只验证无模型执行及任务状态边界，不提供新的质量或降费结论。未开始任何制作动作、也未创建/更改项目的自然语言任务不由机械规则推断为必须导出；不承诺自动修复所有生成失败。预览工具只接受当前任务导出，旧任务成品须重新获得有效回执。原执行环境和权限限制保留，Windows/macOS 完整本机写页、Office 导出与命令宿主仍需设备验收，不能因路径规则兼容就宣称已支持。

PPT113/Paper115 为匹配本次源码的兼容候选，保留 PPT112/Paper114。新源码签名要求学习组件/连续程序重新认证后方可启用；不手改旧证书或停用状态。正式服务和现有隔离测试实例保持原版。
