# GeneLoop Desktop

首阶段是 Windows x64 桌面宿主与本地打包界面。聊天、侧栏、设置、文件预览、主题和场景交互来自同一份 GeneLoop/DSH 客户端源码；Agent、MCP、学习和模型调用仍在服务器执行。它不会直接整理电脑目录，也不包含本机 Agent。

## 使用与执行位置

- 安装后默认连接 `https://geneloop.ai/`，沿用网页账号。服务器是否提供某个场景、该场景是否可用，以账号的实际配置为准。
- 论文、PPT、数据、文件管理、视频等入口复用现有场景菜单，不重新实现场景 Agent，也不需要用户另装插件。
- 上传将选中文件的副本发送到服务器；产物通过原有认证通道预览和下载。文件读写确认、计量、取消与权限检查仍由原服务执行。
- Windows 关闭窗口时隐藏到托盘，点击托盘恢复；应用菜单或托盘的“退出”结束客户端。客户端不主动取消服务器任务，任务状态仍以服务器为准。
- 应用菜单提供连接设置、重新连接、最近下载的位置和退出；`Ctrl+,` 打开连接设置，`Ctrl+R` 重新连接。重连不自动重发消息。
- 当前没有自动更新服务；安装包为本地试用产物，生产签名、更新发布及其他平台验收另行完成。

## 实现边界

`apps/desktop/` 是独立 TypeScript/Electron 工程，拥有窗口、托盘、下载与生命周期。安装资源包含固定 DSH `0.1.5-rc.3` 的 Web 前端、客户端模块及仓库的 GeneLoop 品牌、主题、工作区和场景客户端。

`LocalFrontendHost` 在桌面会话中提供这些静态资源；只从原服务读取结构化 boot JSON、认证、会话/API、事件流及用户文件。服务器整站 HTML 不作为工作区执行。保留真实 HTTPS origin，以沿用 HttpOnly Cookie、WebSocket 和原服务的同源检查；不关闭 Web 安全或证书验证。

前端入口资源、客户端 ID 或依赖声明不兼容时明确提示更新，不静默退回远程 UI 脚本。这些检查不能识别所有“声明相同但源码不同”的变化，GeneLoop 自定义客户端与服务器仍需配套发布，尚未验证任意未来版本兼容。原生启动请求保留 `/starting` 与 `/login` 的真实跳转，历史入口回到本地工作区；账户页面沿用网关 CSP。当前并未升级或修改上游 Harness。

连接设置和 Cookie 保存在 Electron 的本机用户数据目录，各服务器使用不同会话分区。安装包不包含 API Key、账号密码、服务器私有配置或运行日志。更换服务器不会迁移原账号资料；服务器侧账号、工作区和累计计量不随客户端升级清零。

## 开发与构建

构建建议 Node 24；桌面工程要求 Node 22.18+。从 Git 检出后：

```powershell
npm run desktop:setup
npm run desktop:check
npm run desktop:dev
npm run desktop:build
npm --prefix apps/desktop run smoke:packaged
```

桌面依赖及锁文件位于 `apps/desktop/`，不改变根运行时依赖。`desktop:build` 生成 Windows x64 NSIS 安装包到 `apps/desktop/release/`，显式禁止自动发布；最终用户运行安装包不需要 Git、Node 或 Python。`smoke:packaged` 在独立用户目录启动实际打包程序，只读检查公开登录页和 ASAR 资源，关闭时仅清理它持有的进程树；不执行安装器或登录账号。

`GENELOOP_DESKTOP_URL` 可指定 HTTPS 服务器根地址；优先于保存的连接设置，不接受令牌、用户名/密码、路径或查询参数。仅未打包开发模式可用 `GENELOOP_DESKTOP_ALLOW_HTTP_LOOPBACK=1` 连接本机 HTTP fixture；`GENELOOP_DESKTOP_USER_DATA_DIR` 也仅供未打包调试隔离。它们不是本机 Agent 模式。

协议与 UI 诊断需先按主 README 安装根依赖及 Python SDK，再执行：

```powershell
npm run desktop:smoke
npm run desktop:smoke -- --public
```

诊断通过原 `npm run web` 启动唯一 RUN_ID 的本机 mock Host，校验 127.0.0.1、私有输出路径和禁用真实模型后，才创建诊断工作区/空会话；结束时只清理本次测试持有的进程树。`--public` 额外只读检查正式服务登录入口，不登录、发消息或创建生产数据。这些是传输/UI 检查，不代表真实 Agent 交付验收。

当前验证、限制及接手入口见 [桌面交接](handoffs/desktop.md)。后续本机执行应复用当前界面和执行端接缝，逐场景适配运行依赖与权限，不另建一套聊天系统。
