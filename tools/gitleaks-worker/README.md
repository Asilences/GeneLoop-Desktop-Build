# Gitleaks 本地复用适配器

复用官方 Gitleaks `v8.30.0`，没有新增秘密识别规则。固定 Go `1.25.4`，依赖锁定于 `go.mod` / `go.sum`，使用与官方 release 相同的 `gore2regex` build tag。上游：[stdin入口](https://github.com/gitleaks/gitleaks/blob/v8.30.0/cmd/stdin.go)、[Detector API](https://github.com/gitleaks/gitleaks/blob/v8.30.0/detect/detect.go)、[MIT许可](https://github.com/gitleaks/gitleaks/blob/v8.30.0/LICENSE)。

只在启动时编译官方默认规则；每次请求新建 Detector，保持 `IgnoreGitleaksAllow=true`、`MaxDecodeDepth=2`、`MaxArchiveDepth=0`，通过相同 `DetectSource` / `sources.File` 入口检测。每个请求独立的findings、上下文、超时和buffer在结束后丢弃；输出只有固定握手和0/1/2状态，不返回原文或命中内容。官方 File 对不同 Reader 的分块可能不同，必须用长文/边界样例和原CLI对照，不能仅因API相同宣称完全等价。

传输为8字节大端长度加UTF-8原文；最大512MiB，单次8秒限时。Python公共入口更严格的输入限额不变。常驻的是受限本地工具进程，没有监听端口或网络接口，随宿主退出/管道关闭结束，不是正式服务生命周期入口。

在独立构建环境准备固定Go后运行：

```sh
cd tools/gitleaks-worker
go mod verify
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOAMD64=v1 GOTOOLCHAIN=local go build -mod=readonly -trimpath -buildvcs=false -tags=gore2regex -ldflags='-s -w' -o /PRIVATE/gitleaks-worker .
```

Windows改为`GOOS=windows`，输出`.exe`。`config/rsi-gitleaks-worker-tools.json`固定两平台二进制、默认规则、正则引擎和构建源码摘要；不匹配即拒绝，不能更新摘要绕过未经审阅的实现。构建产物留私有目录，当前未制作安装器或正式部署。

宿主以`SSS_RSI_GITLEAKS_WORKER`指定已核验二进制，未指定时沿用原CLI。`SSS_RSI_GITLEAKS_DEDUP=1`只允许同事务、同PID、同规则/工具、完全相同UTF-8字节的已完成clear结果复用，最多64项、只留摘要、不跨请求。每个逻辑输入/输出检查仍核验实际二进制字节，失败和命中不缓存，子进程故障无原文回退。
