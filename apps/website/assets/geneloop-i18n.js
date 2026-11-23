/* English/Chinese UI copy. Text is assigned through DOM APIs, never evaluated. */
(()=>{if(window.GeneLoopI18n)return;const pairs={"Blog": "博客", "Explore GENELOOP": "探索 GENELOOP", "Explore GENELOOP ↗": "探索 GENELOOP ↗", "Intelligence,": "智能，", "shaped by": "源于", "recursion.": "递归。", "Our research": "我们的研究", "Four ways into GENELOOP.": "从这里，开始使用 GENELOOP。", "Desktop": "桌面端", "DSH Plugin": "DSH 插件", "Web": "网页版", "Mobile": "移动端", "Your own workspace.": "让能力有处安放。", "Start where you work.": "接入熟悉的工具。", "Open a new window.": "打开就能开始。", "A workspace for your agent.": "为智能体提供工作空间。", "A place for new capabilities.": "让新能力在这里生长。", "Bring GENELOOP to your tools.": "将 GENELOOP 接入工具。", "Build within your workflow.": "在现有流程中继续构建。", "Open GENELOOP in your browser.": "在浏览器中打开 GENELOOP。", "Continue in your workspace.": "在工作区里继续推进。", "What we learn": "我们所学", "Explore the research": "探索研究", "Experience": "经验", "Abstraction": "抽象", "Composition": "组合", "New capability": "新能力", "Skip to content": "跳转到正文", "Take intelligence beyond the known.": "让智能，走向未曾抵达之处", "Back to exploring": "返回探索", "RESEARCH NOTE / 001": "研究笔记 / 001", "should change": "应当改变", "what we can learn next.": "下一次学习的可能。", "From experience to building blocks": "一次任务之后，留下什么", "Where efficiency enters the loop": "把重复省下来，把探索接上去", "What we have observed": "从具体实验开始", "← Back to GENELOOP": "← 返回 GENELOOP", "GENELOOP turns experience into executable capabilities, then uses those capabilities to build new ones.": "GENELOOP 将经验转化为可执行的能力，再用这些能力构建新的能力。", "Access and release details will be shared here.": "产品开放与发布信息将在这里更新。", "A path toward recursive self-improvement through executable abstraction.": "让做过的事，成为下一次创造的起点。", "Human technology builds on accumulated foundations. A new generation of builders does not recreate every tool from the beginning. Reliable structures become the building blocks for what comes next. GENELOOP asks whether agents can develop a similar relationship with their own experience.": "技术向前推进，靠的不只是一次次从零开始。工具、方法和经验被留下来，后来者才能站在已有基础上继续构建。我们希望智能体也能如此：把一次任务中的有效做法，变成下一次可以直接使用的能力。", "Knowing how to complete a task is different from possessing a reliable, executable capability. An agent may successfully write a program and still repeat much of the reasoning, dependency checking, and debugging when a similar task appears.": "完成一次任务之后，究竟留下了什么？如果下次遇到相似问题，仍要重新推理、检查依赖、调试参数，那么成功就只停留在那一次对话里。我们希望留下的，是能够再次执行、再次检验的东西。", "GENELOOP learns executable programs from normal task traces. These capabilities can be matched, bound, validated, and reused in subsequent tasks. The next step is composition: using an existing capability as material for constructing a new one.": "GENELOOP 从任务过程里提取可执行程序，让经验有一个可以调用的形态。在新任务中，这些程序经过匹配、参数绑定和验证，再被实际使用。而已有能力也可以成为材料，参与下一种能力的构建。", "Reducing repeated work can release compute for exploration. If that exploration produces reliable higher-level abstractions, future execution and capability construction may become less costly in turn. This is the feedback loop we want to investigate.": "少做一些重复工作，就有机会把资源用在新的探索上。新的探索再沉淀为能力，服务后续任务——我们关心的，正是经验、能力与创造之间能否形成这样的循环。", "That goal does not necessarily require changes to model weights. An evolving collection of executable abstractions may change what an agent can accomplish within a fixed compute budget.": "这条路径不以修改模型权重为前提。随着可执行能力不断积累，智能体可以尝试在同样的计算预算里，完成更丰富的工作。", "Initial experiments provide local evidence for execution reuse and autonomous capability composition. In a five-paper BibTeX review experiment, model requests fell from 195 to 110 while the core check score remained 9 out of 10.": "初步实验为执行复用和自主能力组合提供了局部证据。在一次包含五篇论文的 BibTeX 审查实验中，模型请求从 195 次降至 110 次，核心检查得分保持为 9/10。", "In six parameterized video tasks, model requests fell from 44 to 30, but total tokens increased by about 7.8%, and independent quality review did not pass in every case. A separate recursive-construction experiment showed an agent building a cross-version consistency capability from an existing citation-review capability, passing four checks across two new paper projects.": "在六项参数化视频任务中，模型请求从 44 次降至 30 次，但总 token 数增加约 7.8%，且并非所有案例都通过独立质量评审。另一项递归构建实验中，智能体以已有引文审查能力为基础，构建了跨版本一致性能力，并在两个新论文项目上通过四项检查。", "Past capabilities should become the primitives of future creation.": "做过的事，应当为下一次创造留下基础。", "The goal is not only to do the same work more cheaply. It is to make the next capability easier to create.": "让经验真正有用：既服务眼前的工作，也为下一种能力铺路。", "Language": "语言", "A workspace for what comes next.": "面向下一步的工作空间。", "The desktop direction brings GENELOOP into a dedicated workspace, with richer functionality and a focus on de-identified experience sharing.": "在专属桌面工作区中使用 GENELOOP，连接工具与任务，积累经过验证的经验。", "Start where you already work.": "从现有工作流程开始。", "A plugin entry point for bringing GENELOOP into an existing workflow. Integration and compatibility details will accompany its release.": "通过插件把 GENELOOP 接入现有工作流程，集成与兼容信息会随版本发布。", "An entry point in your browser.": "从浏览器进入。", "The web experience offers a browser-based way to explore GENELOOP and its approach to learning and reusing capabilities.": "在浏览器中体验 GENELOOP，探索能力的学习与复用。", "The loop, a little closer.": "让能力循环更进一步。", "A mobile entry point is part of the GENELOOP vision. Platform support and availability are still to be announced.": "移动入口是 GENELOOP 规划的一部分，平台支持与开放时间将在后续公布。", "Structures that evolve.": "让结构持续演进，", "Capabilities that compound.": "让能力不断生长。", "Room for your ideas.": "给灵感留个位置。", "Keep your ideas close.": "随时记录新的想法。", "Pick up when inspiration strikes.": "在灵感到来时继续探索。", "From experience.": "把经验，", "To capability.": "变成可用的能力。", "Footer navigation": "页脚导航", "SHAPE THE NEXT ERA OF INTELLIGENCE": "共同塑造智能的下一个时代", "Toward": "迈向", "Recursive": "递归", "Self-Improvement.": "自我改进", "Turn experience into capability.": "经验成为能力", "Pursue discoveries": "追求", "that matter.": "真正重要的发现", "Progress that builds on itself": "让进步，拥有继续进步的能力", "Keep what experience teaches.": "经验成为能力", "An agent’s work should leave more than an answer. It should leave a capability.": "让智能体从经历中积累能够长期使用的能力", "Build with what you’ve learned.": "能力创造能力", "Use what already works to create what doesn’t yet exist.": "用已有能力发现、组合和构建新能力", "Get better at getting better.": "改进推动改进", "Push beyond doing more. Build intelligence that becomes better at advancing itself.": "每次突破，既拓展智能能做什么，也增强它继续突破的能力", "Join GENELOOP": "加入我们", "Make Intelligence Compound": "让每一次发现，打开下一次突破的可能", "Discovery builds on discovery.": "人类的进步，来自发现之上的新发现", "Turn experience into capability. Build what comes next.": "我们相信，智能也应如此：把经验积累为能力，再用已有能力探索尚未抵达的边界", "Independent minds": "我们寻找这样的人", "Ask the fundamental questions.": "我们寻找敢于提出根本问题、", "Challenge the accepted answers.": "挑战既定假设，", "Build what doesn’t exist yet.": "并把非传统想法付诸实践的人", "Think freely. Test rigorously.": "独立思考，严谨求证", "Make intelligence": "让进步，", "compound.": "推动下一次进步"};const english=new Map(),chinese=new Map();for(const [en,zh]of Object.entries(pairs)){english.set(en,en);english.set(zh,en);chinese.set(en,zh);chinese.set(zh,zh);}let locale='en';try{locale=localStorage.getItem('geneloop.locale')||'en'}catch{}const originals=new WeakMap(),attrs=new WeakMap();let queued=false;
function translate(value){const key=value.trim();let translated=(locale==='en'?english:chinese).get(key);if(!translated){const m=/^(新会话|New conversation) (\d+)$/.exec(key);if(m)translated=(locale==='en'?'New conversation':'新会话')+' '+m[2];}return translated?value.replace(key,translated):value;}

const localizedBlocks=new WeakMap();
function layoutForLocale(){for(const selector of ['.hero-copy h1','.journal h1','.invitation-copy>h2','.research h2','#closing-heading','.vision-lines']){const el=document.querySelector(selector);if(!el)continue;if(!localizedBlocks.has(el))localizedBlocks.set(el,{english:el.innerHTML,language:'en'});const state=localizedBlocks.get(el);if(state.language===locale)continue;if(locale==='en')el.innerHTML=state.english;else if(selector==='.hero-copy h1')el.innerHTML='<span>智能的</span><span>下一步，</span><em>始于递归。</em>';else if(selector==='.vision-lines')el.innerHTML='<span>让智能从经验中积累能力，</span><span>在每一次突破中，</span><span>获得继续突破的力量</span>';else if(selector==='#closing-heading')el.textContent='与我们一起，定义下一代智能';else if(selector==='.research h2')el.innerHTML='<span class="research-title-line">把经验，</span><em class="research-title-line">变成<span class="capability-emphasis">可用的能力</span></em>';else if(selector==='.invitation-copy>h2')el.innerHTML='<span>追求</span><em>真正重要的发现</em>';else el.innerHTML='<span class="journal-title-line">把经验，</span><em class="journal-title-line">变成下一种能力。</em>';state.language=locale;}}
function mountLanguage(){const target=document.querySelector('.site-banner .header')||document.querySelector('#workspace:not([hidden]) .header-actions');if(target){if(switcher.parentElement!==target)target.append(switcher);}else{let header=document.querySelector('.account-language-banner');if(!header){header=document.createElement('header');header.className='account-language-banner';document.body.append(header);}if(switcher.parentElement!==header)header.append(switcher);}}
function apply(){queued=false;mountLanguage();layoutForLocale();document.documentElement.lang=locale==='en'?'en':'zh-CN';const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;while(n=walker.nextNode()){if(n.parentElement?.closest('script,style,svg,[data-no-translate],[contenteditable=true],textarea,pre,code,#history .markdown,#history .message,[data-message-id],.geneloop-task-answer,.geneloop-message-content'))continue;let data=originals.get(n);if(!data||n.nodeValue!==data.last)data={original:n.nodeValue,last:n.nodeValue};let value=translate(data.original);if(locale==='zh'&&n.parentElement.closest('h1,h2,h3,h4,.hero-description,.interface,.story-copy,.hint,.welcome,.scene-cards,.loop-stage-title,.research-body,.join-copy')&&!n.parentElement.closest('.journal'))value=value.replace(/。(?=\s*$)/,'');if(n.nodeValue!==value)n.nodeValue=value;data.last=value;originals.set(n,data);}document.querySelectorAll('[placeholder],[title],[aria-label]').forEach(el=>{if(el.closest('[data-no-translate],svg'))return;let saved=attrs.get(el)||{};for(const name of ['placeholder','title','aria-label']){if(!el.hasAttribute(name))continue;const value=el.getAttribute(name);if(!saved[name]||saved[name].last!==value)saved[name]={original:value,last:value};const next=translate(saved[name].original);if(next!==value)el.setAttribute(name,next);saved[name].last=next;}attrs.set(el,saved);});updateLanguageControl();observer.takeRecords();}
function setLocale(value){locale=value==='en'?'en':'zh';try{localStorage.setItem('geneloop.locale',locale)}catch{}apply();}
const observer=new MutationObserver(()=>{if(!queued){queued=true;queueMicrotask(apply);}});
const switcher=document.createElement('div');
switcher.className='language-switch';
switcher.dataset.noTranslate='true';

const trigger=document.createElement('button');
trigger.type='button';
trigger.className='language-trigger';
trigger.setAttribute('aria-haspopup','menu');
trigger.setAttribute('aria-expanded','false');

const triggerLabel=document.createElement('span');
const chevron=document.createElementNS('http://www.w3.org/2000/svg','svg');
chevron.setAttribute('viewBox','0 0 16 16');
chevron.setAttribute('aria-hidden','true');
const path=document.createElementNS(chevron.namespaceURI,'path');
path.setAttribute('d','m4 6 4 4 4-4');
path.setAttribute('fill','none');
path.setAttribute('stroke','currentColor');
path.setAttribute('stroke-width','1.2');
chevron.append(path);
trigger.append(triggerLabel,chevron);

const menu=document.createElement('div');
menu.className='language-menu';
menu.id='geneloop-language-menu';
menu.hidden=true;
menu.setAttribute('role','menu');
menu.setAttribute('aria-label','Language / 语言');
trigger.setAttribute('aria-controls',menu.id);

const option=document.createElement('button');
option.type='button';
option.setAttribute('role','menuitem');
menu.append(option);
switcher.append(trigger,menu);

function updateLanguageControl(){
  const isEnglish=locale==='en';
  triggerLabel.textContent=isEnglish?'EN':'中文';
  trigger.setAttribute('aria-label',isEnglish?'Language':'语言');
  option.dataset.locale=isEnglish?'zh':'en';
  option.textContent=isEnglish?'中文':'EN';
}

function setMenuOpen(open){
  if(menu.hidden===!open)return;
  menu.hidden=!open;
  trigger.setAttribute('aria-expanded',String(open));
  if(open)option.focus({preventScroll:true});
}

trigger.onclick=()=>setMenuOpen(menu.hidden);
option.onclick=()=>{
  setMenuOpen(false);
  setLocale(option.dataset.locale);
  trigger.focus({preventScroll:true});
};

switcher.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&!menu.hidden){
    event.preventDefault();
    setMenuOpen(false);
    trigger.focus({preventScroll:true});
  }else if(event.target===trigger&&['ArrowDown','ArrowUp'].includes(event.key)){
    event.preventDefault();
    setMenuOpen(true);
  }
});

