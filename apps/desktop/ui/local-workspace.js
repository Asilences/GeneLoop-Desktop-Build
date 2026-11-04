const bridge = window.localWorkspace;
const byId = id => document.getElementById(id);
const results = byId('results');
const history = byId('history');
const historyList = byId('history-list');
let current;
const setBusy = busy => {
  byId('send').disabled = busy;
  history.inert = busy;
  byId('cancel').hidden = !busy;
  if (busy) byId('cancel').disabled = false;
};
bridge.state().then(state => {
  byId('directory').textContent = state.directory;
  byId('output').textContent = state.output;
  for (const task of state.tasks) addHistory(task);
});
byId('task').onsubmit = async event => {
  event.preventDefault();
  const text = byId('prompt').value.trim();
  if (!text) return;
  current = { prompt: text, at: Date.now(), updates: [] };
  setBusy(true);
  results.replaceChildren();
  byId('status').textContent = '正在获取本机模型授权并启动任务…';
  try { await bridge.start(text); }
  catch { current = undefined; byId('status').textContent = '无法提交本机任务。'; setBusy(false); }
};
byId('cancel').onclick = () => {
  byId('cancel').disabled = true;
  byId('status').textContent = '正在停止…';
  void bridge.cancel();
};
function renderUpdate(event) {
  if (event.kind === 'ready') {
    byId('status').textContent = '本机 Agent 正在执行…';
  }
  if (event.kind === 'answer' && typeof event.text === 'string') {
    const paragraph = document.createElement('p');
    paragraph.textContent = event.text;
    results.append(paragraph);
  } else if (event.kind === 'report' && typeof event.report?.name === 'string') {
    const button = document.createElement('button');
    button.textContent = '在资源管理器中查看 ' + event.report.name;
    button.onclick = () => bridge.reveal(event.report.name);
    results.append(button);
  } else if (event.kind === 'done') {
    const status = event.status === 'completed' ? '任务已完成。' : event.status === 'canceled' ? '任务已停止。' : '任务未完成。';
    byId('status').textContent = status + (event.error ? ' ' + event.error : '');
    setBusy(false);
  }
  results.scrollTop = results.scrollHeight;
}
function addHistory(task, latest = false) {
  const item = document.createElement('li');
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = task.prompt.trim().slice(0, 64);
  button.title = new Date(task.at).toLocaleString();
  button.onclick = () => {
    byId('prompt').value = task.prompt;
    results.replaceChildren();
    for (const update of task.updates) if (update) renderUpdate(update);
  };
  item.append(button);
  if (latest) historyList.prepend(item);
  else historyList.append(item);
  if (historyList.children.length > 30) historyList.lastElementChild.remove();
  history.hidden = false;
}
bridge.onUpdate(event => {
  if (current && event.kind !== 'ready') current.updates.push(event);
  renderUpdate(event);
  if (current && event.kind === 'done') {
    addHistory(current, true);
    current = undefined;
  }
});
