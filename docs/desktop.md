# GeneLoop Desktop

0.2.0是独立桌面前端预览版。窗口、页面、组件、样式和交互状态均由 `apps/desktop/` 自己实现，只参考GeneLoop网页的视觉与场景；没有打包DSH网页前端、客户端插件图或远程网页脚本。Agent、场景工具和模型调用仍在所连接的服务器执行。

## 本机工作区 Windows 预览

侧栏「新建工作区」提供本机和云端两种类型。「文件」菜单的「打开本机文件夹」可用系统选择器直接添加或打开本机工作区。工作区右键和三点菜单的「编辑工作区」支持添加、更换或解除一个本机文件夹。云端工作区的绑定按服务器和账号保存在本机，云端会话继续在服务器执行。绑定后，可从工作区首页运行本机任务。

本机 Agent 以只读方式访问原始文件，只能在所选文件夹的 `GeneLoop 输出/` 下新建 Markdown 报告。输出目录在首次写入时创建，旧版已生成的报告保留在原位置。解除绑定和移除本机工作区仅修改应用记录。侧栏「工作区视图」保存分组、排序和归档筛选偏好。

每次运行建立一个本机 Agent，本机任务记录保存在桌面应用数据目录。预览界面暂未提供历史恢复。

首次真实验收使用独立服务器启动计划和试用账号。候选账号网关配置中加入 `"desktopLocalModel": {"accountIds": ["<隔离试用账号 ID>"]}`。保持原有预算代理、累计账本、服务入口和模型密钥。启用配置后，仅已登录且在名单中的账号能取得十分钟任务凭证，单账号同时一个本机任务。桌面使用该凭证调用 `deepseek-flash`，服务端在既有预算控制登记、绑定并结算。切断连接、撤销或超时后关闭模型转发。任务描述和必要文件片段发给云端模型。客户端不会收到供应商密钥。

开发构建先执行 `npm --prefix apps/desktop run runtime:stage`，然后使用现有 dev 入口。Windows x64 的 `pack` 和 `dist` 将锁定的 Harness 运行时封入 `resources/geneloop-runtime.asar`，Windows 原生模块和外部工具保存在相邻的 `.asar.unpacked` 目录。桌面界面仍来自本仓库。用 `npm --prefix apps/desktop run smoke:local-workspace` 运行回环诊断，或运行 `node apps/desktop/scripts/probe-local-runtime.mjs --installed "<安装目录>"` 验证实际安装中的 Agent 和文件工具。真实云端模型验收使用隔离服务和试用账号，并核对预算账本、产物、取消与重复提交。

## 使用与基线

- 默认连接 `https://geneloop.ai/`，使用同一个服务器账号、工作区和会话。桌面与浏览器分别保存登录Cookie，不复制服务器密钥或私有部署配置。
- Chat、PPT、论文校对、数据分析、文件管理、视频编辑从服务器目录读取；服务器不可用的场景保持不可用。界面入口齐全不等于六个场景均已通过真实任务验收。
- 场景选择按本轮发送序列化为服务器公开的斜杠命令，成功后回到Chat；模型选择保存成功后才提交消息，不截断正文。
- 选中文件只上传副本；服务器产物通过同一账号认证预览/下载。写操作请求需要明确确认，客户端不自动允许。关闭客户端不取消服务器任务；停止由显式操作发往服务器。
- Windows关闭窗口隐藏到托盘；应用菜单或托盘的“退出”结束应用。保留32px应用/编辑菜单和主题联动，没有顶部黑色状态条。`Ctrl+,` 修改连接，`Ctrl+R` 重连；重连读取状态，不自动重发。
- 设置包含主题、已归档、最近删除、账户与安全。清空最近删除先核对列表并明确确认；服务器继续负责归属、修订版本和忙碌状态校验。
- 本次没有修改用户安装、正式服务、账号资料或累计账本。安装包未签名，没有自动更新；目前只构建与诊断Windows x64。

用户指定的旧基线为 **0.1.5顶部黑条修复版**，标签 `geneloop-desktop-v0.1.5-baseline`、分支 `codex/geneloop-desktop-baseline`，commit `15af73e`。它仍打包整套网页客户端，仅作回退/对照。本次在 `codex/geneloop-desktop-independent-ui` 单独开发，冻结工作区不改动。

## 代码与接口

- `src/main.ts`、`workspace.ts`：桌面窗口、菜单、托盘、下载、生命周期；退出时先释放子视图和连接，再销毁窗口。
- `ui/desktop/index.html`、`desktop.css`：桌面自己的布局和视觉。
- `ui/desktop/api.js`：公开JSON RPC和WebSocket mux传输；`conversation.js`：日志/流式状态；`composer.js`：逐轮场景与附件序列化。
- `ui/desktop/app.js`、`components.js`、`comparison.js`、`panels.js`：桌面会话、场景选项、安全Markdown、双路结果、交付、问题和设置。没有复制网页组件实现，也没有另造Agent循环。
- `src/frontend.ts`：本地资源白名单，仅 `/api/` 转发至服务器；不获取整站HTML、boot JSON、插件脚本或未知UI。生产依赖为空，Electron自带运行时即可启动。
- `scripts/prepare-assets.mjs`：只复用透明品牌SVG并生成图标；manifest记录代码版本、是否未提交、独立资源摘要和公共场景目录。

保留原服务HTTPS origin、HttpOnly Cookie、原生WebSocket和来源校验。Electron的 `protocol.handle` 不携带普通请求Origin时，只按Chromium可信 `initiatorOrigin` 恢复同源Origin；跨源、不透明源、伪造头或无来源写请求被拒绝。不关闭Web安全/证书验证。

工作区无Node和窗口控制桥；外观preload只观察颜色，主进程校验当前同源主frame与hex颜色值。连接页面的窗口IPC只对安装包内主frame开放。安装器保留准确exe名查询，不按目录前缀匹配，也不强制结束用户进程。

## 开发和诊断

```powershell
npm --prefix apps/desktop ci
npm --prefix apps/desktop run dev
npm --prefix apps/desktop run check
npm --prefix apps/desktop run smoke:account
npm --prefix apps/desktop run smoke:renderer
npm --prefix apps/desktop run smoke -- --public
npm --prefix apps/desktop run dist -- --config.electronDist=node_modules/electron/dist
npm --prefix apps/desktop run smoke:packaged
```

`check` 验证传输与权限边界、日志投影和逐轮发送。`smoke:account` 使用原网关和本机临时合成账号，验证独立表单、密码拒绝、Cookie、刷新和退出；该夹具不启动Agent工作空间。`smoke:renderer` 使用确定性协议夹具验证双路结果、权限确认、人类问答、场景/模型保存顺序、文件预览及设置，不作为模型行为验收。`smoke` 启动原项目隔离mock Host，验证原生工作区/会话/RPC、上传与重连，**不发送模型任务**；`--public` 只读检查正式站未登录账号状态。

`smoke:packaged` 检查ASAR不含网页/生产Node依赖，再把整个应用复制到祖先无node_modules的临时目录运行；只读取公开未登录账号状态，不执行安装/卸载。诊断数据、截图和失败保存在 `apps/desktop/.local/validation/`，不提交。

上述测试均不证明真实模型效果。正式账号、六场景真实交付、评分/归档/清空/改密等服务器持久操作仍需隔离账号验收；不通过读取用户密码、复制浏览器Cookie或模拟回复补齐。本机Agent/工具执行属于下一阶段，模型仍可通过网络调用云服务。

当前版本与证据见[桌面交接](handoffs/desktop.md)和[独立前端记录](experiments/geneloop-desktop-independent-20261103.md)。