switcher.addEventListener('focusout',event=>{
  if(!switcher.contains(event.relatedTarget))setMenuOpen(false);
});
document.addEventListener('pointerdown',event=>{
  if(!switcher.contains(event.target))setMenuOpen(false);
});
window.addEventListener('scroll',()=>setMenuOpen(false),{passive:true});

const style=document.createElement('style');
style.textContent=`
.language-switch {
  --language-rule-inset:4px;
  --language-rule-bottom:4px;
  position:relative;
  display:inline-flex;
  align-items:center;
  flex:none;
  font-family:var(--ui,'GL Sans','GL Chinese',sans-serif);
  font-size:var(--type-nav,18px);
  line-height:1.2;
  color:inherit;
}
.language-trigger,
.language-menu button {
  box-sizing:border-box;
  display:grid;
  grid-template-columns:minmax(0,1fr) 13px;
  align-items:center;
  column-gap:8px;
  border:0;
  border-radius:0;
  background:none;
  color:inherit;
  font:inherit;
  text-align:center;
  cursor:pointer;
}
.language-trigger {
  position:relative;
  width:76px;
  min-height:48px;
  padding:0 var(--language-rule-inset);
}
.language-trigger svg {width:13px;height:13px;display:block}
.language-trigger::after,
.language-menu button::after {
  content:'';
  position:absolute;
  inset:auto var(--language-rule-inset) var(--language-rule-bottom);
  height:1px;
  background:currentColor;
  opacity:0;
  transition:opacity .18s ease;
}
.language-trigger:hover,
.language-trigger[aria-expanded=true],
.language-menu button:hover,
.language-menu button:focus-visible {color:var(--accent,var(--blue,#a34736))}
.language-trigger:hover::after,
.language-trigger[aria-expanded=true]::after,
.language-menu button:is(:hover,:focus-visible)::after {opacity:1}
.language-switch:has(.language-menu button:is(:hover,:focus-visible)) .language-trigger {color:inherit}
.language-switch:has(.language-menu button:is(:hover,:focus-visible)) .language-trigger::after {opacity:0}
.language-trigger:focus-visible {outline:1px solid currentColor;outline-offset:3px}
.language-menu {
  position:absolute;
  z-index:2;
  inset:calc(100% - var(--language-rule-bottom) + 1px) var(--language-rule-inset) auto;
  background:var(--banner,var(--paper,#f3f4f4));
}
.language-menu:not([hidden]) {animation:reveal-language .16s ease-out}
.language-switch .language-menu button {position:relative;width:100%;min-height:38px;padding:0}
.language-menu button::after {inset-inline:0}
.language-menu button:focus-visible {outline:none}
@keyframes reveal-language {from {clip-path:inset(0 0 100% 0)} to {clip-path:inset(0)}}
@media(prefers-reduced-motion:reduce) {
  .language-trigger::after,.language-menu button::after {transition:none}
  .language-menu:not([hidden]) {animation:none}
}
.account-language-banner {
  position:absolute;
  top:26px;
  right:32px;
  z-index:100;
  display:flex;
  align-items:center;
  font-family:'GL Sans','GL Chinese',sans-serif;
}
#workspace .language-switch {font-family:'GL Sans','GL Chinese',sans-serif;font-size:var(--type-control,16px)}
#workspace .language-trigger {min-height:36px;height:36px}
html[lang=zh-CN] :is(em,i,cite,dfn) {font-style:normal!important;font-weight:600!important}
`;
document.head.append(style);
observer.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['placeholder','title','aria-label','hidden']});
window.GeneLoopI18n={setLocale,refresh:apply,get locale(){return locale},t:translate};
apply();

