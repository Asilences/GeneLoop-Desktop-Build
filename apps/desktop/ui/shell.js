(() => {
  const bridge = window.geneLoopDesktop;
  const byId = id => document.getElementById(id);
  let latest;
  function render(state) {
    if (state.appearance) {
      const root = document.documentElement;
      root.style.setProperty('--chrome-bg', state.appearance.background);
      root.style.setProperty('--chrome-ink', state.appearance.foreground);
      root.dataset.dark = String(state.appearance.dark);
    }
    latest = state;
    byId('desktop-menus').hidden = !state.workspaceVisible || !['connected', 'settings'].includes(state.phase);
    const modalOpen = state.phase === 'connected' && state.modalOpen;
    document.documentElement.classList.toggle('workspace-modal', modalOpen);
    byId('desktop-menus').inert = modalOpen;
    const settings = state.phase === 'settings', error = state.phase === 'error';
    byId('title').textContent = settings ? '连接你的 GeneLoop' : error ? '工作区暂时无法连接' : '正在连接你的工作区';
    byId('message').textContent = state.message || (settings ? '使用与网页版相同的账号和场景。' : '即将打开 GeneLoop。');
    byId('progress').hidden = settings || error || state.phase === 'connected';
    byId('settings').hidden = !settings;
    byId('retry').hidden = !error;
    byId('configure').hidden = !error;
    byId('version').textContent = '版本 ' + state.version;
    if (settings) { byId('server').value = state.server; byId('server').focus(); }
  }
  bridge.onState(render);
  bridge.state().then(render);
  byId('file-menu').onclick = () => bridge.menu('file');
  byId('edit-menu').onclick = () => bridge.menu('edit');
  byId('view-menu').onclick = () => bridge.menu('view');
  byId('help-menu').onclick = () => bridge.menu('help');
  byId('retry').onclick = () => bridge.retry();
  byId('configure').onclick = () => render({ ...latest, phase: 'settings', message: '' });
  byId('settings').onsubmit = async event => {
    event.preventDefault();
    byId('connect').disabled = true; byId('error').textContent = '';
    try {
      const result = await bridge.connect(byId('server').value.trim());
      if (!result.ok) byId('error').textContent = result.message;
    } catch { byId('error').textContent = '连接设置未能保存，请稍后重试。'; }
    finally { byId('connect').disabled = false; }
  };
})();
