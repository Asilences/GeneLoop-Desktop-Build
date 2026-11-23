/** Receipt shape normalization only; no reading, classification or permission. */
import {digest} from './paper_rsi_program.ts';
const prefix='mcp__file_management__';
function completedChains(events:any[]){
 const opens=new Map(),chunks=new Map(),conflicts=new Set();
 for(const {tool,out} of events){
  if(!out||out.error||out.isError)continue;
  if(tool===prefix+'open_document')opens.set(digest(out),out);
  if(tool===prefix+'read_document_chunk'&&typeof out.request_id==='string'){
   const prior=chunks.get(out.request_id);
   if(prior&&digest(prior)!==digest(out))conflicts.add(out.request_id);
   chunks.set(out.request_id,out);
  }
 }
 const completed=[];
 for(const open of opens.values()){
  if(!Number.isInteger(open.page_count)||open.page_count<1||typeof open.request_id!=='string')continue;
  let id=open.request_id,page=1,offset=0,done=false;const seen=new Set(),proofs=[];
  while(typeof id==='string'&&!seen.has(id)&&!conflicts.has(id)){
   seen.add(id);const c=chunks.get(id);
   if(!c||c.document_id!==open.document_id||c.source_id!==open.source_id||c.source_sha256!==open.source_sha256||
    c.mode!==open.mode||c.page!==page||c.offset!==offset||typeof c.text!=='string'||
    !Number.isInteger(c.end_offset)||!Number.isInteger(c.page_characters)||c.end_offset<offset||
    c.end_offset>c.page_characters||[...c.text].length!==c.end_offset-offset||
    c.page_complete!==(c.end_offset===c.page_characters))break;
   proofs.push(digest(c));
   if(c.next_request_id===null){done=c.page_complete&&page===open.page_count;break;}
   if(c.page_complete){page++;offset=0;}else{if(c.end_offset===offset)break;offset=c.end_offset;}
   if(page>open.page_count)break;id=c.next_request_id;
  }
  if(done)completed.push({format:'file-derived-document-coverage-v1',source_id:open.source_id,
   source_sha256:open.source_sha256,document_id:open.document_id,mode:open.mode,
   complete:true,page_count:open.page_count,derived_from:'actual_open_and_chunk_chain',
   open_receipt_sha256:digest(open),chunk_receipt_sha256:proofs});
 }
 return completed;
}
export function fileReadEvidence(context:any){
 const inventory=context?.receipts?.[prefix+'list_files']?.files;
 if(!Array.isArray(inventory))return {format:'file-read-evidence-v1',files:[],reads:[]};
 const current=new Map(inventory.map(f=>[f.file_id,f]));
 const events=[...(Array.isArray(context.history)?context.history:[]).map(r=>({tool:r.tool,out:r.out,args:r.args??r.arguments??{}})),
  ...Object.entries(context.receipts??{}).map(([tool,out])=>({tool,out,args:{}}))];
 const identities=new Map<string,string>(),reads:any[]=[],coverages:any[]=[];
 const seen=new Set<string>();
 for(const e of events){
  const out:any=e.out;if(!out||typeof out!=='object'||out.error||out.isError)continue;
  if(e.tool===prefix+'pin_file'&&out.source_id&&current.has(out.file_id))identities.set(out.source_id,out.file_id);
  if(e.tool===prefix+'pin_files'&&Array.isArray(out.source_ids)&&out.source_ids.length===out.file_ids?.length)
   out.source_ids.forEach((sid,i)=>{if(current.has(out.file_ids[i]))identities.set(sid,out.file_ids[i]);});
  const rows=e.tool===prefix+'read_files'&&Array.isArray(out.reads)?out.reads:e.tool===prefix+'read_file'?[out]:[];
  for(const row of rows){
   const file:any=current.get(row.file_id);
   if(!file||row.sha256!==file.sha256||typeof row.text!=='string')continue;
   if(row.source_id)identities.set(row.source_id,row.file_id);
   const id=digest(row);if(seen.has(id))continue;seen.add(id);
   reads.push({...row,receipt_tool:e.tool,receipt_sha256:id,
    complete:row.status==='readable'&&row.truncated===false&&row.metadata?.preview_only!==true});
  }
  if(e.tool===prefix+'document_coverage')coverages.push(out);
 }
 coverages.push(...completedChains(events));
 return {format:'file-read-evidence-v1',reads,
  files:inventory.map(file=>{
   const rows=reads.filter(r=>r.file_id===file.file_id);
   const coverage=coverages.filter(c=>identities.get(c.source_id)===file.file_id&&c.source_sha256===file.sha256&&c.complete===true);
   return {...file,complete:rows.some(r=>r.complete)||coverage.length>0,
    reads:rows,coverage:coverage.map(c=>({...c,receipt_sha256:digest(c)}))};
  })};
}

export function withFileReadEvidence(input:any){
 if(!input||typeof input!=='object'||!input.receipts)return input;
 return {...input,read_evidence:fileReadEvidence(input)};
}