const hero=document.querySelector('.hero');
if(hero){
  const layoutSlots=[
    '#hero-title','.hero-description','.hero-actions a','.section-line h2',
    '.interface-top','.interface h3','.interface p',
    '.research h2','.research-body p','.research-body .text-link','.loop-stage-title',
    '#vision h2','#vision .join-intro','.footer-motto'
  ].join(',');
  let measuredWidth,layoutFrame;

  function matchLocaleHeights(){
    layoutFrame=undefined;
    const slots=[...document.querySelectorAll(layoutSlots)];
    for(const slot of slots)slot.style.removeProperty('min-height');

    // Measure both languages in the same frame, then reserve room for the longer copy.
    const currentLocale=locale;
    const heights=slots.map(slot=>parseFloat(getComputedStyle(slot).height));
    locale=currentLocale==='en'?'zh':'en';
    apply();
    const alternateHeights=slots.map(slot=>parseFloat(getComputedStyle(slot).height));
    locale=currentLocale;
    apply();

    slots.forEach((slot,index)=>{
      const height=Math.max(heights[index],alternateHeights[index]);
      if(Number.isFinite(height))slot.style.minHeight=Math.ceil(height)+'px';
    });
  }

  function scheduleLayout(){
    if(layoutFrame===undefined)layoutFrame=requestAnimationFrame(matchLocaleHeights);
  }

  new ResizeObserver(([entry])=>{
    const width=entry.contentRect.width;
    if(width===measuredWidth)return;
    measuredWidth=width;
    scheduleLayout();
  }).observe(hero);
  window.addEventListener('resize',scheduleLayout);
  document.fonts?.addEventListener('loadingdone',scheduleLayout);
}
})();
