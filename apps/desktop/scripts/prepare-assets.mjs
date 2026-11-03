import {copyFileSync,mkdirSync,readFileSync,readdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import sharp from 'sharp';
import {createHash} from 'node:crypto';
const app=fileURLToPath(new URL('../',import.meta.url)),repo=fileURLToPath(new URL('../../../',import.meta.url)),assets=join(app,'assets');
mkdirSync(assets,{recursive:true});
// 仅复用品牌SVG，页面、CSS与状态管理均来自桌面自己的源码。
copyFileSync(join(repo,'src/adapters/brand/geneloop-spiral.svg'),join(assets,'geneloop-spiral.svg'));
const rendererFiles=readdirSync(join(app,'ui/desktop'));
writeFileSync(join(assets,'manifest.json'),JSON.stringify({format:2,frontend:'geneloop-independent-desktop',sourceCommit:execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8'}).trim(),sourceDirty:execFileSync('git',['status','--porcelain','--','apps/desktop','tests/test_desktop_frontend.mjs'],{cwd:repo,encoding:'utf8'}).trim().length>0,rendererFiles,rendererSha256:Object.fromEntries(rendererFiles.map(file=>[file,createHash('sha256').update(readFileSync(join(app,'ui/desktop',file))).digest('hex')])),scenes:JSON.parse(readFileSync(join(repo,'config/harless-scenes.json'),'utf8')).scenes.map(({id,label})=>({id,label}))},null,2)+'\n');
const resize={fit:'contain',background:{r:0,g:0,b:0,alpha:0}};
await sharp(join(assets,'geneloop-spiral.svg')).resize(512,512,resize).png().toFile(join(assets,'icon.png'));
const sizes=[16,32,48,64,128,256],frames=await Promise.all(sizes.map(size=>sharp(join(assets,'geneloop-spiral.svg')).resize(size,size,resize).png().toBuffer()));
const header=Buffer.alloc(6+frames.length*16);header.writeUInt16LE(1,2);header.writeUInt16LE(frames.length,4);let offset=header.length;
frames.forEach((frame,i)=>{const at=6+i*16;header[at]=sizes[i]===256?0:sizes[i];header[at+1]=header[at];header.writeUInt16LE(1,at+4);header.writeUInt16LE(32,at+6);header.writeUInt32LE(frame.length,at+8);header.writeUInt32LE(offset,at+12);offset+=frame.length;});
writeFileSync(join(assets,'icon.ico'),Buffer.concat([header,...frames]));

// NSIS Modern UI uses bottom-up, 24-bit BMP artwork.
async function installerBitmap(name,width,height,background,logo){
  const canvas=Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">${background}</svg>`);
  const image=await sharp(join(assets,'geneloop-spiral.svg')).resize(logo.width,logo.height,resize).png().toBuffer();
  const {data:pixels,info}=await sharp(canvas).composite([{input:image,left:logo.left,top:logo.top}])
    .removeAlpha().raw().toBuffer({resolveWithObject:true});
  if(info.channels!==3)throw Error('Installer artwork must be RGB');
  const stride=Math.ceil(width*3/4)*4;
  const bmp=Buffer.alloc(54+stride*height);
  bmp.write('BM');
  bmp.writeUInt32LE(bmp.length,2);
  bmp.writeUInt32LE(54,10);
  bmp.writeUInt32LE(40,14);
  bmp.writeInt32LE(width,18);
  bmp.writeInt32LE(height,22);
  bmp.writeUInt16LE(1,26);
  bmp.writeUInt16LE(24,28);
  bmp.writeUInt32LE(stride*height,34);
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    const from=(y*width+x)*3,to=54+(height-y-1)*stride+x*3;
    bmp[to]=pixels[from+2];bmp[to+1]=pixels[from+1];bmp[to+2]=pixels[from];
  }
  writeFileSync(join(assets,name+'.bmp'),bmp);
}
await installerBitmap('installerHeader',150,57,`
  <defs><linearGradient id="header"><stop stop-color="#fff"/><stop offset="1" stop-color="#eef5ff"/></linearGradient></defs>
  <rect width="150" height="57" fill="url(#header)"/>
  <path d="M80 57L105 31L130 41L150 19M105 31L93 11" fill="none" stroke="#9eadea" opacity=".34"/>
  <g fill="#a1b3e6"><circle cx="105" cy="31" r="2"/><circle cx="130" cy="41" r="2"/><circle cx="93" cy="11" r="1.5"/></g>
`,{width:25,height:40,left:115,top:8});
await installerBitmap('installerSidebar',164,314,`
  <defs>
    <linearGradient id="panel" x2=".8" y2="1"><stop stop-color="#eef0ff"/><stop offset=".58" stop-color="#f8faff"/><stop offset="1" stop-color="#e9f9f7"/></linearGradient>
  </defs>
  <rect width="164" height="314" fill="url(#panel)"/>
  <g fill="none" stroke="#96a9d4" stroke-opacity=".44">
    <path d="M-7 86L29 49L63 68L104 39L172 73M29 49L42 17M104 39L130 12M63 68L74 106"/>
    <path d="M-6 259L29 228L65 252L101 220L145 241L173 210M29 228L16 193M65 252L53 290M101 220L130 184M145 241L133 283"/>
  </g>
  <g fill="#96a9d4">
    <circle cx="29" cy="49" r="3"/><circle cx="104" cy="39" r="2.5"/><circle cx="29" cy="228" r="2.5"/>
    <circle cx="65" cy="252" r="3"/><circle cx="101" cy="220" r="2.5"/><circle cx="133" cy="283" r="2"/>
  </g>
`,{width:70,height:112,left:47,top:99});
console.log('Prepared independent desktop renderer and brand icons; no DSH web frontend or client modules.');
