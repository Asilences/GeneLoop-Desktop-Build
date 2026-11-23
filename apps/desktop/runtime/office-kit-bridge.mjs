// Compatibility adapter for the desktop's existing, constrained soffice calls.
// The official Kit owns document parsing, layout, fonts and native processes.
import {dirname,extname,join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {existsSync} from 'node:fs';
import {renderEmbeddedMetafile} from './office-metafile.mjs';
const root=dirname(fileURLToPath(import.meta.url));
const args=process.argv.slice(2);
const kit=await import(pathToFileURL(join(root,'node_modules/@deepseek-ai/libreoffice-kit/lib/index.js')).href);
async function main(){
 const runtime=await kit.discoverRuntime();
 if(runtime.backend!=='native')throw Error('当前系统的原生 Office Kit 引擎未就绪。');
 if(args.includes('--version')){console.log('GeneLoop LibreOffice Kit '+runtime.version+' (native)');return;}
 const at=args.indexOf('--convert-to'),out=args.indexOf('--outdir');
 if(at<0||out<0||!args[at+1]||!args[out+1])throw Error('不支持的 Office 命令。');
 const flags=new Set(['--headless','--nologo','--nodefault','--norestore','--nofirststartwizard','--geneloop-embedded-preview']);
 const files=[];
 for(let i=0;i<args.length;i++){
  const v=args[i];if(i===at||i===out){i++;continue;}
  if(flags.has(v)||v.startsWith('-env:UserInstallation='))continue;
  if(v.startsWith('-'))throw Error('不支持的 Office 选项。');files.push(v);
 }
 if(files.length!==1)throw Error('每次只转换一个明确的本机文件。');
 const input=resolve(files[0]),format=args[at+1];
 const embedded=args.includes('--geneloop-embedded-preview');
 if(!/^(?:pdf(?::(?:impress|writer|calc)_pdf_Export)?|docx|odt|txt|xlsx|ods|csv|pptx|odp)$/.test(format)&&!(embedded&&format==='png'))throw Error('该格式不在精简 Office 的支持范围内。');
 const suffix=format.split(':')[0],extension=extname(input).slice(1).toLowerCase();
 if(embedded&&(suffix!=='png'||!['emf','wmf'].includes(extension)))throw Error('内嵌图片预览只接受模板中的 EMF／WMF 并输出 PNG。');
 if(extension==='rtf')throw Error('RTF 不再作为独立输入格式，请另存为 DOCX 或 TXT 后使用。');
 const output=join(resolve(args[out+1]),input.slice(input.lastIndexOf('/')+1).split('\\').at(-1).slice(0,-extname(input).length)+'.'+suffix);
 if(existsSync(output))throw Error('输出文件已存在，请使用新的任务目录。');
 const fonts=join(root,'../fonts');
 const options={timeoutMs:120000,maxInputBytes:200*1024*1024,
  maxOutputBytes:200*1024*1024,fontMetadataCacheDirectory:false,
  ...(existsSync(fonts)?{fontDirectories:[...(process.platform==='win32'?[join(process.env.SystemRoot??'C:\\Windows','Fonts')]:['/System/Library/Fonts','/Library/Fonts']),fonts]}:{})};
 if(embedded){await renderEmbeddedMetafile(kit,root,input,output,options);console.log(JSON.stringify({engine:'libreoffice-kit',embeddedMetafile:true}));return;}
 const converter=await kit.createConverter(options);
 try{const r=await converter.convert({inputPath:input,outputPath:output});
  console.log(JSON.stringify({engine:'libreoffice-kit',backend:r.backend,pageCount:r.pageCount,missingFonts:r.missingFonts}));
 }finally{await converter.dispose();}
}
try{await main();}catch(error){console.error(error.message);process.exitCode=1;}
