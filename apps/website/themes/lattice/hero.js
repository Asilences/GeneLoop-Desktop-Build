/* A growing Heighway dragon and a one-way self-similar zoom. Neither reverses. */
(() => {
  'use strict';
  const html=document.documentElement;
  if(html.dataset.theme!=='lattice')return;
  const canvas=document.querySelector('#lattice-scene'),ctx=canvas?.getContext('2d');
  if(!ctx)return;
  const exploration=html.dataset.art==='zoom';
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const TAU=Math.PI*2,INK='#272b2e',RED='#ad4c39',PAPER='#fafbfb',ROOT3=Math.sqrt(3);
  let width=0,height=0,unit=1,clock=0,last=0,painted=-1000,raf=null,visible=true,running=!reduced.matches,dirty=true,ready=false;
  // The regular paperfolding turn sequence extends the same curve at its frontier.
  const points=[[0,0],[1,0]],directions=[[1,0],[0,1],[-1,0],[0,-1]];
  let total=1,baseIndex=0,heading=0,camera=null,splitUnit=null;
  function extendTo(target){
    while(total<target){
      if(exploration){
        // A Hilbert survey extends only at the leading edge; old geometry is retained.
        let order=14;while(total+1>=4**order)order+=2;
        let x=0,y=0,t=total+1;
        for(let size=1;size<2**order;size*=2){
          const rx=Math.floor(t/2)%2,ry=(t%2)^rx;
          if(!ry){if(rx){x=size-1-x;y=size-1-y;}[x,y]=[y,x];}
          x+=size*rx;y+=size*ry;t=Math.floor(t/4);
        }
        points.push([x,y]);total++;
      }else{
        let odd=total;while(odd%2===0)odd/=2;
        heading=(heading+(odd%4===1?1:3))%4;
        const p=points[points.length-1],d=directions[heading];points.push([p[0]+d[0],p[1]+d[1]]);total++;
      }
    }
    if(points.length>8192){const remove=points.length-8192;points.splice(0,remove);baseIndex+=remove;}
  }
  function line(a,b,color=INK,alpha=1,width=1){ctx.strokeStyle=color;ctx.globalAlpha=alpha;ctx.lineWidth=width;ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();}
  function dragon(time){
    const progress=240+time*.055,end=Math.floor(progress),fraction=progress-end;
    extendTo(end+1);
    const current=end-baseIndex,a=points[current],b=points[current+1],head=[a[0]+(b[0]-a[0])*fraction,a[1]+(b[1]-a[1])*fraction];
    const composed=['split','overlay','reveal'].includes(html.dataset.layout);
    const recent=points.slice(Math.max(0,current-(composed?4096:180)),current+1);
    const center=composed?[
      (Math.min(...recent.map(p=>p[0]))+Math.max(...recent.map(p=>p[0])))/2,
      (Math.min(...recent.map(p=>p[1]))+Math.max(...recent.map(p=>p[1])))/2
    ]:recent.reduce((s,p)=>[s[0]+p[0]/recent.length,s[1]+p[1]/recent.length],[0,0]);
    if(!camera)camera=center;
    camera[0]+=(center[0]-camera[0])*.045;camera[1]+=(center[1]-camera[1])*.045;
    let drawingUnit=unit;
    if(html.dataset.layout==='split'&&width>0){
      const spanX=Math.max(...recent.map(p=>p[0]))-Math.min(...recent.map(p=>p[0]))+2;
      const spanY=Math.max(...recent.map(p=>p[1]))-Math.min(...recent.map(p=>p[1]))+2;
      const target=Math.min(width*.86/spanX,height*.94/spanY);
      splitUnit=splitUnit===null?target:splitUnit+(target-splitUnit)*.045;
      drawingUnit=splitUnit;
    }
    let originX=width/2,originY=height/2;
    if(html.dataset.layout==='split'&&html.dataset.heroFlow==='stack'){
      const heading=document.querySelector('.hero-copy h1').getBoundingClientRect();
      const frame=canvas.getBoundingClientRect();
      originX=heading.left+heading.width/2-frame.left;
      originY=heading.top+heading.height/2-frame.top;
      // Anchor the drawn bounds, not the smoothed camera or the whole copy stack.
      camera=[...center];
    }
    const at=p=>[originX+(p[0]-camera[0])*drawingUnit,originY+(p[1]-camera[1])*drawingUnit];
    const grid=unit*4,ox=((originX-camera[0]*unit)%grid+grid)%grid,oy=((originY-camera[1]*unit)%grid+grid)%grid;
    for(let x=ox;x<width;x+=grid)line([x,0],[x,height],INK,.065,.75);
    for(let y=oy;y<height;y+=grid)line([0,y],[width,y],INK,.065,.75);
    ctx.strokeStyle=INK;ctx.globalAlpha=.88;ctx.lineWidth=2;ctx.lineJoin='miter';ctx.lineCap='butt';ctx.beginPath();
    const start=Math.max(0,current-4096);points.slice(start,current+1).forEach((p,i)=>{const q=at(p);i?ctx.lineTo(...q):ctx.moveTo(...q);});ctx.lineTo(...at(head));ctx.stroke();
    ctx.strokeStyle=RED;ctx.globalAlpha=1;ctx.lineWidth=2.6;ctx.beginPath();points.slice(Math.max(0,current-64),current+1).forEach((p,i)=>{const q=at(p);i?ctx.lineTo(...q):ctx.moveTo(...q);});ctx.lineTo(...at(head));ctx.stroke();
    const q=at(head);ctx.fillStyle=RED;ctx.beginPath();ctx.arc(...q,3,0,TAU);ctx.fill();
    line([q[0]-8,q[1]],[q[0]+8,q[1]],RED,.65,.6);line([q[0],q[1]-8],[q[0],q[1]+8],RED,.65,.6);
  }
  function paint(){
    const time=reduced.matches?5500:clock;ctx.clearRect(0,0,width,height);
    dragon(time);ctx.globalAlpha=1;
    canvas.closest('.artwork').classList.add('canvas-ready');
    if(!ready){ready=true;document.dispatchEvent(new Event('geneloop:art-ready'));}
  }
  function resize(){
    const r=canvas.getBoundingClientRect();width=r.width;height=r.height;if(!width||!height)return;
    const dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);
    unit=Math.min(width,height)/(html.dataset.layout==='split'?30.5:36);dirty=true;schedule();
  }
  function schedule(){if(raf===null)raf=requestAnimationFrame(frame);}
  function frame(time){
    raf=null;const delta=last?Math.min(1000,time-last):0;last=time;if(!visible||document.hidden)return;
    if(running){clock+=delta;dirty=true;}if(dirty&&time-painted>33){paint();painted=time;dirty=false;}if(running||dirty)schedule();
  }
  reduced.addEventListener('change',()=>{running=!reduced.matches;dirty=true;schedule();});
  document.addEventListener('visibilitychange',()=>{last=0;if(!document.hidden){dirty=true;schedule();}});
  new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;last=0;if(visible){dirty=true;schedule();}},{rootMargin:'100px'}).observe(canvas);
  new ResizeObserver(resize).observe(canvas);resize();
})();
