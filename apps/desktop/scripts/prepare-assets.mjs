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
console.log('Prepared independent desktop renderer and brand icons; no DSH web frontend or client modules.');
