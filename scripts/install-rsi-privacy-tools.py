"""Install the pinned upstream Gitleaks asset for Linux/Windows x64 checks."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import urllib.request
import zipfile

VERSION='8.30.0'
# Official GitHub Release API asset digests, checked on 2026-11-06.
ASSETS={
    'Linux':('linux_x64.tar.gz','79a3ab579b53f71efd634f3aaf7e04a0fa0cf206b7ed434638d1547a2470a66e','gitleaks'),
    'Windows':('windows_x64.zip','54fe94f644b832dd08e8c3a5915efb3bfa862386d59fb27ca0792cb687a83573','gitleaks.exe'),
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--archive',type=Path,help='offline copy of the same official asset')
    args=parser.parse_args()
    if platform.machine().lower() not in ('x86_64','amd64') or platform.system() not in ASSETS:
        parser.error('this installer supports the verified Linux/Windows x64 assets only')
    asset,expected,binary=ASSETS[platform.system()]
    url=f'https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/gitleaks_{VERSION}_{asset}'
    if args.archive:
        with args.archive.open('rb') as stream:raw=stream.read(64*1024*1024+1)
    else:
        request=urllib.request.Request(url,headers={'User-Agent':'GeneLoop-pinned-privacy-tools'})
        with urllib.request.urlopen(request,timeout=60) as response:raw=response.read(64*1024*1024+1)
    if len(raw)>64*1024*1024 or hashlib.sha256(raw).hexdigest()!=expected:
        parser.error('upstream archive checksum mismatch; nothing installed')
    if asset.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:data=archive.read(binary)
    else:
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
            member=archive.getmember(binary)
            if not member.isfile():parser.error('upstream binary must be a regular file')
            data=archive.extractfile(member).read(64*1024*1024+1)
    if not data or len(data)>64*1024*1024:parser.error('invalid upstream binary')
    root=args.root.absolute()
    if root.is_symlink() or root.resolve()!=root or '\n' in str(root) or '\r' in str(root):
        parser.error('an ordinary private installation directory is required')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=root/binary
    if target.exists() or target.is_symlink():parser.error('destination exists; keep the existing installation')
    with target.open('xb') as stream:stream.write(data)
    target.chmod(0o700)
    environment={key:os.environ[key] for key in ('PATH','SYSTEMROOT','WINDIR') if key in os.environ}
    version=subprocess.run([str(target),'version'],env=environment,capture_output=True,text=True,check=True,timeout=10).stdout.strip()
    if version!=VERSION:parser.error('upstream binary version mismatch')
    (root/'installation.json').write_text(json.dumps({'version':VERSION,'url':url,'archive_sha256':expected,
        'binary_sha256':hashlib.sha256(data).hexdigest()},indent=2)+'\n',encoding='utf-8')
    (root/'installation.json').chmod(0o600)
    print(target)


if __name__=='__main__':main()
