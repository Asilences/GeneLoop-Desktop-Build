import { ipcRenderer } from 'electron';

// 隔离世界观察页面外观和模态状态。
window.addEventListener('DOMContentLoaded', () => {
  let previous = '', pending = false;
  const color = (value: string): string | undefined => {
    if (/^#[0-9a-f]{6}$/i.test(value)) return value;
    const rgb = /^rgb\(\s*(\d+)[, ]+\s*(\d+)[, ]+\s*(\d+)\s*\)$/.exec(value);
    if (rgb) return '#' + rgb.slice(1).map(channel => Math.max(0, Math.min(255, Number(channel))).toString(16).padStart(2, '0')).join('');
  };
  const publish = () => {
    pending = false;
    const style = getComputedStyle(document.body);
    const background = color(style.getPropertyValue('--gl-sidebar').trim()) || color(style.backgroundColor);
    const foreground = color(style.getPropertyValue('--gl-ink').trim()) || color(style.color);
    if (!background || !foreground) return;
    const screen = document.body.dataset.desktopScreen;
    const modalOpen = Boolean(document.querySelector('dialog:modal'));
    const signature = background + foreground + screen + modalOpen;
    if (signature === previous) return;
    previous = signature;
    ipcRenderer.send('geneloop:appearance', { background, foreground, screen, modalOpen });
  };
  const schedule = () => { if (!pending) { pending = true; requestAnimationFrame(publish); } };
  const observer = new MutationObserver(schedule);
  for (const element of [document.documentElement, document.body]) observer.observe(element, { attributes: true, attributeFilter: ['data-ds-dark-theme', 'data-geneloop-style', 'data-auth-active', 'data-desktop-screen', 'class', 'style'] });
  document.addEventListener('toggle', event => {
    if (event.target instanceof HTMLDialogElement) schedule();
  }, true);
  window.addEventListener('load', schedule);
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', schedule);
  publish();
});
