/* English/Chinese UI copy. Text is assigned through DOM APIs, never evaluated. */
(()=>{if(window.GeneLoopI18n)return;const pairs={"Blog": "博客", "Explore": "探索", "Main navigation": "主导航", "GENELOOP home": "GENELOOP 首页", "Explore GENELOOP": "探索 GENELOOP", "Explore GENELOOP ↗": "探索 GENELOOP ↗", "Intelligence,": "智能，", "shaped by": "源于", "recursion.": "递归。", "Our research": "我们的研究", "Desktop": "桌面端", "DSH Plugin": "DSH 插件", "Web": "网页版", "What we learn": "我们所学", "Explore the research": "探索研究", "Experience": "经验", "Abstraction": "抽象", "Composition": "组合", "New capability": "新能力", "Skip to content": "跳转到正文", "Take intelligence beyond the known.": "让智能，走向未曾抵达之处", "RESEARCH NOTE / 001": "研究笔记 / 001", "should change": "应当改变", "what we can learn next.": "下一次学习的可能。", "From experience to building blocks": "一次任务之后，留下什么", "Where efficiency enters the loop": "把重复省下来，把探索接上去", "What we have observed": "从具体实验开始", "← Back to GENELOOP": "← 返回 GENELOOP", "GENELOOP turns experience into executable capabilities, then uses those capabilities to build new ones.": "GENELOOP 将经验转化为可执行的能力，再用这些能力构建新的能力。", "Access and release details will be shared here.": "产品开放与发布信息将在这里更新。", "A path toward recursive self-improvement through executable abstraction.": "让做过的事，成为下一次创造的起点。", "Human technology builds on accumulated foundations. A new generation of builders does not recreate every tool from the beginning. Reliable structures become the building blocks for what comes next. GENELOOP asks whether agents can develop a similar relationship with their own experience.": "技术向前推进，靠的不只是一次次从零开始。工具、方法和经验被留下来，后来者才能站在已有基础上继续构建。我们希望智能体也能如此：把一次任务中的有效做法，变成下一次可以直接使用的能力。", "Knowing how to complete a task is different from possessing a reliable, executable capability. An agent may successfully write a program and still repeat much of the reasoning, dependency checking, and debugging when a similar task appears.": "完成一次任务之后，究竟留下了什么？如果下次遇到相似问题，仍要重新推理、检查依赖、调试参数，那么成功就只停留在那一次对话里。我们希望留下的，是能够再次执行、再次检验的东西。", "GENELOOP learns executable programs from normal task traces. These capabilities can be matched, bound, validated, and reused in subsequent tasks. The next step is composition: using an existing capability as material for constructing a new one.": "GENELOOP 从任务过程里提取可执行程序，让经验有一个可以调用的形态。在新任务中，这些程序经过匹配、参数绑定和验证，再被实际使用。而已有能力也可以成为材料，参与下一种能力的构建。", "Reducing repeated work can release compute for exploration. If that exploration produces reliable higher-level abstractions, future execution and capability construction may become less costly in turn. This is the feedback loop we want to investigate.": "少做一些重复工作，就有机会把资源用在新的探索上。新的探索再沉淀为能力，服务后续任务——我们关心的，正是经验、能力与创造之间能否形成这样的循环。", "That goal does not necessarily require changes to model weights. An evolving collection of executable abstractions may change what an agent can accomplish within a fixed compute budget.": "这条路径不以修改模型权重为前提。随着可执行能力不断积累，智能体可以尝试在同样的计算预算里，完成更丰富的工作。", "Initial experiments provide local evidence for execution reuse and autonomous capability composition. In a five-paper BibTeX review experiment, model requests fell from 195 to 110 while the core check score remained 9 out of 10.": "初步实验为执行复用和自主能力组合提供了局部证据。在一次包含五篇论文的 BibTeX 审查实验中，模型请求从 195 次降至 110 次，核心检查得分保持为 9/10。", "In six parameterized video tasks, model requests fell from 44 to 30, but total tokens increased by about 7.8%, and independent quality review did not pass in every case. A separate recursive-construction experiment showed an agent building a cross-version consistency capability from an existing citation-review capability, passing four checks across two new paper projects.": "在六项参数化视频任务中，模型请求从 44 次降至 30 次，但总 token 数增加约 7.8%，且并非所有案例都通过独立质量评审。另一项递归构建实验中，智能体以已有引文审查能力为基础，构建了跨版本一致性能力，并在两个新论文项目上通过四项检查。", "Past capabilities should become the primitives of future creation.": "做过的事，应当为下一次创造留下基础。", "The goal is not only to do the same work more cheaply. It is to make the next capability easier to create.": "让经验真正有用：既服务眼前的工作，也为下一种能力铺路。", "Language": "语言", "A workspace for what comes next.": "面向下一步的工作空间。", "The desktop direction brings GENELOOP into a dedicated workspace, with richer functionality and a focus on de-identified experience sharing.": "在专属桌面工作区中使用 GENELOOP，连接工具与任务，积累经过验证的经验。", "Start where you already work.": "从现有工作流程开始。", "A plugin entry point for bringing GENELOOP into an existing workflow. Integration and compatibility details will accompany its release.": "通过插件把 GENELOOP 接入现有工作流程，集成与兼容信息会随版本发布。", "Structures that evolve.": "让结构持续演进，", "Capabilities that compound.": "让能力不断生长。", "From experience.": "把经验，", "To capability.": "变成可用的能力。", "Footer navigation": "页脚导航", "SHAPE THE NEXT ERA OF INTELLIGENCE": "共同塑造智能的下一个时代", "Toward": "迈向", "Recursive": "递归", "Self-Improvement.": "自我改进", "Turn experience into capability.": "经验成为能力", "Pursue discoveries": "追求", "that matter.": "真正重要的发现", "Progress that builds on itself": "让进步，拥有继续进步的能力", "Keep what experience teaches.": "经验成为能力", "An agent’s work should leave more than an answer. It should leave a capability.": "让智能体从经历中积累能够长期使用的能力", "Build with what you’ve learned.": "能力创造能力", "Use what already works to create what doesn’t yet exist.": "用已有能力发现、组合和构建新能力", "Get better at getting better.": "改进推动改进", "Push beyond doing more. Build intelligence that becomes better at advancing itself.": "每次突破，既拓展智能能做什么，也增强它继续突破的能力", "Join GENELOOP": "加入我们", "Make Intelligence Compound": "让每一次发现，打开下一次突破的可能", "Discovery builds on discovery.": "人类的进步，来自发现之上的新发现", "Turn experience into capability. Build what comes next.": "我们相信，智能也应如此：把经验积累为能力，再用已有能力探索尚未抵达的边界", "Independent minds": "我们寻找这样的人", "Ask the fundamental questions.": "我们寻找敢于提出根本问题、", "Challenge the accepted answers.": "挑战既定假设，", "Build what doesn’t exist yet.": "并把非传统想法付诸实践的人", "Think freely. Test rigorously.": "独立思考，严谨求证", "Make intelligence": "让进步，", "compound.": "推动下一次进步", "Products": "产品", "Back to products": "返回产品入口"};
Object.assign(pairs, {
  "Blog": "博客",
  "Featured": "项目介绍",
  "Publications": "学术论文",
  "Technical Reports": "评估报告",
  "Static Agents, and Computational Structures That Grow": "静态的 Agent，与会生长的计算结构",
  "GeneLoop: An Efficiency-Oriented Self-Improving System for LLM Agents": "GeneLoop：面向 LLM Agent 的效率自进化系统",
  "Online capability learning, verified reuse, execution efficiency, and learning overhead.": "在线能力学习、经核实的程序复用、执行效率与学习开销。",
  "Earlier research note": "早期研究笔记",
  "Back to Blog": "返回博客",
  "GeneLoop learns executable capabilities from real task traces, verifies them, and reuses them on new tasks.": "GeneLoop 从真实任务轨迹中学习可执行能力，认证后用于新的任务。",
  "Read Our Story": "阅读发布文章",
  "Evaluation Details": "查看评估详情",
  "Efficiency-Oriented": "面向效率的",
  "Self-Improving Agents": "自进化智能体",
  "GENELOOP — Efficiency-Oriented Self-Improving Agents": "GENELOOP — 面向效率的自进化智能体",
  "An agent that builds on its past work, accumulates reusable capabilities, and improves how it approaches new tasks.": "让智能体从过去的工作中积累能力，并在新的任务中不断改进自身的执行方式。",
  "Open GeneLoop": "打开 GeneLoop",
  "Learn More": "了解更多",
  "What Makes GeneLoop Different?": "GeneLoop 有何不同？",
  "GeneLoop turns useful computation from completed tasks into executable capabilities that can be reused, adapted, and combined in future work.": "GeneLoop 将已完成任务中的有效计算积累为可执行能力，并在新的工作中复用、适应和组合这些能力。",
  "From three shots to four": "从三镜头到四镜头",
  "How GeneLoop builds on completed work": "GeneLoop 如何从完成的任务中积累能力",
  "Concrete task": "具体任务",
  "The agent writes and runs Remotion code to deliver a three-shot edit.": "智能体编写并运行 Remotion 代码，交付三镜头成片。",
  "Executable abstraction": "可执行抽象",
  "GeneLoop extracts and verifies a timeline structure from the successful execution.": "GeneLoop 从成功执行中提取并认证时间线结构。",
  "Reuse and adaptation": "复用与适应",
  "For the four-shot edit, the agent binds new footage ranges, cut points, and labels to that structure.": "智能体给同一结构绑定新的素材区间、切点和标签，生成四镜头成片。",
  "Formation of new capabilities": "新能力的形成",
  "Each new execution can feed back into learning and help build future capabilities.": "新的执行经验可回到学习循环，为后续能力构造提供依据。",
  "Established computation can be executed directly, while the model focuses on unresolved parts of the task.": "已经掌握的计算可以直接执行，模型专注于任务中尚待解决的部分。",
  "Execution & results": "执行对照与实测",
  "Work with GeneLoop": "用 GeneLoop 开展工作",
  "Research documents · Presentations · Data analysis · Video editing · File workflows": "研究文档 · 演示文稿 · 数据分析 · 视频剪辑 · 文件处理",
  "Delivered four-shot video": "交付的四镜头成片",
  "Play the full edit": "播放完整成片",
  "Close preview": "收起播放器",
  "Open the delivered video": "打开交付视频",
  "Cut points in the delivered video": "成片镜头时间线",
  "Both runs used the same model and brief. Select a shot in either tree to inspect the code and inputs.": "两侧采用同一模型和剪辑要求。点击渲染树中的镜头，可对照源码和输入参数。",
  "Native DSH": "DSH 原生执行",
  "Model reasoning": "模型推理",
  "Write the timeline logic for this edit": "现场编写时间线逻辑",
  "writes Remotion logic to trim and sequence the footage and add labels.": "将剪辑需求写成 Remotion 的裁剪、编排和叠字逻辑。",
  "Render with newly written code": "用本次编写的代码渲染",
  "Structured computation": "结构化计算",
  "Remotion composition": "Remotion 合成",
  "Shots in the render tree": "渲染树中的镜头",
  "View Remotion code": "查看 Remotion 源码",
  "Reuse the learned timeline structure": "复用已学时间线结构",
  "selects the verified structure from the prior edit and binds new clips, cut points, and labels.": "选择上次剪辑后认证的结构，绑定本次素材、切点和标签。",
  "View bound inputs": "查看绑定参数",
  "MP4 delivered · Passed independent checks": "交付 MP4 · 通过独立验收",
  "Model requests": "模型请求数",
  "Execution time": "执行耗时",
  "Est. model cost (USD)": "模型费用估算（USD）",
  "Independent verification checked both deliveries for resolution, frame rate, frame count, and full decoding, and compared sampled frames with the source footage.": "独立验收检查两份成片的分辨率、帧率、总帧数和完整解码，并将固定采样帧与源素材比对。",
  "Model costs are estimated in USD using cache-adjusted token pricing for this run. Learning and verification of the reusable structure are accounted for separately.": "费用按本次执行的 Token 用量与缓存计价规则估算，以美元计。结构学习与认证另计。"
});
const english=new Map(),chinese=new Map();for(const [en,zh]of Object.entries(pairs)){english.set(en,en);english.set(zh,en);chinese.set(en,zh);chinese.set(zh,zh);}let locale='zh';try{locale=localStorage.getItem('geneloop.locale')||'zh'}catch{}const originals=new WeakMap(),attrs=new WeakMap();let queued=false;
function translate(value){const key=value.trim();let translated=(locale==='en'?english:chinese).get(key);if(!translated){const m=/^(新会话|New conversation) (\d+)$/.exec(key);if(m)translated=(locale==='en'?'New conversation':'新会话')+' '+m[2];}return translated?value.replace(key,translated):value;}

const localizedBlocks=new WeakMap();
function layoutForLocale(){for(const selector of ['.legacy-research-note h1','.invitation-copy>h2','.research h2','#closing-heading','.vision-lines']){const el=document.querySelector(selector);if(!el)continue;if(!localizedBlocks.has(el))localizedBlocks.set(el,{english:el.innerHTML,language:'en'});const state=localizedBlocks.get(el);if(state.language===locale)continue;if(locale==='en')el.innerHTML=state.english;else if(selector==='.vision-lines')el.innerHTML='<span>让智能从经验中积累能力，</span><span>在每一次突破中，</span><span>获得继续突破的力量</span>';else if(selector==='#closing-heading')el.textContent='与我们一起，定义下一代智能';else if(selector==='.research h2')el.innerHTML='<span class="research-title-line">把经验，</span><em class="research-title-line">变成<span class="capability-emphasis">可用的能力</span></em>';else if(selector==='.invitation-copy>h2')el.innerHTML='<span>追求</span><em>真正重要的发现</em>';else el.innerHTML='<span class="journal-title-line">把经验，</span><em class="journal-title-line">变成下一种能力。</em>';state.language=locale;}}
function showArticleLocale() {
  if (document.getElementById('hero-title')) {
    document.title = translate('GENELOOP — Efficiency-Oriented Self-Improving Agents');
  }
  for (const article of document.querySelectorAll('[data-article-locale]')) {
    const hidden = article.dataset.articleLocale !== locale;
    if (article.hidden !== hidden) article.hidden = hidden;
    if (!hidden) document.title = article.querySelector('h1').textContent + ' — GENELOOP';
  }
}
function apply(){queued=false;layoutForLocale();showArticleLocale();document.documentElement.lang=locale==='en'?'en':'zh-CN';const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;while(n=walker.nextNode()){if(n.parentElement?.closest('script,style,svg,[data-no-translate],[contenteditable=true],textarea,pre,code,#history .markdown,#history .message,[data-message-id],.geneloop-task-answer,.geneloop-message-content'))continue;let data=originals.get(n);if(!data||n.nodeValue!==data.last)data={original:n.nodeValue,last:n.nodeValue};let value=translate(data.original);if(locale==='zh'&&n.parentElement.closest('h1,h2,h3,h4,.hero-description,.interface,.story-copy,.hint,.welcome,.scene-cards,.loop-stage-title,.research-body,.join-copy')&&!n.parentElement.closest('.journal'))value=value.replace(/。(?=\s*$)/,'');if(n.nodeValue!==value)n.nodeValue=value;data.last=value;originals.set(n,data);}document.querySelectorAll('[placeholder],[title],[aria-label]').forEach(el=>{if(el.closest('[data-no-translate],svg'))return;let saved=attrs.get(el)||{};for(const name of ['placeholder','title','aria-label']){if(!el.hasAttribute(name))continue;const value=el.getAttribute(name);if(!saved[name]||saved[name].last!==value)saved[name]={original:value,last:value};const next=translate(saved[name].original);if(next!==value)el.setAttribute(name,next);saved[name].last=next;}attrs.set(el,saved);});updateLanguageControl();observer.takeRecords();}
function setLocale(value){locale=value==='en'?'en':'zh';try{localStorage.setItem('geneloop.locale',locale)}catch{}apply();}
const observer=new MutationObserver(()=>{if(!queued){queued=true;queueMicrotask(apply);}});
const trigger = document.createElement('button');
trigger.type = 'button';
trigger.className = 'language-trigger';
trigger.dataset.noTranslate = 'true';

function updateLanguageControl() {
  const isEnglish = locale === 'en';
  trigger.textContent = isEnglish ? '中文' : 'EN';
  trigger.setAttribute('aria-label', isEnglish ? '中文 — Switch to Chinese' : 'EN — 切换为英文');
}

trigger.addEventListener('click', () => setLocale(locale === 'en' ? 'zh' : 'en'));
document.querySelector('.site-banner nav')?.append(trigger);
observer.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['placeholder','title','aria-label','hidden']});
window.GeneLoopI18n={setLocale,refresh:apply,get locale(){return locale},t:translate};
apply();

})();
