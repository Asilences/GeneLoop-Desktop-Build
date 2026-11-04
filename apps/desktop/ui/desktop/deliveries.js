import {node,button,dialog,icon} from './components.js';

export function deliveryPath(session,id){
  return '/api/harless/'+(id.startsWith('native-')?'deliveries':'comparisons')+'?'+new URLSearchParams({session_id:session,id});
}

export function deliveryFiles(path,lane,result){
  return (result.artifacts||[]).map(file=>({...file,href:path+'&'+new URLSearchParams({lane,file:file.id})}));
}

export const deliveryName=file=>file.name.split('/').at(-1);

export function presentation(files){
  const decks=files.filter(file=>/\.pptx?$/i.test(file.name));
  const numbered=new Map();
  for(const file of files){
    const match=/^slide[-_ ]?(\d+)\.(?:png|jpe?g|webp)$/i.exec(deliveryName(file));
    if(match&&!numbered.has(Number(match[1])))numbered.set(Number(match[1]),file);
  }
  if(decks.length>1||(!decks.length&&numbered.size<2))return null;
  const slides=[...numbered].sort(([a],[b])=>a-b).map(([number,file])=>({...file,number}));
  return {deck:decks[0],slides};
}

function slideImage(file,attributes={}){
  const image=node('img',{src:file.href,alt:'幻灯片 '+file.number,...attributes});
  image.addEventListener('error',()=>image.replaceWith(node('span',{class:'slide-unavailable'},'第 '+file.number+' 页预览暂不可用')));
  return image;
}

function download(file,label){
  return node('a',{class:'secondary delivery-download',href:file.href,download:deliveryName(file)},icon('download'),label);
}

export function previewPresentation({slides,deck}){
  let index=0;
  const stage=node('div',{class:'slide-stage'}),counter=node('span',{'aria-live':'polite'});
  const previous=button('上一页',()=>show(index-1),'secondary');
  const next=button('下一页',()=>show(index+1),'secondary');
  function show(target){
    if(target<0||target>=slides.length)return;
    index=target;
    stage.replaceChildren(slideImage(slides[index]));
    counter.textContent='第 '+slides[index].number+' 页 · '+(index+1)+' / '+slides.length;
    previous.disabled=index===0;
    next.disabled=index===slides.length-1;
  }
  const element=dialog('演示文稿预览',stage,[previous,counter,next,deck?download(deck,'下载原稿'):null]);
  element.classList.add('presentation-dialog');
  element.addEventListener('keydown',event=>{
    if(event.key==='ArrowLeft'||event.key==='ArrowRight'){
      event.preventDefault();
      show(index+(event.key==='ArrowLeft'?-1:1));
    }
  });
  show(0);
}

export function presentationCard(value){
  const {deck,slides}=value;
  return node('section',{class:'presentation-card','aria-label':'演示文稿交付'},
    node('div',{class:'presentation-cover'},slides.length?slideImage(slides[0],{loading:'lazy'}):icon('files')),
    node('div',{class:'presentation-details'},
      node('div',{class:'delivery-kicker'},'演示文稿交付'),
      node('h4',{},deck?deliveryName(deck):'幻灯片预览'),
      node('p',{},slides.length?slides.length+' 页可预览':'演示文稿原稿'),
      node('div',{class:'delivery-actions'},
        slides.length?button('预览',()=>previewPresentation(value),'secondary'):null,
        deck?download(deck,'下载原稿'):null)));
}
