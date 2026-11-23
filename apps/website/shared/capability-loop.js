/* Four related forms, printed ink and restrained pointer feedback. */
(()=>{
'use strict';
const theme=document.documentElement.dataset.theme;
if(theme!=='lattice')return;
const root=document.querySelector('.loop-line');if(!root)return;
const labels=[...root.querySelectorAll(':scope>span')];if(labels.length!==4)return;
const reduce=matchMedia('(prefers-reduced-motion:reduce)');
root.classList.add('animated-loop');
const stages=labels.map((label,index)=>{
 const stage=document.createElement('div');stage.className='loop-stage';stage.tabIndex=0;
 const canvas=document.createElement('canvas');canvas.setAttribute('aria-hidden','true');
 const title=document.createElement('div');title.className='loop-stage-title';
 const number=document.createElement('small');number.textContent=String(index+1).padStart(2,'0');
 title.append(number,label);stage.append(title,canvas);
 return{stage,canvas,ctx:canvas.getContext('2d'),index,points:[],pointer:{x:0,y:0,amount:0,tx:0,ty:0,target:0}};
});
root.replaceChildren(...stages.map(s=>s.stage));
let visible=false,raf=0,last=0,clock=0;
for(const s of stages){
 let p=[0,0],dir=0;const dirs=[[1,0],[0,1],[-1,0],[0,-1]];s.points.push(p);
 for(let n=1;n<2**(5+s.index*2);n++){let odd=n;while(odd%2===0)odd/=2;dir=(dir+(odd%4===1?1:3))%4;p=[p[0]+dirs[dir][0],p[1]+dirs[dir][1]];s.points.push(p);}
 const xs=s.points.map(p=>p[0]),ys=s.points.map(p=>p[1]);s.bounds=[Math.min(...xs),Math.max(...xs),Math.min(...ys),Math.max(...ys)];
 const update=()=>{if(reduce.matches){s.pointer.x=s.pointer.tx;s.pointer.y=s.pointer.ty;s.pointer.amount=s.pointer.target;paint(1800);}else schedule();};
 s.canvas.addEventListener('pointermove',e=>{if(e.pointerType==='touch')return;const r=s.canvas.getBoundingClientRect();s.pointer.tx=Math.max(-1,Math.min(1,(e.clientX-r.left)/r.width*2-1));s.pointer.ty=Math.max(-1,Math.min(1,(e.clientY-r.top)/r.height*2-1));s.pointer.target=1;update();});
 s.canvas.addEventListener('pointerleave',()=>{s.pointer.target=0;s.pointer.tx=s.pointer.ty=0;update();});
 s.stage.addEventListener('focus',()=>{s.pointer.target=.6;s.pointer.tx=.25;s.pointer.ty=-.2;update();});
 s.stage.addEventListener('blur',()=>{s.pointer.target=0;s.pointer.tx=s.pointer.ty=0;update();});
}
const inks=[[55,60,51]];
const spotInks=[[169,76,47],[66,121,101],[70,100,135],[164,121,49]];
const mix=(a,b,t)=>a.map((v,i)=>Math.round(v+(b[i]-v)*t));
/* All stages retain one 24-second phase. Hover never changes speed. */
function fractal(s,t,w,h){
 const ctx=s.ctx,[xmin,xmax,ymin,ymax]=s.bounds,mouse=s.pointer;
 const scale=Math.min((w-40)/(xmax-xmin||1),(h-32)/(ymax-ymin||1));
 const pan=reduce.matches?0:mouse.amount;
 const at=p=>[w/2+(p[0]-(xmin+xmax)/2)*scale+mouse.x*pan*3,h/2+(p[1]-(ymin+ymax)/2)*scale+mouse.y*pan*3];
 ctx.lineWidth=1;ctx.strokeStyle='#272b2e';ctx.globalAlpha=.22+mouse.amount*.04;ctx.beginPath();
 s.points.forEach((p,i)=>{const q=at(p);i?ctx.lineTo(...q):ctx.moveTo(...q)});ctx.stroke();ctx.globalAlpha=1;
 const cycle=24000,progress=(t%cycle)/cycle,position=progress*(s.points.length-1),head=Math.floor(position),fraction=position-head,a=s.points[head],b=s.points[Math.min(head+1,s.points.length-1)],tip=[a[0]+(b[0]-a[0])*fraction,a[1]+(b[1]-a[1])*fraction];
 ctx.strokeStyle='#ad4c39';ctx.lineWidth=1.6;ctx.beginPath();
 s.points.slice(Math.max(0,head-Math.max(3,Math.floor(s.points.length*.08))),head+1).forEach((p,i)=>{const q=at(p);i?ctx.lineTo(...q):ctx.moveTo(...q)});ctx.lineTo(...at(tip));ctx.stroke();const q=at(tip);ctx.fillStyle='#ad4c39';ctx.fillRect(q[0]-1.5,q[1]-1.5,3,3);
 if(mouse.amount>.01){
  const cursor=[w/2+mouse.x*w/2,h/2+mouse.y*h/2];let nearest=0,distance=Infinity;
  s.points.forEach((p,i)=>{const q=at(p),d=(q[0]-cursor[0])**2+(q[1]-cursor[1])**2;if(d<distance){distance=d;nearest=i;}});
  const span=Math.max(2,Math.floor(20/Math.max(scale,1)));
  ctx.globalAlpha=mouse.amount*.7;ctx.strokeStyle='#ad4c39';ctx.lineWidth=1.3;ctx.beginPath();
  s.points.slice(Math.max(0,nearest-span),nearest+span+1).forEach((p,i)=>{const q=at(p);i?ctx.lineTo(...q):ctx.moveTo(...q)});ctx.stroke();
  const target=at(s.points[nearest]);ctx.strokeRect(target[0]-3,target[1]-3,6,6);ctx.globalAlpha=1;
 }
}
function paint(t){
 for(const s of stages){
  const r=s.canvas.getBoundingClientRect();if(!r.width||!r.height||!s.ctx)continue;
  const dpr=Math.min(devicePixelRatio||1,2);
  if(s.canvas.width!==Math.round(r.width*dpr)||s.canvas.height!==Math.round(r.height*dpr)){s.canvas.width=Math.round(r.width*dpr);s.canvas.height=Math.round(r.height*dpr);}
  s.ctx.setTransform(dpr,0,0,dpr,0,0);s.ctx.clearRect(0,0,r.width,r.height);
  fractal(s,t,r.width,r.height);
 }
}
function frame(t){
 raf=0;if(!visible||document.hidden)return;
 if(t-last>40){clock+=last?Math.min(t-last,100):0;for(const s of stages){for(const [key,target]of [['x','tx'],['y','ty'],['amount','target']])s.pointer[key]+=(s.pointer[target]-s.pointer[key])*.12;}paint(reduce.matches?1800:clock);last=t;}
 if(!reduce.matches)raf=requestAnimationFrame(frame);
}
function schedule(){if(!raf&&visible&&!document.hidden)raf=requestAnimationFrame(frame);}
new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible){last=0;schedule();}},{rootMargin:'120px'}).observe(root);
new ResizeObserver(()=>{paint(reduce.matches?1800:clock);schedule()}).observe(root);
document.addEventListener('visibilitychange',schedule);
reduce.addEventListener('change',()=>{paint(reduce.matches?1800:clock);schedule()});
})();
