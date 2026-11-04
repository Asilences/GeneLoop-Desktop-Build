import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

const supported = process.versions.node.split('.').map(Number);
const available = supported[0] > 22 || supported[0] === 22 && supported[1] >= 18;
const { readAppearance } = available ? await import('../apps/desktop/src/appearance.ts') : {};
const policy = available ? await import('../apps/desktop/src/policy.ts') : undefined;
const settingsModule = available ? await import('../apps/desktop/src/settings.ts') : undefined;

test('桌面主题消息只接受颜色值，不接收CSS文本或执行能力', {skip:!available}, () => {
  assert.deepEqual(readAppearance({background:'#F7F7F8',foreground:'#171719'}), {background:'#f7f7f8',foreground:'#171719',dark:false});
  assert.equal(readAppearance({background:'#1b1b1b',foreground:'#f1f1f1'}).dark,true);
  for (const value of [null, {}, {background:'url(https://example.test)',foreground:'#171719'}, {background:'#fff;display:none',foreground:'#171719'}]) assert.equal(readAppearance(value),undefined);
});

test('桌面连接仅接受不含令牌的 HTTPS 根地址；本地 HTTP 仅用于显式开发诊断', { skip: !available }, () => {
  assert.equal(policy.serverOrigin('https://geneloop.ai'), 'https://geneloop.ai/');
  assert.equal(policy.serverOrigin('http://127.0.0.1:3050/', true), 'http://127.0.0.1:3050/');
  for (const input of ['http://geneloop.ai/', 'http://127.0.0.1/', 'file:///etc/passwd', 'javascript:alert(1)', 'https://user:password@geneloop.ai/', 'https://geneloop.ai/?token=private', 'https://geneloop.ai/login', 'https://geneloop.ai/#private', 'https://geneloop.ai/\n']) {
    assert.throws(() => policy.serverOrigin(input));
  }
  assert.throws(() => policy.serverOrigin('http://192.168.1.1/', true));
});

test('桌面站点、下载和系统浏览器地址分别校验', { skip: !available }, () => {
  const server = policy.DEFAULT_SERVER;
  assert.equal(policy.sameServer('https://geneloop.ai/login', server), true);
  for (const url of ['https://geneloop.ai.evil.example/', 'https://geneloop.ai@evil.example/', 'https://geneloop.ai:444/', 'file:///C:/private.txt', 'blob:https://geneloop.ai/id']) {
    assert.equal(policy.sameServer(url, server), false);
  }
  assert.equal(policy.ownedDownload(['https://geneloop.ai/api/file'], server), true);
  assert.equal(policy.ownedDownload(['blob:https://geneloop.ai/synthetic-file'], server), true);
  assert.equal(policy.ownedDownload(['https://geneloop.ai/api/file', 'https://evil.example/file'], server), false);
  assert.equal(policy.ownedDownload(['blob:https://evil.example/file'], server), false);
  assert.equal(policy.ownedDownload([], server), false);
  assert.equal(policy.externalWebUrl('https://example.org/paper'), 'https://example.org/paper');
  for (const url of ['file:///C:/Windows/system32/cmd.exe', 'powershell:command', 'javascript:alert(1)', 'https://private:secret@example.org/']) assert.equal(policy.externalWebUrl(url), null);
});

test('下载默认文件名保留中文并去除路径和 Windows 设备名', { skip: !available }, () => {
  assert.equal(policy.downloadName('../../论文.pptx'), '论文.pptx');
  assert.equal(policy.downloadName('C:\\secret\\报告.pdf'), '报告.pdf');
  assert.equal(policy.downloadName('NUL.txt'), '_NUL.txt');
  assert.equal(policy.downloadName('...'), 'GeneLoop-file');
  assert.equal(policy.downloadName('a<b>.txt'), 'a_b_.txt');
});

test('桌面设置往返、隔离运行地址与损坏配置恢复不清理原文件', { skip: !available }, () => {
  const directory = mkdtempSync(join(tmpdir(), 'geneloop-desktop-'));
  const file = join(directory, 'settings.json');
  try {
    const settings = settingsModule.loadSettings(file);
    assert.equal(settings.server, policy.DEFAULT_SERVER);
    settings.server = 'https://lab.example/';
    settingsModule.saveSettings(file, settings);
    assert.deepEqual(settingsModule.loadSettings(file), settings);
    assert.equal(settingsModule.loadSettings(file, 'https://other.example/').server, 'https://other.example/');
    assert.equal(settingsModule.loadSettings(file).server, 'https://lab.example/');
    writeFileSync(file, 'broken configuration');
    assert.equal(settingsModule.loadSettings(file).server, policy.DEFAULT_SERVER);
    assert.equal(readFileSync(file, 'utf8'), 'broken configuration');
    assert.throws(() => settingsModule.loadSettings(file, 'https://user:secret@example.org/'));
    assert.deepEqual(policy.windowSize({ width: 2, height: Infinity, maximized: 'yes' }), { width: 800, height: 860, maximized: false });
  } finally { rmSync(directory, { recursive: true, force: true }); }
});
