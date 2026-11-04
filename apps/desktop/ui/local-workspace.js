const bridge = window.localWorkspace;
const byId = id => document.getElementById(id);
const results = byId('results');
const setBusy = busy => {
  byId('send').disabled = busy;
  byId('cancel').hidden = !busy;
  if (busy) byId('cancel').disabled = false;
};
bridge.state().then(state => {
  byId('directory').textContent = state.directory;
  byId('output').textContent = state.output;
});
byId('task').onsubmit = async event => {
  event.preventDefault();
  const text = byId('prompt').value.trim();
  if (!text) return;
  setBusy(true);
  results.replaceChildren();
  byId('status').textContent = '正在获取本机模型授权并启动任务…';
  try { await bridge.start(text); }
  catch { byId('status').textContent = '无法提交本机任务。'; setBusy(false); }
};
byId('cancel').onclick = () => {
  byId('cancel').disabled = true;
  byId('status').textContent = '正在停止…';
  void bridge.cancel();
};
bridge.onUpdate(event => {
  if (event.kind === 'answer') {
    const paragraph = document.createElement('p');
    paragraph.textContent = event.text;
    results.append(paragraph);
  } else if (event.kind === 'report') {
    const button = document.createElement('button');
    button.textContent = '在资源管理器中查看 ' + event.report.name;
    button.onclick = () => bridge.reveal(event.report.name);
    results.append(button);
  } else if (event.kind === 'done') {
    byId('status').textContent = event.status === 'completed' ? '任务已完成。' :
      event.status === 'canceled' ? '任务已停止。' : event.error || '任务未完成。';
    setBusy(false);
  }
  results.scrollTop = results.scrollHeight;
});
