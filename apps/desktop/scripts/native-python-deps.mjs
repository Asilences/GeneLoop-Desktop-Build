// Keep the current upstream crypto version on Intel macOS, where official
// wheels are no longer published. Compile only at build time, never on users' PCs.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {existsSync,mkdirSync,readFileSync,readdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
const cryptoSource={version:'50.0.2',sha256:'7b46165bb56eb4704e2eaaf86f3c940d19154535d9b0ca7d6d590b04060e00d5',
 url:'https://files.pythonhosted.org/packages/9d/af/182eb91b0df3fe75c4d9f26fe70684569566745f6ba7e5c9c73a862c5252/cryptography-50.0.2.tar.gz'};
export function installNativePythonDeps(python,app) {
  const run=(exe,args,env=process.env)=>{const r=spawnSync(exe,args,{stdio:'inherit',env});assert.equal(r.status,0,'native Python dependency build failed');};
  const extra=[];
  if(process.platform==='darwin'&&process.arch==='x64') {
    const cache=join(app,'.local','crypto-intel');mkdirSync(cache,{recursive:true});
    const source=join(cache,'cryptography-'+cryptoSource.version+'.tar.gz');
    if(!existsSync(source))run('curl',['--fail','--location','--retry','2','--output',source,cryptoSource.url]);
    assert.equal(createHash('sha256').update(readFileSync(source)).digest('hex'),cryptoSource.sha256);
    const prefix=spawnSync('brew',['--prefix','openssl@3'],{encoding:'utf8'});assert.equal(prefix.status,0,'Intel build needs the build host OpenSSL development library');
    const openssl=prefix.stdout.trim();assert.ok(existsSync(join(openssl,'lib/libssl.a'))&&existsSync(join(openssl,'lib/libcrypto.a')),'OpenSSL static libraries required');
    if(!readdirSync(cache).some(name=>/^cryptography-50\.0\.2-.*\.whl$/.test(name)))
      run(python,['-m','pip','wheel','--no-deps','--wheel-dir',cache,source],{...process.env,OPENSSL_DIR:openssl,OPENSSL_STATIC:'1'});
    const wheel=readdirSync(cache).find(name=>/^cryptography-50\.0\.2-.*\.whl$/.test(name));assert.ok(wheel);
    writeFileSync(join(cache,'provenance.json'),JSON.stringify({platform:'darwin',arch:'x64',source:cryptoSource,
      wheel,sha256:createHash('sha256').update(readFileSync(join(cache,wheel))).digest('hex'),staticOpenSSL:true},null,2)+'\n');
    extra.push('--find-links',cache);
  }
  run(python,['-m','pip','install','--only-binary=:all:',...extra,'-r',join(app,'native-tools-requirements.txt'),'-c',join(app,'native-tools-constraints.txt')]);
}
