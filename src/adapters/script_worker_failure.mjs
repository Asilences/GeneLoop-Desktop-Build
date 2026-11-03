/** Bounded data-only diagnostics from the existing sandbox, never authority. */
import {basename} from 'node:path';
export const SCRIPT_FAILURE_FRAME='SCRIPT_CAPABILITY_FAILURE_V1 ';

export function scriptWorkerFailure(error){
 const text=error instanceof Error?error.message:'';
 const sandbox=text.startsWith('script_sandbox_failed: ');
 const suffix=text.slice(-1000);
 const type=sandbox?/\b(TypeError|KeyError|IndexError|AttributeError|ValueError|SyntaxError|NameError|ZeroDivisionError):(?: |$)/g:null;
 let exceptionType=null,match;
 if(type)while((match=type.exec(suffix)))exceptionType=match[1];
 const frames=[...suffix.matchAll(/File "([^"\r\n]+)", line ([0-9]+)/g)];
 const frame=frames.at(-1);
 const line=frame?Number(frame[2]):null;
 // Do not forward arbitrary exception messages, file contents or host paths.
 return {format:'script_worker_failure_v1',reason:'script_native_execution_failed',
  phase:sandbox?'sandbox_execution':'worker',exception_type:exceptionType,
  source_file:frame?basename(frame[1]).slice(0,128):null,
  source_line:Number.isSafeInteger(line)&&line>0?line:null,
  source_space:'executed_module',
  category:sandbox&&['TypeError','KeyError','IndexError'].includes(exceptionType)?'data_operation_error':'unknown',
  detail:'An observed exception is diagnostic evidence, not a contract violation or a retry authorization.'};
}

export function readScriptWorkerFailure(text){
 if(typeof text!=='string'||Buffer.byteLength(text)>8192)return null;
 try{
  const trimmed=text.trim();
  const frames=trimmed.split('\n').filter(line=>line.startsWith(SCRIPT_FAILURE_FRAME));
  if(frames.length>1)return null;
  const value=JSON.parse(frames.length===1?frames[0].slice(SCRIPT_FAILURE_FRAME.length):trimmed);
  const expected=['format','reason','phase','exception_type','source_file','source_line','source_space','category','detail'];
  if(!value||Array.isArray(value)||Object.keys(value).length!==expected.length||expected.some(k=>!Object.hasOwn(value,k)))return null;
  const canonical=scriptWorkerFailure(Error(''));
  if(value.format!==canonical.format||value.reason!==canonical.reason||value.source_space!==canonical.source_space||value.detail!==canonical.detail)return null;
  if(!['sandbox_execution','worker'].includes(value.phase))return null;
  if(value.exception_type!==null&&!['TypeError','KeyError','IndexError','AttributeError','ValueError','SyntaxError','NameError','ZeroDivisionError'].includes(value.exception_type))return null;
  if(value.source_file!==null&&(typeof value.source_file!=='string'||value.source_file.length>128||/[\/\\\r\n\x00]/.test(value.source_file)))return null;
  if(value.source_line!==null&&(!Number.isSafeInteger(value.source_line)||value.source_line<=0))return null;
  const category=value.phase==='sandbox_execution'&&['TypeError','KeyError','IndexError'].includes(value.exception_type)?'data_operation_error':'unknown';
  if(value.category!==category)return null;
  return value;
 }catch{return null;}
}
