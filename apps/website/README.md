# GeneLoop 官网

官网页眉和首页共用居中的内容宽度。首屏在宽屏上采用文字与递归动画并排布局，在窄屏上改为上下布局。页面支持中文与英文切换。

品牌和平面延展请参阅 [平面与视觉设计规范](DESIGN.md)。

## 页面

- `index.html`：官网，三种产品入口、研究方向和愿景。
- `desktop.html`、`dsh-plugin.html`：桌面端和 DSH 插件介绍。
- `journal.html`：Blog 索引，收录发布文章、学术论文和技术报告。
- `geneloop-launch.html`：发布文章，中英文沿用站点语言切换。
- `geneloop-evaluation.html`：评估与方法报告，以提供的中文原稿为准。
- `join.html`：保留的招募页面，使用已提供的招募表单；官网导航不展示此入口。

## 本地查看

在仓库根目录执行：

```sh
python -m http.server 8090 --bind 127.0.0.1 --directory apps/website
```

打开 `http://127.0.0.1:8090/`。这是一份无需构建的静态网站，可以将本目录直接作为静态站点根目录部署。字体和脚本随同静态目录发布。

Web 产品入口指向现有 `https://geneloop.ai/login?theme=lattice`。本目录不提供账号接口、不启动后端，也不包含本机 API 转发或工作区模拟逻辑。

## 正式官网

官网改动先通过 PR 合并到 `main`，再从合并提交的 `apps/website` 制作静态发布包。静态前置使用同一提交中的 [website-front.mjs](../../scripts/website-front.mjs)，负责官网路由和视频分段读取。发布后核对首页、工作区返回官网的 `/?home`、产品页、资源和视频分段。

## 登录、加载与工作区

登录与加载页的分形界面位于 [`src/adapters/web/account/harless_account.html`](../../src/adapters/web/account/harless_account.html)，Web 工作区样式位于 [`src/adapters/web/geneloop_theme.css`](../../src/adapters/web/geneloop_theme.css)，独立桌面工作区位于 [`apps/desktop/ui/desktop/`](../desktop/ui/desktop/)。它们复用官网分形风格和字体。

这些应用页面需要相应的账号服务和工作区运行环境；仅部署本目录的静态官网不会启动它们。

登录页的语言菜单和插画布局位于 `src/adapters/web/account/harless_account.html`。语言菜单采用高对比配色，分形的渐隐边缘与标题区之间保留 16 px。已在本地浏览器检查 1280×720、821×720 和 390×844 下的布局、键盘切换及语言记忆。

## 资源与验证

站点资源包括分形图标、字体和首页的 7 秒剪辑案例。字体授权见 `assets/fonts/FONT-LICENSES.txt`，视频素材署名与许可随案例展示。

首页第二屏回放已验收的四镜头成片，四个切点可用鼠标或键盘跳转。已在 320、390、768、1440 px 下核对中英文排版、播放器和程序来源说明。
