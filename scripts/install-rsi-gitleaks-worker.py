"""Build the pinned official-library adapter outside product/service directories."""
import argparse,hashlib,json,os,pathlib,platform,subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--go',type=pathlib.Path,required=True)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    args=parser.parse_args()
    root=pathlib.Path(__file__).resolve().parents[1]
    spec=json.loads((root/'config/rsi-gitleaks-worker-tools.json').read_text())
    if platform.machine().lower() not in ('amd64','x86_64'):raise ValueError('unsupported_worker_platform')
    target=spec['platforms'].get(platform.system()+'-x64')
    if target is None:raise ValueError('unsupported_worker_platform')
    for name,digest in spec['source_files'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('worker_build_source_changed')
    version=subprocess.check_output([str(args.go),'version'],text=True).split()
    if len(version)<3 or version[2]!=spec['go']:raise ValueError('worker_toolchain_version_mismatch')
    output=args.output.absolute()
    if output.exists():raise ValueError('new_worker_output_required')
    output.parent.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'GOTOOLCHAIN':'local','CGO_ENABLED':'0','GOARCH':'amd64','GOAMD64':'v1',
         'GOOS':'windows' if platform.system()=='Windows' else 'linux'}
    source=root/'tools/gitleaks-worker'
    subprocess.run([str(args.go),'mod','verify'],cwd=source,env=env,check=True)
    subprocess.run([str(args.go),'build','-mod=readonly','-trimpath','-buildvcs=false','-tags=gore2regex',
                    '-ldflags=-s -w','-o',str(output),'.'],cwd=source,env=env,check=True)
    if hashlib.sha256(output.read_bytes()).hexdigest()!=target['binary_sha256']:
        raise ValueError('worker_build_bytes_mismatch')
    print('Pinned Gitleaks worker verified; enable only through trusted host configuration.')


if __name__=='__main__':main()
