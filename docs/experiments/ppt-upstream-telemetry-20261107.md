# 上游响应证据与三类费用分离

记录 ID：`ppt-upstream-telemetry-20261107`。基于[既有日志审计](ppt-upstream-routing-billing-audit-20261107.md)修补记录缺口；本轮不新增制作、学习或Judge请求，不扩跑真实实验，不提交、推送、更新PR或切换服务。旧轨迹、评分和累计账本不改。

## 修改范围与行为

`deepseek_cost_gate.py`、`file_cost_gate.py`在原转发路径旁记录`upstream_response`；共用`model_usage.py`的有限白名单投影。Web/File任务统计提供`cost_accounting`，旧兼容字段继续存在。

每次模型尝试单独记录：

- `requested_model`：经过别名映射后，实际发送体的模型ID；原回执`model`仍是预算使用的SDK模型ID。
- `response_model`、`response_id`、`system_fingerprint`：上游响应声明的值。流式响应首事件只有身份、末事件只有usage时，二者都保留；不能将上游声明视作底层权重认证。
- `request_ids`：只保留`x-request-id`、`request-id`、`x-correlation-id`、`x-amzn-requestid`、`x-amz-request-id`、`cf-ray`中合法的短标识，不记录其他响应头。`route`仅含scheme/host/port/path，不含凭证、查询串。
- `raw_usage`：保留原计数、缓存详情和cost的字段原值，包括总量不一致的情况。仅保存token/cost相关根字段、有限深度/数量的数值及数字字符串，货币/单位用白名单；不是完整响应字节。过滤时记录`raw_usage_status:filtered`及省略数量。正文、思考、choices、Cookie、认证头不入账目。
- `reported_cost`：保留`usage.cost`金额；未明确提供或无法识别币种/单位时为`unknown`，未返回金额时为`null`。不从模型名、配置费率或数字比例猜币种、折扣和单位。
- `http_status`、`outcome`、`response_complete`：区分上游HTTP响应、本机传输异常及未发送的凭证失败。异常仅保存类型，不保存可能含凭证的异常文本。截断响应已有的usage保留，但预算不据此释放；每次重试和同连接下一次请求都重新建立证据，不能继承前次费用或身份。
- `request_started_utc_epoch`：补记发送前时间；原`request_utc_epoch`保留其原有接近处理结束的语义，历史值不重写。

## 费用分离

| 任务统计路径 | 含义 | 限制 |
| --- | --- | --- |
| `cost_accounting.budget_reservation` | 原保守预算计量，单位USD | 用于限额，不是实付；未知请求的预留不释放 |
| `cost_accounting.configured_estimate` | 收到的可分类token按记录费率估算，单位USD | 保留缺usage、总量异常和未分类token数量，不是上游账单 |
| `cost_accounting.upstream_reported` | 上游`usage.cost`覆盖数量及按币种/单位分组金额 | 单位未知不合计；不与配置估费相加或替换，不当作发票 |

`reported_accounting.upstream_reported_costs`保留相同的上游费用汇总。只有响应完整、解析有效且明确标注同币种与同单位的金额才分组相加；不同单位分组，未知单位只统计请求数量，逐笔原值留私有账目。未返回费用、旧日志缺字段和连接中断均不记为零。所有`invoice_usd`仍为`null`。

原`estimated_cost_usd`仍是`budget_reserved_usd`兼容别名，新增`estimated_cost_usd_semantics`明确标为`compatibility_alias_of_budget_reserved_usd_not_spend`，避免改坏旧消费者。`cost_evidence`继续单独提供配置费率证据；预算准入、严格token校验、重试范围与累计账本规则不变。未将上游请求ID、原usage或完整头添加到聊天展示/取消回执的公开投影。

## 验证与证据

只做离线诊断：本机回环HTTP模拟上游、合成响应和原有计费/重试测试，没有云API。覆盖JSON、碎片SSE、首尾身份与usage分离、流首字节及时返回、浏览器断连后继续排空、截断/异常响应、缺usage、总token异常、File持久任务的延迟转发分支、同连接连续请求、不同费用单位、原账本恢复与权限拒绝。

最终Windows定向 **99项通过，17.76秒**。日志为`.local/ppt-upstream-telemetry-20261107/final-source-tests.log`，源码SHA及两套候选的加载验证为同目录`source-sha256.json`；兼容导出记录为`compat-export-verified.log`。首次受限本地执行遇Windows回环连接及临时文件替换权限限制（11失败/37通过），保留为环境失败，不能称为通过；允许本机测试后中间77项、97项通过，最终增加截断错误等覆盖后99项通过。候选导出也保留了一次Windows目录解析权限失败，允许访问后正常导出并重新加载成功。

复现命令（无模型）：

```powershell
python -m pytest tests/test_upstream_accounting.py tests/test_model_usage.py tests/test_deepseek_cost_gate.py tests/test_deepseek_cost_gate_stream.py tests/test_web_task_budget.py tests/test_model_api.py tests/test_provider_retry.py tests/test_geneloop_retry_metering.py tests/test_model_transport_capacity.py -q
python scripts/reexport-ppt-managed-compat.py --upstream-accounting-evidence --write --update-registry --validation-record docs/experiments/ppt-upstream-telemetry-20261107.md
```

按用户要求限定为计费、转发与重试相关验证，未重跑整套Python/Node或真实生成，不把前轮全量通过记为本轮全量通过。每个本机HTTP测试仅访问`127.0.0.1`。新增制作、学习、Judge云请求均为0，新增模型费用为0。

## 版本与边界

兼容导出入口`--upstream-accounting-evidence`已从PPT111/Paper113产生PPT112/Paper114候选，两个候选均由`load_product_bundle`重新加载通过；保留旧库、IR、学习证据和认证要求，并将`model_api.py`、`config/kouri-models.json`纳入新源码锁。仅更新源码与兼容锁，不代表学到了新能力或证明降费。旧库不覆盖，运行实例不切换。

历史制作响应已丢失的上游模型、request ID和cost不能回填。本轮改动只能让未来正常转发保存可核对证据，不证明当前缓存已改善，也不能确认供应商实付。学习与Judge继续单列；本轮二者新增费用均为0。Windows为本机验证；Mac没有实机验收，Linux运行实例仍保留旧版。
