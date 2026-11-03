/** 与服务器同一逐轮场景协议；输入内容不截断，显式斜杠命令优先。 */
export function promptContent(text,attachments,scene,scenes){
  const normalized=value=>value?'/'+value.replace(/^\//,''):undefined;
  const shortcuts=scenes.map(row=>normalized(row.shortcut)).filter(Boolean);
  const explicit=shortcuts.some(shortcut=>text===shortcut||text.startsWith(shortcut+' ' )||text.startsWith(shortcut+'\n'));
  const shortcut=normalized(scenes.find(row=>row.id===scene)?.shortcut);
  const serialized=!explicit&&shortcut&&scene!=='new-scene'?shortcut+(text?' '+text:''):text;
  return [...(serialized.trim()?[{type:'text',text:serialized}]:[]),...attachments.map(row=>({type:'file',receiptId:row.receiptId}))];
}
