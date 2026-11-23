/** Fast path for an explicitly scoped literal replacement, on one uploaded PPTX. */
export type PptLiteralEdit = { page: number; replacements: { before: string; after: string }[] };

export function pptLiteralEdit(task: any): PptLiteralEdit | undefined {
  if(task.scene?.ppt_execution_strategy!=='ppt_master'||task.scene_options?.allow_output!==true||
    task.scene_inputs?.length!==1||!/\.pptx$/i.test(task.scene_inputs[0].file??'')||
    !Array.isArray(task.request?.content)||task.request.content.some((part:any)=>part.type==='image'))return;
  const text=task.request.content.filter((part:any)=>part.type==='text').map((part:any)=>part.text).join('\n');
  const target=/(?:只|仅)\s*(?:修改|编辑|改|替换)\s*第\s*(\d+)\s*页|\b(?:only\s+(?:edit|modify|change)\s+slide|(?:edit|modify|change)\s+only\s+slide)\s+(\d+)\b/i.exec(text);
  if(!target)return;
  const page=Number(target[1]??target[2]);
  if(!Number.isSafeInteger(page)||page<1)return;
  const quoted='[“"「]([^”"」\\r\\n]+)[”"」]';
  const expression=new RegExp('(?:将|把|replace\\s+)\\s*'+quoted+'\\s*(?:替换为|替换成|改为|改成|with)\\s*'+quoted,'gi');
  const replacements=[...text.matchAll(expression)].map((m)=>({before:m[1],after:m[2]}));
  if(!replacements.length||new Set(replacements.map(item=>item.before)).size!==replacements.length||
    replacements.some(({before,after})=>before===after))return;
  // A literal edit receipt cannot satisfy an unrecognized additional clause.
  const remaining=text.replace(expression,'').replace(target[0],'').split(/[。；;，,\n]+/).map(s=>s.trim()).filter(Boolean);
  if(remaining.some(clause=>!(/^(?:请)?(?:修改|编辑)(?:附件中|上传)的\s*PPTX$/i.test(clause)||
    /^(?:并|和|以及)$/.test(clause)||/^(?:保持(?:英文和)?原版式|(?:其余|其他|其它)(?:页面|页)?保持不变|(?:请)?(?:并)?交付(?:可编辑)?\s*PPTX(?:、同版\s*PDF(?:\s*和逐页预览)?)?)$/i.test(clause)||
    /^(?:keep (?:all )?(?:other slides|the original layout) unchanged|deliver (?:an editable )?pptx(?: and (?:a )?pdf)?|and)\.?$/i.test(clause))))return;
  return {page,replacements};
}

export function verifiedLiteralPptEdits(intent:PptLiteralEdit|undefined,edits:any[]):boolean {
  if(!intent||!Array.isArray(edits)||!edits.length||edits.length>intent.replacements.length)return false;
  const matched=new Set<string>();
  for(const edit of edits){
    if(edit.page!==intent.page||edit.action!=='replace_text'||typeof edit.expected_text!=='string'||typeof edit.text!=='string')return false;
    const original=edit.expected_text;
    const replacements=intent.replacements.map(row=>({...row,offset:original.indexOf(row.before)}))
      .filter(row=>row.offset>=0).sort((left,right)=>left.offset-right.offset);
    if(!replacements.length)return false;
    let end=0,updated='';
    for(const {before,after,offset} of replacements){
      if(matched.has(before)||offset<end||original.indexOf(before,offset+1)>=0||[...after].length>[...before].length)return false;
      updated+=original.slice(end,offset)+after;
      end=offset+before.length;
      matched.add(before);
    }
    if(updated+original.slice(end)!==edit.text)return false;
  }
  return matched.size===intent.replacements.length;
}
