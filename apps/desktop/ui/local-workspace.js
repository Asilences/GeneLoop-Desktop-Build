const bridge = window.localWorkspace;
const byId = id => document.getElementById(id);
const results = byId('results');
const history = byId('history');
const historyList = byId('history-list');
let continuation;
const scene = byId('scene');
const setContext = id => {
  continuation = id;
  byId('continuation').hidden = !id;
};
scene.onchange = () => setContext(undefined);
byId('reset-context').onclick = () => setContext(undefined);
byId('back').onclick = async () => {
  try { await bridge.back(); }
  catch (error) { byId('status').textContent = error?.message || '无法返回工作区。'; }
};
const setBusy = busy => {
  byId('back').disabled = busy;
  byId('send').disabled = busy;
  scene.disabled = busy;
  byId('reset-context').disabled = busy;
  history.inert = busy;
  byId('cancel').hidden = !busy;
  if (busy) byId('cancel').disabled = false;
};
async function refreshHistory(continueLatest = false) {
  const state = await bridge.state();
  byId('workspace-name').textContent = state.name;
  byId('directory').textContent = state.directory;
  byId('output').textContent = state.output;
  historyList.replaceChildren();
  for (const task of state.tasks) addHistory(task);
  history.hidden = !state.tasks.length;
  if (continueLatest && state.tasks[0]?.scene === scene.value && state.tasks[0]?.sessionId) {
    setContext(state.tasks[0].sessionId);
  }
}
void refreshHistory();
byId('task').onsubmit = async event => {
  event.preventDefault();
  const text = byId('prompt').value.trim();
  if (!text) return;
  setBusy(true);
  results.replaceChildren();
  byId('status').textContent = '正在获取本机模型授权并启动任务…';
  try { await bridge.start({ prompt: text, scene: scene.value, continuation }); }
  catch (error) { byId('status').textContent = error?.message || '无法提交本机任务。'; setBusy(false); }
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
  }
  results.scrollTop = results.scrollHeight;
}
function addHistory(task) {
  const item = document.createElement('li');
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = task.prompt.trim().slice(0, 64);
  button.title = new Date(task.at).toLocaleString();
  button.onclick = () => {
    setContext(undefined);
    byId('prompt').value = task.prompt;
    results.replaceChildren();
    for (const update of task.updates) if (update) renderUpdate(update);
  };
  item.append(button);
  if (task.sessionId && [...scene.options].some(option => option.value === task.scene)) {
    const resume = document.createElement('button');
    resume.type = 'button';
    resume.textContent = '续接';
    resume.setAttribute('aria-label', '续接 ' + button.textContent);
    resume.onclick = () => {
      button.click();
      scene.value = task.scene;
      setContext(task.sessionId);
      byId('prompt').value = '';
      byId('prompt').focus();
    };
    item.append(resume);
  }
  historyList.append(item);
}
bridge.onUpdate(async event => {
  renderUpdate(event);
  if (event.kind === 'done') {
    try { await refreshHistory(event.status === 'completed' && !event.error); }
    finally { setBusy(false); }
  }
});
