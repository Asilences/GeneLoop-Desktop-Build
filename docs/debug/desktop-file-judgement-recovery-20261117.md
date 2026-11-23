# Windows 0.4.0：File 私有判断与原任务恢复

本轮在 PR #171 的桌面主聊天接入 #170 的有界 JEV 判断和原任务恢复，版本仍为 0.4.0。六场景工具保留，安装包仅本地交付。

## 数据流与范围

- 绑定本机文件夹后，在原主聊天发送文件管理消息。工具只读取已授权目录的实际字节，并核对来源 SHA256。
- 网关为当前账号的 File 任务声明 fileJev 能力与不可逆账号摘要 fileJevAccount；只有配置了原账号判断上下文时，桌面才注册 local_file_judge。其他场景的凭证不能调用此判断接口。
- 判断使用 #170 原有 typed_decisions.ts、run-typed-decision.mjs 和 decision-meter.py；提供商密钥留在服务器，原账号判断账本继续记录。判断结果不是修改文件的授权，副本操作仍需原预览确认。
- 每次判断绑定账号、原本机会话、问题及来源内容。客户端和服务器均复用同一原结果。服务器在启动 CLI 前原子登记请求；中断、启动失败或不明结果不能自动重新发起付费调用。币种未核实的费用保留为未知。
- 主聊天为未完成的 File 消息显示“恢复原任务”。重新打开应用后，继续同一任务 ID、同一 DSH 会话与原 MCP 工作目录，而不是创建另一个任务。原 read_task 范围、来源版本、工具目录和执行器版本需一致。
- 管理工作流补齐 #170 的 script_catalog、inspect_script_result、run_script。桌面映射从 132 增至 135 项。

这轮提供可供原 Agent 选择的有界判断工具与恢复入口，不改上游 DSH 核心，也不把工具可用等同于学习收益或所有 File 策略已获得降本。

## 后端配置

已有网页账号可以复用。服务端源码包含新接口；仅更新客户端不会替正式网关部署或生成账号的私有判断配置。

在原 desktopLocalModel 配置中登记账号自己的 #170 判断上下文：

~~~json
{
  "desktopLocalModel": {
    "accountIds": ["EXISTING_ACCOUNT_ID"],
    "jev": {
      "accounts": {
        "EXISTING_ACCOUNT_ID": {
          "config": "/ABSOLUTE/PRIVATE/provider.env",
          "meterContext": "/ABSOLUTE/PROJECT/.local/account/decision-meter.json",
          "python": "/ABSOLUTE/PYTHON"
        }
      }
    }
  }
}
~~~

config 是原 Kouri 私有凭据文件；meterContext 是已有 geneloop-decision-account-v1 上下文，owner 必须等于登录账号，关联原私有 state_root/pool。使用原 decision_accounting.py 的权限、账目与准入规则：零预算不允许付费，有限预算在 JEV 定价未验证时不放行，不能通过另建无限预算来替换正式账号的有限授权。示例不是完整网关启动计划。

File lease 额外返回 fileJev:true。POST /api/harless/desktop-model/v1/systemone 使用同一 Bearer 任务凭证，提交 {request_id,packet}，返回原 result、decision、accounting 及 reused；未知结果返回 409。账号 owner 由网关注入，不信任客户端填写值。

V100 本轮验证发现：加载完整网关模块后，同进程 HTTPS HEAD 即可使旧系统的 Node 原生进程退出；独立判断进程可正常调用。桌面桥因此复用已有单次 CLI 按需启动，完成即退出，不新增常驻服务。该机还需在私有启动环境使用已验证的 IPv4 选项；没有将它强加给所有部署。

## 验证与边界

- Windows 类型/界面检查 20 项；判断、任务凭证和网络出口定向 14 项；服务器原子登记、跨实例恢复和账号拒绝回归 2 项通过。
- 实际 Electron、DSH worker 和 File MCP 完成“打开管理工作流 → 读取原任务 → 判断 → 取消 → 销毁控制器/重开 → 恢复工具目录和原范围 → 复用判断 → 写报告”。8 次协议模型响应、1 次夹具 JEV HTTP，原文件字节保持；不算真实模型效果。
- 同一恢复诊断也直接加载最终 Windows app.asar、运行时和随包工具通过；不借用开发依赖。
- 原生 Host UI 7 项和实际场景注册库的独立 renderer 诊断通过。原 UI 脚本补上显式选择云端工作区、input 事件和当前主题断言。
- V100 隔离网关以真实试用账号登录、获取 File lease 后，真实 JEV 将固定合成票据判为 invoice；实际模型 typesafe/jev-1.14-20261014，验收调用 input_tokens=702、output_tokens=38、上游报告 cost=0.000029484。本机缓存同时绑定服务地址与登录账号；本机缓存与服务器端同请求均 reused:true，只有一次上游调用。币种未知、未对账，不换算成美元。
- 调试中另有独立 JEV 成功和失败/被中断的尝试，原记录保留，不把未知计费记为零；原聊天累计账本、请求上限和美元费用上限未改。
- 完整 npm test 已执行，仍未全绿：Python 3388 通过、172 失败、30 错误、340 跳过；Node runner 1805 通过、29 失败、95 跳过。旧 PR #171 同环境记录已有大量 Windows 基线失败。不同项在未修改的 26727774 副本复核，文献用例另独立 29/29 通过；不能将本轮结果宣称为全量通过。原始与对照结果仅存本地 .local/file171-20261116/。
- 未重做 main 的全量基线，未做新 Mac 构建，未证明复杂任务质量或 P0 效率收益。正式网关与正式账号未部署；原试用网关保留，新的隔离测试网关仅用于本轮验收。

本机可重跑：

~~~powershell
node --test tests/test_desktop_file_decisions.mjs tests/test_desktop_file_decision_host.mjs tests/test_desktop_model_capabilities.mjs
npm --prefix apps/desktop run check
npm --prefix apps/desktop run check:tool-parity
# 准备好本机工具环境后：
node apps/desktop/scripts/check-file-recovery.mjs
# 或把 GENELOOP_FILE_RECOVERY_PACKAGE 指向 win-unpacked，检查最终安装资源
~~~
