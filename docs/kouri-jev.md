# Kouri JEV 本地调用

JEV 通过 `POST https://api.kourichat.com/v1/systemone` 提供结构化判断，独立于 DeepSeek 的 `/v1/chat/completions`。当前客户端实现用户提供的 `noul` 与 `choice` 两种问题类型，保留上游 `answers`、实际模型、概率、用量及其他返回字段。`noul` 原样返回数值；不把它强制转换成布尔值，也不假定通用阈值。

## 使用

需要 Node 22.18+，不增加依赖。进入当前项目检出目录后运行：

```sh
# 显示帮助，无付费调用
npm run jev -- --help

# 真实调用：用户提供的退款紧急度、归属团队示例
npm run jev -- --example

# 真实调用：构造的文件正文分类示例
npm run jev -- --input examples/kouri-jev/file-judgement.json

# 自定义 JSON，也支持 --input - 从标准输入读取
npm run jev -- --input request.json --records .local/jev/runs
```

自动读取仓库被忽略的 `.env`。私有配置路径优先级为 `--config`、`KOURI_JEV_CONFIG`、`SSS_FILE_PROVIDER_CONFIG`；沿用现有 Kouri 配置即可。配置文件必须为受保护的普通文件，包含 `KOURI_BASE_URL=https://api.kourichat.com/v1` 和 `KOURI_API_KEY`。不要把密钥写进命令行、示例 JSON 或版本库。客户端只在内存读取凭证，不向环境或子进程导出密钥，且禁止 HTTP 重定向。

程序调用接口：

```ts
import { judgeWithJev } from './src/adapters/kouri_jev.ts';
const { result, accounting, record_directory } = await judgeWithJev({
  state: '当前已获准读取的正文或任务状态',
  questions: {
    urgent: { type: 'noul', instructions: '当前事项是否紧急？' },
    category: {
      type: 'choice', instructions: '选择归属，信息不足选择 unknown',
      criteria: { invoice: '票据', contract: '合同', unknown: '信息不足' },
    },
  },
});
```

`judgeWithJev` 接受可选 `config`、`recordRoot`、`timeoutMs` 和 `signal`。默认120秒为传输超时，可覆盖；没有新增请求、费用或输出配额，没有自动重试。取消或超时可能已产生费用，保留失败记录后由调用方决定后续操作。

## 记录与使用边界

每次调用独立写入 `.local/jev/runs/<UUID>/`，目录700、文件600。包含原始请求、开始记录、HTTP状态及请求ID、原始响应正文，以及成功或失败记录。`started.json` 存在而无终态表示调用被中断，不能据此视为未计费。凭证不写入记录。输入正文和返回仍可能含私有资料，整份目录应按私有运行数据保管。

`accounting.reported_usage` 与 `reported_cost` 原样记录上游报告；币种与账单未核实，分别为 `currency:null`、`invoice_verified:false`。缺失费用标记未知，不记为零，也不套用 DeepSeek 聊天费率。这些是独立 JEV 调用账目，不冒充原 File 认证账本的成本。

File 运行时通过已认证学习程序调用此客户端。只有当前任务与证书、工具契约和文件状态相符时，才把范围明确的判断交给 JEV。工具仍由原 File MCP 执行，并沿用原任务授权。局部判断与独立 Pro 质量评审分开。配置和入口见[文件管理说明](../scenarios/file-management/README.md)。

2026-11-10 已用现有私有凭证真实验证退款示例，HTTP200，实际模型 `jev-1.14.0`，`urgent.noul=0.81`、`team.choice=billing`。详细调用、构造文件正文测试、费用与限制见本地实验记录。

## File实验接入（2026-11-10）

在上述传输客户端之上新增场景中立的 `typed_decisions.ts`，以及独立 File证据/参数绑定适配器。首轮已经完成真实决策校准、认证及18次试点；尚未取得整体降本，日常 `/file` 默认策略保持。公共模块不依赖 File存储目录，账号计量通过注入的meter关联原账本。参见[接口记录](interfaces.md#类型化决策与-file-实验端口2026-11-10)和本地实验记录。
