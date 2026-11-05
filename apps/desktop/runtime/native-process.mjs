// Use the upstream managed process range: cancellation joins descendants on
// Windows and macOS. Generated programs only receive a staged scratch folder.
export async function runNativeProcess(ctx, argv, cwd, signal, {confine = false, timeoutMs = 450_000} = {}) {
  signal.throwIfAborted();
  const local = confine ? ctx.sandbox.confine(argv, {mode:'workspace-write', workspaceRoot:cwd}) : {argv};
  const timeout = AbortSignal.timeout(timeoutMs);
  const abort = AbortSignal.any([signal, timeout]);
  const env = {
    HOME:cwd, USERPROFILE:cwd, APPDATA:cwd, LOCALAPPDATA:cwd,
    TEMP:cwd, TMP:cwd, TMPDIR:cwd, ELECTRON_RUN_AS_NODE:'1',
    NODE_OPTIONS:undefined, NODE_PATH:undefined,
  };
  const child = ctx.subprocess.spawn({argv:local.argv, cwd, env, signal:abort, graceMs:1000,
    stdio:{stdin:'ignore',stdout:{maxBytes:2*1024*1024},stderr:{maxBytes:64*1024}}});
  const result = await child.done;
  signal.throwIfAborted();
  timeout.throwIfAborted();
  if (result.exitCode !== 0) throw Error('本机工具执行失败。', {cause:new Error(child.collected.stderr.readFrom(0).text)});
  return {stdout:child.collected.stdout.readFrom(0).text, enforcement:local.enforcement};
}
