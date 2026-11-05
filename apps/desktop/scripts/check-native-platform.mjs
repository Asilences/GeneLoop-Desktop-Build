import assert from 'node:assert/strict';
import { mkdtempSync, realpathSync, mkdirSync, writeFileSync, readFileSync, symlinkSync, linkSync, statSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { openWorkspaceReader, openReportWriter } from '../runtime/local-files.mjs';

const root = realpathSync(mkdtempSync(join(tmpdir(),'geneloop-platform-')));
try {
  const workspace = join(root,'中文工作区');
  mkdirSync(workspace);
  writeFileSync(join(workspace,'source.txt'),'original');
  writeFileSync(join(root,'outside.txt'),'outside');
  const reader = openWorkspaceReader(workspace), writer = openReportWriter(workspace);
  try {
    assert.equal(reader.readText('source.txt'),'original');
    assert.deepEqual(reader.list(),reader.list(),'重复列目录必须返回相同结果');
    assert.throws(()=>reader.readText('../outside.txt'));
    assert.throws(()=>reader.readText(join(root,'outside.txt')));
    if (process.platform !== 'win32') {
      symlinkSync(join(root,'outside.txt'),join(workspace,'alias.txt'));
      assert.throws(()=>reader.readText('alias.txt'));
      symlinkSync(root,join(workspace,'alias-dir'));
      assert.throws(()=>reader.list('alias-dir'));
    }
    linkSync(join(workspace,'source.txt'),join(root,'source-hardlink.txt'));
    assert.throws(()=>reader.readText('source.txt'),'拒绝多链接文件');
    const first = writer.writeMarkdown('# 本机验证');
    const second = writer.writeMarkdown('# 第二份');
    assert.notEqual(first.name,second.name);
    assert.equal(readFileSync(join(workspace,'GeneLoop 输出',first.name),'utf8'),'# 本机验证');
    if (process.platform !== 'win32') {
      assert.equal(statSync(join(workspace,'GeneLoop 输出',first.name)).mode & 0o777,0o600,'产物须可由当前用户读写且不向其他用户开放');
      assert.equal(statSync(join(workspace,'GeneLoop 输出')).mode & 0o777,0o700,'输出目录仅对当前用户开放');
    }
    assert.equal(readFileSync(join(workspace,'source.txt'),'utf8'),'original');
  } finally {reader.close();writer.close();}
  assert.throws(()=>reader.list());
  assert.throws(()=>writer.writeMarkdown('closed'));
  if (process.platform !== 'win32') {
    const blocked = join(root,'blocked');mkdirSync(blocked);
    symlinkSync(root,join(blocked,'GeneLoop 输出'));
    const writer2 = openReportWriter(blocked);
    try {assert.throws(()=>writer2.writeMarkdown('escape'));} finally {writer2.close();}
  }
  console.log(JSON.stringify({diagnostic:true,platform:process.platform,arch:process.arch,
    checks:['read','repeat-list','path-traversal','hardlink','output','revocation',...(process.platform==='win32'?[]:['symlink','output-symlink'])]}));
} finally {
  assert.ok(root.startsWith(realpathSync(tmpdir())+'/') || root.startsWith(realpathSync(tmpdir())+'\\'));
  rmSync(root,{recursive:true,force:true});
}
