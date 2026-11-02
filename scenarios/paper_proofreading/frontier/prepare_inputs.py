"""Prepare deterministic copies and controlled versions before model execution."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import tarfile
import zipfile

from src.adapters.paper_bibliography import bib_records
from scenarios.paper_proofreading.frontier.oracle import audit,compare,canonical,sha


def from_tar(path):
    files={}
    with tarfile.open(path) as tar:
        for row in tar.getmembers():
            if not row.isfile() or not row.name.endswith(('.tex','.bib')):continue
            name=row.name.removeprefix('./');p=PurePosixPath(name)
            if name.startswith('/') or '..' in p.parts or row.size>2_000_000:raise ValueError('unsafe_source_member')
            raw=tar.extractfile(row).read();raw.decode('utf-8-sig');files[name]=raw
    return files


def roots(files):
    return [name for name,raw in files.items() if name.endswith('.tex') and re.search(rb'(?m)^\s*\\documentclass',raw)]


def write_project(path,root,files):
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        rows={**files,'geneloop-project.json':canonical({'root':root}).encode()}
        for name,raw in sorted(rows.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.external_attr=0o100400<<16
            archive.writestr(info,raw,compress_type=zipfile.ZIP_DEFLATED)
    path.chmod(0o400)


def perturb(files,root,report,project_id):
    v1=dict(files);v2=dict(files)
    chosen=next(r for r in report['citations'] if r['key'] in {e['key'] for e in report['entries']})
    key,path=chosen['key'],chosen['path'];text=files[path].decode('utf-8-sig')
    pattern=r'\\(?:cite|citep|citet|citeauthor|citeyear|parencite|textcite|autocite)\*?(?:\s*\[[^\]]*\])*\s*\{([^{}]*)\}'
    for m in re.finditer(pattern,text):
        if key not in [s.strip() for s in m.group(1).split(',')]:continue
        parts=[('FrontierMissing_'+project_id) if s.strip()==key else s.strip() for s in m.group(1).split(',')]
        v1[path]=(text[:m.start(1)]+','.join(parts)+text[m.end(1):]).encode();break
    else:raise ValueError('controlled_citation_edit_not_found')
    entry=next(e for e in report['entries'] if e['key']!=key)
    bib_path=entry['path'];raw=files[bib_path].decode('utf-8-sig')
    record=next(r for r in bib_records(raw) if r['key']==entry['key'])['raw']
    v1[bib_path]=(raw+'\n'+record+'\n').encode()
    # v2 resolves the two v1 interventions and changes a real record's bytes.
    modified=record.replace('=', '= ',1) if '=' in record else record.replace(',',', ',1)
    v2[bib_path]=raw.replace(record,modified,1).encode()
    extra='frontier-extra.tex';extra_key=report['unused'][0] if report['unused'] else key
    v2[extra]=('% controlled derivative for dependency evaluation\n\\cite{'+extra_key+'}\n').encode()
    main=files[root].decode('utf-8-sig');position=main.rfind('\\end{document}')
    insertion='\n\\input{frontier-extra}\n'
    v2[root]=(main[:position]+insertion+main[position:] if position>=0 else main+insertion).encode()
    return v1,v2,{'missing_key':'FrontierMissing_'+project_id,'replaced_citation_key':key,
                  'duplicated_key':entry['key'],'added_tex':extra,'added_citation_key':extra_key}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--atc',type=Path,required=True)
    p.add_argument('--lora',type=Path,required=True);p.add_argument('--qlora',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    atc={str(f.relative_to(a.atc)):f.read_bytes() for f in a.atc.rglob('*') if f.is_file() and f.suffix in ('.tex','.bib')}
    specs=[('atc',atc,'main.tex','user_accepted_paper_source',None),
           ('lora',from_tar(a.lora),None,'https://arxiv.org/src/2106.09685v2',sha(a.lora.read_bytes())),
           ('qlora',from_tar(a.qlora),None,'https://arxiv.org/src/2305.14314v1',sha(a.qlora.read_bytes()))]
    manifest={'format':'frontier_inputs_v1','projects':[],'originals_modified':False,
              'controlled_versions_not_natural_user_history':True,'roles':{
                  'primitive_source':'atc-v0','primitive_native_certification':'lora-v0',
                  'C_validation':'atc-v1','C_followup':'lora-v1',
                  'D_program_examples':['atc-v0-to-v1','lora-v0-to-v1'],
                  'D_validation':'atc-v1-to-v2','D_followup':'lora-v1-to-v2',
                  'final_test':['qlora-v0-to-v1','qlora-v1-to-v2']}}
    for name,files,root,origin,source_sha in specs:
        candidates=roots(files)
        if root is None:
            if len(candidates)!=1:raise ValueError('ambiguous_root:'+str(candidates))
            root=candidates[0]
        original={k:sha(v) for k,v in files.items()};v0=a.output/(name+'-v0.zip');write_project(v0,root,files)
        baseline=audit(v0);v1,v2,edits=perturb(files,root,baseline,name)
        rows=[]
        for version,data in [(0,files),(1,v1),(2,v2)]:
            path=a.output/f'{name}-v{version}.zip'
            if version:write_project(path,root,data)
            result=audit(path)
            (a.output/f'{name}-v{version}.oracle.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
            rows.append({'version':version,'file':path.name,'sha256':sha(path.read_bytes()),
                         'tex_files':len([r for r in result['files'] if r['kind']=='tex']),
                         'entries':len(result['entries']),'citations':len(result['citations']),
                         'unresolved':result['unresolved']})
        for old,new in [(0,1),(1,2)]:
            result=compare(a.output/f'{name}-v{old}.zip',a.output/f'{name}-v{new}.zip')
            (a.output/f'{name}-v{old}-v{new}.oracle.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        manifest['projects'].append({'id':name,'source':origin,'source_archive_sha256':source_sha,
          'root':root,'source_files':original,'versions':rows,'controlled_edits':edits})
    (a.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    assert atc=={str(f.relative_to(a.atc)):f.read_bytes() for f in a.atc.rglob('*') if f.is_file() and f.suffix in ('.tex','.bib')}
    print(json.dumps({r['id']:r['versions'] for r in manifest['projects']},ensure_ascii=False))


if __name__=='__main__':main()
