/** 在私有目录编译只检查进程的NSIS探针，不安装、不改注册表、不操作用户应用。 */
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { once } from 'node:events';
import { copyFileSync, existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

assert.equal(process.platform, 'win32');
const app = fileURLToPath(new URL('../', import.meta.url));
const nsis = resolve(process.env.GENELOOP_NSIS_DIR || '');
const plugins = resolve(process.env.GENELOOP_NSIS_PLUGINS || '');
assert.ok(process.env.GENELOOP_NSIS_DIR && existsSync(join(nsis, 'makensis.exe')), 'GENELOOP_NSIS_DIR 指向本机构建缓存内的NSIS目录');
assert.ok(process.env.GENELOOP_NSIS_PLUGINS && existsSync(join(plugins, 'nsProcess.dll')), 'GENELOOP_NSIS_PLUGINS 指向同一构建器的x86-unicode插件目录');
const token = randomUUID().slice(0, 8);
const output = join(app, '.local/validation/installer-processes-' + token);
const install = join(output, 'Installed App'), sibling = install + '-other';
mkdirSync(install, { recursive: true }); mkdirSync(sibling);
const name = 'GeneLoop-process-test-' + token + '.exe';
const executable = join(install, name), unrelated = join(install, 'Uninstall ' + name), prefixSibling = join(sibling, 'Helper.exe');
for (const path of [executable, unrelated, prefixSibling]) copyFileSync(process.execPath, path);
const probe = join(output, 'probe.exe');
const script = join(output, 'probe.nsi');
writeFileSync(script, `Unicode true
RequestExecutionLevel user
SilentInstall silent
OutFile "${probe}"
!addincludedir "${join(nsis, 'Include')}"
!addplugindir "${plugins}"
!include "LogicLib.nsh"
!define APP_EXECUTABLE_FILENAME "${name}"
!define PRODUCT_NAME "GeneLoop Diagnostic"
!include "${join(app, 'installer.nsh')}"
Section
  !insertmacro customCheckAppRunning
  SetErrorLevel 0
SectionEnd
`);
const compiled = spawnSync(join(nsis, 'makensis.exe'), ['/V2', script], { cwd: output, encoding: 'utf8', windowsHide: true });
assert.equal(compiled.status, 0, compiled.stdout + compiled.stderr);
const report = { kind: 'native-nsis-process-diagnostic', model_requests: 0, checks: [] };
const owned = new Set();
async function start(file) {
  const child = spawn(file, ['-e', "process.stdout.write('ready');setInterval(()=>{},1000)"], { cwd: dirname(file), stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  owned.add(child);
  const ready = once(child.stdout, 'data');
  await Promise.race([ready, once(child, 'exit').then(([code]) => { throw Error('诊断进程启动失败：' + code); }), new Promise((_, reject) => { const timer = setTimeout(() => reject(Error('诊断进程启动超时')), 5000); timer.unref(); })]);
  return child;
}
async function stop(child) {
  if (child.exitCode === null) { const exited = once(child, 'exit'); child.kill(); await exited; }
  owned.delete(child);
}
const check = (label, expected) => {
  const result = spawnSync(probe, [], { cwd: output, windowsHide: true, timeout: 10_000 });
  assert.equal(result.status, expected, label + ': ' + String(result.error || result.status));
  report.checks.push(label); console.log('通过：' + label);
};
try {
  check('无应用进程时允许继续，不显示无法关闭', 0);
  const uninstall = await start(unrelated);
  check('同目录卸载器不被误判为应用', 0); assert.equal(uninstall.exitCode, null);
  const helper = await start(prefixSibling);
  check('安装路径前缀相同的其他目录程序不被误判', 0); assert.equal(helper.exitCode, null);
  const main = await start(executable), renderer = await start(executable);
  check('真实同名应用进程存在时拒绝静默覆盖', 1618);
  assert.equal(main.exitCode, null); assert.equal(renderer.exitCode, null);
  await stop(main);
  check('仍有同名子进程时继续阻止覆盖，不因主进程退出就放行', 1618);
  await stop(renderer);
  check('应用所有进程退出后重新检查可以继续', 0);
  assert.equal(uninstall.exitCode, null); assert.equal(helper.exitCode, null);
  report.ok = true;
} catch (error) { report.ok = false; report.error = String(error.stack); throw error; }
finally {
  for (const child of owned) await stop(child);
  writeFileSync(join(output, 'summary.json'), JSON.stringify(report, null, 2) + '\n');
  console.log('NSIS只读检查证据：' + output);
}
