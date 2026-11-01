# 视频网页场景集成（2026-11-01）

服务器现网 2901c35b 与运维 b58a79b6、GitHub main 2603388 在独立服务器分支合并。历史发布同名库完整保留到 motif-libraries/server-20261031；原学习 IR、在线程序、MCP schema、task、来源证据不重训、不改写。

新增 video-editing 场景，使用 /video 选择，与 Paper、PPT、Data 并列。网页使用原 DSH 模型循环和会话/计量流程，Agent 自行选择素材、编写 TSX 时间线并调用原 Remotion 工具实际渲染、探测、完整解码和读帧。尚未通过晋级的视频实验 Motif 不发布，不标记本场景已启用 Motif。

新增 web_server.py 只连接本会话 inputs 和固定私有渲染 broker。runtime/image 由管理员固定，调用者不能指定挂载、凭据或网络；容器 network none、原件和依赖只读、仅本会话项目可写。任务 grant 每轮刷新，来源 SHA256、源码版本和完整解码回执绑定当前 task。结果目录中的 MP4、TSX 经哈希核对后形成账户内不可变交付副本；网页右栏支持播放、源码查看和下载。取消或连接关闭清理本次容器。

Paper/PPT 的兼容重导出仅审阅共享能力提示、只读 /artifacts 路径、会话适配、固定渲染 broker、注册与交付逻辑差异。reexport-video-web-compat.py 明列源码差异，复用原导出/校验器；5 个不可变文件逐字节一致，旧库不删除。新增源代码锁不代表新训练或视频效果认证。

依赖：服务器固定 Remotion 4.0.539、React19.1、FFmpeg、Chromium 的只读安装和不可变 Docker image。私有部署提供 memberSceneDeployment.videoRenderer、videoRendererConfig 和 ownerCommandOutput；通过 prepare-release-scenes.py 生成 owner/member 一致的策略快照，再用 npm run service 发布。未部署 renderer 时菜单注明不可用。私有配置、原日志、账户、凭据、素材和生成视频不得提交 Git。

范围：当前沿用平台上传每文件20MB、交付每文件30MB的边界；短视频渲染已做真实预检。该范围不能代表长视频、4K、高并发渲染、自动语音理解或任意格式都已验证。网页真实任务和全量回归结果随后补充。
