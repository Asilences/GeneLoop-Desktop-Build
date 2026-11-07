// Only for pictures extracted by the locked PPTX reader. Wrap the original
// bytes in a tiny slide and let the official native Office engine render them.
import {createRequire} from 'node:module';
import {readFileSync,writeFileSync,mkdtempSync,rmSync,lstatSync,copyFileSync} from 'node:fs';
import {dirname,extname,join,relative,isAbsolute} from 'node:path';
export async function renderEmbeddedMetafile(kit,root,input,output,options){
 const extension=extname(input).slice(1).toLowerCase(),bytes=readFileSync(input);
 if(!['emf','wmf'].includes(extension)||bytes.length<44||bytes.length>16*1024*1024)throw Error('内嵌矢量图格式或大小无效。');
 let width=2,height=1;
 if(extension==='emf'){
  if(bytes.readUInt32LE(0)!==1||bytes.readUInt32LE(40)!==0x464d4520)throw Error('EMF 文件头无效。');
  width=Math.abs(bytes.readInt32LE(32)-bytes.readInt32LE(24));height=Math.abs(bytes.readInt32LE(36)-bytes.readInt32LE(28));
 }else if(bytes.readUInt32LE(0)===0x9ac6cdd7){width=Math.abs(bytes.readInt16LE(10)-bytes.readInt16LE(6));height=Math.abs(bytes.readInt16LE(12)-bytes.readInt16LE(8));}
 if(!width||!height||width/height>50||height/width>50)throw Error('内嵌矢量图尺寸无效。');
 const cx=9144000,cy=Math.round(cx*height/width);
 const require=createRequire(join(root,'node_modules/@deepseek-ai/libreoffice-kit/package.json'));
 const {zipSync,strToU8}=require('fflate');
 const xml=s=>strToU8('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+s);
 const rel=(type,target)=>`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/${type}" Target="${target}"/></Relationships>`;
 const stage=mkdtempSync(join(dirname(output),'.geneloop-metafile-'));
 try{
  const deck=join(stage,'embedded.pptx');
  writeFileSync(deck,zipSync({
   '[Content_Types].xml':xml(`<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="${extension}" ContentType="image/x-${extension}"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>`),
   '_rels/.rels':xml(rel('officeDocument','ppt/presentation.xml')),
   'ppt/presentation.xml':xml(`<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst><p:sldSz cx="${cx}" cy="${cy}"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>`),
   'ppt/_rels/presentation.xml.rels':xml(rel('slide','slides/slide1.xml')),
   'ppt/slides/slide1.xml':xml(`<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/><p:pic><p:nvPicPr><p:cNvPr id="2" name="Embedded vector"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="${cx}" cy="${cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>`),
   'ppt/slides/_rels/slide1.xml.rels':xml(rel('image','../media/image.'+extension)),
   ['ppt/media/image.'+extension]:bytes,
  }));
  const converter=await kit.createConverter(options);
  try{const result=await converter.renderImages({inputPath:deck,outputDir:join(stage,'rendered'),pages:[1],dpi:96});
   const image=result.images?.[0];if(!image)throw Error('内嵌矢量图未生成预览。');
   const name=image.path;
   const rel=relative(stage,name);if(!rel||isAbsolute(rel)||rel.startsWith('..')||!lstatSync(name).isFile())throw Error('矢量图产物路径无效。');
   copyFileSync(name,output);
  }finally{await converter.dispose();}
 }finally{rmSync(stage,{recursive:true,force:true});}
}
