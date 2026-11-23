import {node} from './components.js';

export function welcomeView(cards){
  return node('div',{class:'welcome desktop-hero'},
    node('div',{class:'desktop-hero-copy'},
      node('h2',{},node('span',{},'让研究，'),node('em',{},'向前一步。')),
      node('p',{},'把资料、想法和下一步，连接起来。'),
      node('div',{class:'scene-cards','aria-label':'写作示例'},cards)),
    node('canvas',{'data-fractal-art':'welcome','aria-hidden':true}));
}

/** 沿用官网 a5a044c1 的纸折龙曲线；只作品牌装饰，不代表 Motif 数据或执行进度。 */
export function bindFractalArtwork(){
  const controllers=new Map(),clocks=new Map(),reduced=matchMedia('(prefers-reduced-motion: reduce)');
  function mount(canvas){
    if(controllers.has(canvas))return;
    const ctx=canvas.getContext('2d');if(!ctx)return;
    let width=0,height=0,raf=null,last=0,painted=0,visible=false,dirty=true;
    let clock=clocks.get(canvas.dataset.fractalArt)??4500,ink,accent,camera,scale;
    const points=[[0,0],[1,0]],directions=[[1,0],[0,1],[-1,0],[0,-1]];
    let total=1,baseIndex=0,heading=0;
    const colors=()=>{const s=getComputedStyle(document.body);ink=s.getPropertyValue('--gl-ink').trim();accent=s.getPropertyValue('--blue').trim();dirty=true;};
    function extend(target){
      while(total<target){let odd=total;while(odd%2===0)odd/=2;heading=(heading+(odd%4===1?1:3))%4;
        const p=points.at(-1),d=directions[heading];points.push([p[0]+d[0],p[1]+d[1]]);total++;}
      if(points.length>8192){const remove=points.length-8192;points.splice(0,remove);baseIndex+=remove;}
    }
    function paint(){
      const progress=240+(reduced.matches?4500:clock)*.055,end=Math.floor(progress),fraction=progress-end;
      extend(end+1);const current=end-baseIndex,a=points[current],b=points[current+1];
      const head=[a[0]+(b[0]-a[0])*fraction,a[1]+(b[1]-a[1])*fraction];
      const recent=points.slice(Math.max(0,current-2048),current+1);
      let x0=Infinity,x1=-Infinity,y0=Infinity,y1=-Infinity;
      for(const p of recent){x0=Math.min(x0,p[0]);x1=Math.max(x1,p[0]);y0=Math.min(y0,p[1]);y1=Math.max(y1,p[1]);}
      const center=[(x0+x1)/2,(y0+y1)/2],target=Math.min(width*.88/(x1-x0+2),height*.9/(y1-y0+2));
      camera??=[...center];scale??=target;
      camera=camera.map((v,i)=>v+(center[i]-v)*.07);scale+=(target-scale)*.07;
      const at=p=>[width/2+(p[0]-camera[0])*scale,height/2+(p[1]-camera[1])*scale];
      ctx.clearRect(0,0,width,height);ctx.lineJoin='miter';ctx.lineCap='butt';
      const grid=Math.max(24,Math.min(width,height)/8);ctx.strokeStyle=ink;ctx.globalAlpha=.055;ctx.lineWidth=.6;ctx.beginPath();
      for(let x=grid/2;x<width;x+=grid){ctx.moveTo(x,0);ctx.lineTo(x,height);}
      for(let y=grid/2;y<height;y+=grid){ctx.moveTo(0,y);ctx.lineTo(width,y);}ctx.stroke();
      const path=(start,color,alpha,lineWidth)=>{ctx.strokeStyle=color;ctx.globalAlpha=alpha;ctx.lineWidth=lineWidth;ctx.beginPath();
        for(let i=start;i<=current;i++){const q=at(points[i]);i===start?ctx.moveTo(...q):ctx.lineTo(...q);}ctx.lineTo(...at(head));ctx.stroke();};
      path(Math.max(0,current-2048),ink,.8,1.35);path(Math.max(0,current-48),accent,1,1.8);
      const q=at(head);ctx.fillStyle=accent;ctx.fillRect(q[0]-2,q[1]-2,4,4);ctx.globalAlpha=1;
      canvas.dataset.fractalReady='true';
    }
    const active=()=>visible&&!document.hidden&&canvas.isConnected&&width>0&&height>0;
    function stop(){if(raf!==null)cancelAnimationFrame(raf);raf=null;last=0;canvas.dataset.fractalActive='false';}
    function schedule(){if(active()&&raf===null){canvas.dataset.fractalActive=String(!reduced.matches);raf=requestAnimationFrame(frame);}}
    function frame(time){
      raf=null;if(!active()){stop();return;}
      if(last&&!reduced.matches)clock+=Math.min(200,time-last);last=time;
      if((dirty||!reduced.matches)&&time-painted>=50){paint();painted=time;dirty=false;clocks.set(canvas.dataset.fractalArt,clock);}
      if(!reduced.matches||dirty)schedule();else stop();
    }
    function resize(){
      const r=canvas.getBoundingClientRect();if(!r.width||!r.height){width=height=0;stop();return;}
      width=r.width;height=r.height;const dpr=Math.min(devicePixelRatio||1,1.5);
      canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);dirty=true;schedule();
    }
    const intersection=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible){last=0;dirty=true;schedule();}else stop();},{threshold:.01});
    const sizing=new ResizeObserver(resize);
    controllers.set(canvas,{
      refresh(){colors();if(active())schedule();else stop();},
      visibility(){last=0;if(active()){dirty=true;schedule();}else stop();},
      dispose(){stop();clocks.set(canvas.dataset.fractalArt,clock);intersection.disconnect();sizing.disconnect();controllers.delete(canvas);canvas.width=canvas.height=0;},
    });
    colors();intersection.observe(canvas);sizing.observe(canvas);resize();
  }
  function added(root){if(root.nodeType!==1)return;if(root.matches('canvas[data-fractal-art]'))mount(root);root.querySelectorAll('canvas[data-fractal-art]').forEach(mount);}
  const tree=new MutationObserver(records=>{for(const r of records)for(const n of r.addedNodes)added(n);for(const [canvas,c]of controllers)if(!canvas.isConnected)c.dispose();});
  const theme=new MutationObserver(()=>{for(const c of controllers.values())c.refresh();});
  tree.observe(document.body,{childList:true,subtree:true});theme.observe(document.body,{attributes:true,attributeFilter:['data-ds-dark-theme']});
  const visibility=()=>{for(const c of controllers.values())c.visibility();};
  const preference=()=>{for(const c of controllers.values())c.refresh();};
  document.addEventListener('visibilitychange',visibility);reduced.addEventListener('change',preference);added(document.body);
  return ()=>{tree.disconnect();theme.disconnect();document.removeEventListener('visibilitychange',visibility);reduced.removeEventListener('change',preference);for(const c of [...controllers.values()])c.dispose();};
}
