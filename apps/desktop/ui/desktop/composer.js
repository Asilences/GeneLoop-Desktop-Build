/** 与服务器同一逐轮场景协议；输入内容不截断，显式斜杠命令优先。 */
export const shortcutOf=scene=>scene?.shortcut?'/'+scene.shortcut.replace(/^\//,''):undefined;
export function sceneCommand(text,scenes){
  const match=/^\s*\/([a-z][a-z0-9_-]*)(?=\s|$|[^\x00-\x7F])/i.exec(text);
  const scene=match&&scenes.find(row=>shortcutOf(row)?.toLowerCase()==='/'+match[1].toLowerCase());
  return scene?{scene:scene.id,text:text.slice(match[0].length).trimStart(),hasBodyBoundary:text.length>match[0].length}:undefined;
}
export function sceneSuggestions(text,scenes){
  const match=/^\s*\/([^\s/]*)$/.exec(text);if(!match)return [];
  const query=match[1].toLowerCase();return scenes.filter(scene=>scene.shortcut&&(scene.shortcut.toLowerCase().startsWith(query)||scene.label.toLowerCase().includes(query)));
}
export function promptContent(text,attachments,scene,scenes){
  const explicit=sceneCommand(text,scenes);
  const shortcut=shortcutOf(scenes.find(row=>row.id===scene));
  const serialized=!explicit&&shortcut&&scene!=='new-scene'?shortcut+(text?' '+text:''):text;
  return [...(serialized.trim()?[{type:'text',text:serialized}]:[]),...attachments.map(row=>({type:'file',receiptId:row.receiptId}))];
}
