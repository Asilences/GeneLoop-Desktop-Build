"""Install the pinned upstream Gitleaks asset for Linux/Windows x64 checks."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.adapters.rsi_privacy_tools import TOOLS, gitleaks_asset

VERSION=TOOLS['gitleaks']['version']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--archive',type=Path,help='offline copy of the same official asset')
    args=parser.parse_args()
    try:
        specification=gitleaks_asset()
    except ValueError:
        parser.error('this installer supports the verified Linux/Windows x64 assets only')
    asset,expected,binary=(specification[name] for name in ('asset','archive_sha256','binary'))
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
    if not data or len(data)>64*1024*1024 or hashlib.sha256(data).hexdigest()!=specification['binary_sha256']:
        parser.error('upstream binary checksum mismatch')
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
