"""Host-frozen delivery predicates run INSIDE the normal acceptance/repair loop.

The task preparer owns this data. No arbitrary verifier command or code path is
accepted from model tools. Old tasks without this extension retain their checks.
"""
from __future__ import annotations
from pathlib import Path
import json,re
from common import digest,sha

FORMAT='sss-file-delivery-v1'
KEYS={'format','copies','moves','overwrites','categories','preserve_originals','exact_tree','require_reads',
      'redactions','search_queries','report_terms','restore_initial'}


def verify_delivery(spec,report,state,output,actual):
    contract=spec.get('quality',{}).get('delivery_contract')
    if contract is None:return []
    if not isinstance(contract,dict) or contract.get('format')!=FORMAT or set(contract)-KEYS:
        return ['unknown frozen File delivery contract']
    errors=[];initial=spec['initial_tree']['workspace'];current=actual['workspace'];expected=dict(initial['files'])
    overwrites=contract.get('overwrites',{})
    if not isinstance(overwrites,dict):return ['invalid frozen overwrite mapping']
    if contract.get('preserve_originals',True):
        for name,h in initial['files'].items():
            if name in overwrites:continue
            if current['files'].get(name)!=h:errors.append('original bytes missing/changed: '+name)
    copies=contract.get('copies',{})
    if not isinstance(copies,dict):return ['invalid frozen copy mapping']
    for target,source in copies.items():
        if source not in initial['files']:errors.append('invalid frozen original source: '+source);continue
        expected[target]=initial['files'][source]
        if current['files'].get(target)!=expected[target]:errors.append('required copy missing or wrong: '+target)
    moves=contract.get('moves',{})
    if not isinstance(moves,dict) or len(set(moves.values()))!=len(moves):return ['invalid frozen move mapping']
    for target,source in moves.items():
        if source not in initial['files']:errors.append('invalid frozen move source: '+source);continue
        expected.pop(source,None);expected[target]=initial['files'][source]
        if current['files'].get(target)!=expected[target] or source in current['files']:errors.append('move missing, duplicated or wrong: '+source)
    for target,source in overwrites.items():
        if target not in initial['files'] or source not in initial['files']:errors.append('invalid frozen overwrite source/destination');continue
        expected[target]=initial['files'][source]
        if current['files'].get(target)!=expected[target]:errors.append('required version replacement missing: '+target)
        witnessed=any(j['status']=='executed_verified' and any(a['op']=='overwrite' and a['source_root']=='workspace'
            and a['source']==source and a['destination_root']=='workspace' and a['destination']==target
            for a in state['plans'][pid]['actions']) for pid,j in state['journals'].items())
        if not witnessed:errors.append('version replacement lacks actual confirmed overwrite: '+target)
    categories=contract.get('categories')
    if categories:
        prefixes=categories['prefixes'];source_names=categories['sources'];counts={name:0 for name in source_names}
        for name,h in current['files'].items():
            if name in initial['files']:continue
            matches=[p for p in prefixes if name.startswith(p+'/')]
            if len(matches)!=1:errors.append('output outside category directories: '+name);continue
            relative=name[len(matches[0])+1:]
            source=next((s for s in source_names if Path(s).name==relative),None)
            if source is None or h!=initial['files'][source]:errors.append('category copy has wrong source: '+name);continue
            counts[source]+=1;expected[name]=h
        for source,count in counts.items():
            if not categories.get('min_copies',1)<=count<=categories.get('max_copies',2):errors.append('category coverage/count differs: '+source)
    if contract.get('exact_tree'):
        if current['files']!=expected:errors.append('complete delivered file set differs; extra copies are not accepted')
        directories=set(initial['directories'])
        for target in expected:
            parts=target.split('/')
            directories.update('/'.join(parts[:i]) for i in range(1,len(parts)))
        if set(current['directories'])!=directories:errors.append('complete delivered directory set differs')
    if contract.get('restore_initial') and current!=initial:errors.append('restoration is not the exact initial tree')
    from management_reading import coverage
    for wanted in contract.get('require_reads',[]):
        name=wanted['path'];mode=wanted.get('mode');key='workspace/'+name;h=initial['files'][name]
        documents=[d for d in state.get('documents',{}).values() if d['anchor']['path']==key and d['anchor']['sha256']==h and (mode is None or d['mode']==mode)]
        complete=any(coverage(d)['complete'] for d in documents)
        normal=[r for r in state.get('reads',{}).values() if r['path']==key and r['sha256']==h and r.get('status')=='readable'
                and not r.get('truncated') and not r.get('metadata',{}).get('preview_only')]
        if not complete and not (mode is None and normal):errors.append('required actual full read missing: '+name)
    for wanted in contract.get('redactions',[]):
        name=wanted['source'];original=Path(spec['workspace'])/name
        if sha(original)!=initial['files'][name]:errors.append('redaction original changed: '+name);continue
        expected_bytes=original.read_bytes()
        for replacement in wanted['replacements']:
            old=replacement['old'].encode('utf-8');new=replacement['new'].encode('utf-8')
            if expected_bytes.count(old)!=replacement['count']:errors.append('frozen redaction count differs: '+name)
            expected_bytes=expected_bytes.replace(old,new)
        candidates=[p for p in (Path(output)/'general/work/outputs').rglob(wanted['destination']) if p.is_file()]
        if len(candidates)!=1 or candidates[0].read_bytes()!=expected_bytes:errors.append('redaction copy missing, duplicated or not exact: '+wanted['destination'])
    for query in contract.get('search_queries',[]):
        receipts=[r for r in state.get('search_receipts',{}).values() if r.get('query')==query and r.get('snapshot_sha256')==digest(actual)]
        if not receipts:errors.append('current literal-search receipt missing: '+query)
    summary=report.get('summary','').casefold()
    for term in contract.get('report_terms',[]):
        if term.casefold() not in summary:errors.append('report required evidence identifier missing: '+term)
    return errors
