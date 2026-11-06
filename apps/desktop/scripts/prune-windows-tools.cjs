// Only trim the generated Windows payload; never modify tool sources or user installs.
const fs = require('node:fs');
const path = require('node:path');

module.exports = function pruneWindowsTools(resources) {
  const tools = fs.realpathSync(path.join(resources, 'geneloop-tools'));
  const result = { removedFiles: 0, removedBytes: 0, removedTestDirectories: 0, removedCacheDirectories: 0 };
  // NumPy 2.x imports this helper from numpy.testing during ordinary SciPy use.
  const retained = new Set(['python/site/numpy/_core/tests/_natype.py', 'python/site/numpy/_core/tests/__init__.py']);
  function trimCache(dir) {
    const relative = path.relative(tools, dir).replaceAll('\\', '/');
    const officeVersion = /python-core-(\d+)\.(\d+)/.exec(relative);
    const tag = relative.startsWith('python/') ? 'cpython-312' : officeVersion ? 'cpython-' + officeVersion[1] + officeVersion[2] : null;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isSymbolicLink() || entry.isDirectory()) throw Error('Python缓存目录结构异常');
      // Keep bytecode matching the bundled interpreter; avoid making first use recompile it.
      if (tag && entry.name.includes('.' + tag + '.') && entry.name.endsWith('.pyc')) continue;
      inside(file); result.removedFiles++; result.removedBytes += fs.statSync(file).size; fs.unlinkSync(file);
    }
    if (!fs.readdirSync(dir).length) { inside(dir); fs.rmdirSync(dir); }
  }
  function trimTestTree(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isSymbolicLink()) throw Error('待裁剪目录包含链接');
      if (entry.isDirectory()) trimTestTree(file);
      else if (!retained.has(path.relative(tools, file).replaceAll('\\', '/'))) {
        inside(file); result.removedFiles++; result.removedBytes += fs.statSync(file).size; fs.unlinkSync(file);
      }
    }
    if (!fs.readdirSync(dir).length) { inside(dir); fs.rmdirSync(dir); }
  }
  function inside(file) {
    const relative = path.relative(tools, fs.realpathSync(file));
    if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) throw Error('工具裁剪路径越界');
  }
  function count(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isSymbolicLink()) throw Error('待裁剪目录包含链接');
      if (entry.isDirectory()) count(file);
      else { result.removedFiles++; result.removedBytes += fs.statSync(file).size; }
    }
  }
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory()) {
        // Keep runtime namespaces such as numpy.testing and scipy._lib._testutils.
        if (['tests', 'test', '__pycache__', '.pytest_cache'].includes(entry.name)) {
          inside(file);
          if (entry.name === '__pycache__') trimCache(file);
          else if (path.relative(tools, file).replaceAll('\\', '/') === 'python/site/numpy/_core/tests') trimTestTree(file);
          else { count(file); fs.rmSync(file, { recursive: true }); }
          if (!fs.existsSync(file)) result[entry.name === '__pycache__' || entry.name === '.pytest_cache' ? 'removedCacheDirectories' : 'removedTestDirectories']++;
        } else walk(file);
      } else if (entry.name.endsWith('.pyc') && fs.existsSync(file.slice(0, -1))) {
        inside(file); result.removedFiles++; result.removedBytes += fs.statSync(file).size; fs.unlinkSync(file);
      }
    }
  }
  walk(path.join(tools, 'python'));
  const program = path.join(tools, 'libreoffice', 'program');
  for (const entry of fs.readdirSync(program, { withFileTypes: true })) {
    if (entry.isDirectory() && entry.name.startsWith('python-core-')) walk(path.join(program, entry.name));
  }
  console.log('Windows runtime payload trim: ' + JSON.stringify(result));
  return result;
};
