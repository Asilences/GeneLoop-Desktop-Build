"""Frozen literal-document oracle. Never imports or executes candidate source.

Scope: brace-delimited BibTeX, literal input/include/bibliography/addbibresource
and cite/citep/citet/citeauthor/citeyear/parencite/textcite/autocite commands.
No TeX expansion, external references, document compilation or factual review.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import PurePosixPath
import re
import zipfile

from src.adapters.paper_bibliography import bib_records


def sha(raw):
    return hashlib.sha256(raw if isinstance(raw,bytes) else raw.encode('utf-8')).hexdigest()


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def uncomment(text):
    result=[]
    for line in text.splitlines(keepends=True):
        cut=len(line)
        for i,ch in enumerate(line):
            if ch!='%':continue
            back=i-1
            while back>=0 and line[back]=='\\':back-=1
            if (i-1-back)%2==0:cut=i;break
        result.append(line[:cut]+('\n' if cut<len(line) else ''))
    return ''.join(result)


def commands(text):
    """Scan balanced literal brace arguments, independently of model regexes."""
    text=uncomment(text);i=0
    while i<len(text):
        if text[i]!='\\':i+=1;continue
        match=re.match(r'\\([A-Za-z]+)\*?',text[i:])
        if not match:i+=2;continue
        name=match.group(1);i+=len(match.group());j=i
        while j<len(text) and text[j].isspace():j+=1
        while j<len(text) and text[j]=='[':
            depth=1;j+=1
            while j<len(text) and depth:
                if text[j]=='\\':j+=2;continue
                depth+=(text[j]=='[')-(text[j]==']');j+=1
            while j<len(text) and text[j].isspace():j+=1
        if j>=len(text) or text[j]!='{':continue
        start=j+1;depth=1;j+=1
        while j<len(text) and depth:
            if text[j]=='\\':j+=2;continue
            depth+=(text[j]=='{')-(text[j]=='}');j+=1
        if depth==0:
            argument=text[start:j-1]
            if not any(c in argument for c in ('#','\\','{','}')):yield name,argument
        # Do not skip the body: literal nested commands remain observable.


def archive(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or len(names)>500:raise ValueError('frontier_archive_inventory_invalid')
        files={}
        for name in names:
            p=PurePosixPath(name)
            if name.startswith('/') or '..' in p.parts or str(p)!=name:raise ValueError('frontier_archive_path_invalid')
            if z.getinfo(name).file_size>2_000_000:raise ValueError('frontier_archive_file_too_large')
            files[name]=z.read(name)
    config=json.loads(files.pop('geneloop-project.json'))
    root=config['root']
    if root not in files or not root.endswith('.tex'):raise ValueError('frontier_root_invalid')
    return root,files


def bibliography(path):
    _,files=archive(path);entries=[];versions=[]
    for name,raw in sorted(files.items()):
        if not name.endswith('.bib'):continue
        versions.append({'path':name,'sha256':sha(raw)})
        entries.extend({'path':name,'key':row['key'],'sha256':sha(row['raw'])}
                       for row in bib_records(raw.decode('utf-8-sig')))
    return {'bib_files':versions,'entries':sorted(entries,key=canonical)}


def latex(path):
    root,files=archive(path);pending=[root];seen=set();includes=[];bibliographies=[];citations=set();unresolved=set();versions=[]
    cite_names={'cite','citep','citet','citeauthor','citeyear','parencite','textcite','autocite'}
    while pending:
        current=pending.pop()
        if current in seen:continue
        seen.add(current);versions.append({'path':current,'sha256':sha(files[current])})
        for kind,arg in commands(files[current].decode('utf-8-sig')):
            if kind in cite_names:
                citations.update((current,key.strip()) for key in arg.split(',') if key.strip() and key.strip()!='*')
            if kind not in ('input','include','bibliography','addbibresource'):continue
            for item in arg.split(','):
                name=item.strip()
                if not name:continue
                extension='.tex' if kind in ('input','include') else '.bib'
                target=name if name.endswith(extension) else name+extension
                target=str(PurePosixPath(target))
                exists=target in files and not target.startswith('/') and '..' not in PurePosixPath(target).parts
                row={'parent':current,'child':target,'exists':exists}
                (includes if extension=='.tex' else bibliographies).append(row)
                if not exists:unresolved.add(target)
                elif extension=='.tex':pending.append(target)
    return {'root':root,'tex_files':sorted(versions,key=canonical),'includes':sorted(includes,key=canonical),
            'bibliography':sorted(bibliographies,key=canonical),
            'citations':[{'path':p,'key':k} for p,k in sorted(citations)],'unresolved':sorted(unresolved)}


def audit(path):
    bib,tex=bibliography(path),latex(path)
    active={r['child'] for r in tex['bibliography'] if r['exists']}
    entries=[r for r in bib['entries'] if r['path'] in active]
    counts=Counter(r['key'] for r in entries);used={r['key'] for r in tex['citations']}
    versions=[{**r,'kind':'tex'} for r in tex['tex_files']]
    versions.extend({**r,'kind':'bib'} for r in bib['bib_files'] if r['path'] in active)
    return {'root':tex['root'],'files':sorted(versions,key=canonical),'includes':tex['includes'],
            'bibliography':tex['bibliography'],'citations':tex['citations'],'entries':entries,
            'missing':sorted(used-set(counts)),'duplicates':sorted(k for k,n in counts.items() if n>1),
            'unused':sorted(set(counts)-used),'unresolved':tex['unresolved']}


def compare(before,after):
    """New global relation: entry changes -> citing files -> include ancestors."""
    old,new=audit(before),audit(after)
    def versions(report):return {r['path']:r['sha256'] for r in report['files']}
    def entries(report):
        d=defaultdict(list)
        for r in report['entries']:d[r['key']].append((r['path'],r['sha256']))
        return {k:sorted(v) for k,v in d.items()}
    ov,nv=versions(old),versions(new);oe,ne=entries(old),entries(new)
    changed=sorted(k for k in ov.keys()|nv.keys() if ov.get(k)!=nv.get(k))
    changed_keys=sorted(k for k in oe.keys()|ne.keys() if oe.get(k)!=ne.get(k))
    tex={r['path'] for r in old['files']+new['files'] if r['kind']=='tex'}
    affected=set(changed)&tex
    affected.update(r['path'] for r in old['citations']+new['citations'] if r['key'] in changed_keys)
    reverse=defaultdict(set)
    for r in old['includes']+new['includes']+old['bibliography']+new['bibliography']:
        if r['exists']:reverse[r['child']].add(r['parent'])
    queue=list(set(changed)|affected)
    while queue:
        item=queue.pop()
        for parent in reverse[item]-affected:affected.add(parent);queue.append(parent)
    result={'before_root':old['root'],'after_root':new['root'],'changed_files':changed,
            'changed_entry_keys':changed_keys,'affected_tex_files':sorted(affected&tex),
            'before_files_digest':sha(canonical(old['files'])),'after_files_digest':sha(canonical(new['files'])),
            'after_has_errors':bool(new['missing'] or new['duplicates'] or new['unresolved'])}
    for label,key in [('missing','missing'),('duplicates','duplicates')]:
        result['introduced_'+label]=sorted(set(new[key])-set(old[key]))
        result['resolved_'+label]=sorted(set(old[key])-set(new[key]))
    result['newly_unused']=sorted(set(new['unused'])-set(old['unused']))
    result['now_used']=sorted(set(old['unused'])-set(new['unused']))
    return result


def evaluate(kind,paths,value):
    expected={'bib':bibliography,'tex':latex,'C':audit,'D':compare}[kind](*paths)
    checks=[]
    if not isinstance(value,dict):return {'passed':False,'checks':[{'id':'output_shape','status':'failed','observation':'Expected JSON object'}]}
    checks.append({'id':'output_fields','status':'passed' if set(value)==set(expected) else 'failed',
                   'observation':canonical({'expected':sorted(expected),'actual':sorted(value)})})
    for key,target in expected.items():
        actual=value.get(key)
        # Reports are canonical collections; array order is part of the frozen contract.
        normalized=lambda v:sorted(v,key=canonical) if isinstance(v,list) else v
        ok=type(actual) is type(target) and canonical(normalized(actual))==canonical(normalized(target))
        checks.append({'id':key,'status':'passed' if ok else 'failed',
                       'observation':'matches independent literal oracle' if ok else canonical({'expected':target,'actual':actual})[:16000]})
    return {'passed':all(r['status']=='passed' for r in checks),'checks':checks,
            'scope':'literal_multifile_citation_consistency_and_version_dependencies',
            'limitations':['No TeX expansion or bibliography authenticity review','Controlled changes on real project copies; not natural longitudinal usage']}
