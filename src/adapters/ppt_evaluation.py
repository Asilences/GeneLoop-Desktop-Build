"""Offline PPT review: exact final-version selection and bound evidence IDs.

No service state, model call, or scientific verdict is produced here. A replayed
preview is evaluation evidence; it does not repair the generator's delivery.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import PurePosixPath
import re
from urllib.parse import unquote

SHA=re.compile(r'[a-f0-9]{64}')


def select_pptx(rows,answer,*,previous_sha256=None):
    """Select only host-proven bytes; never rank by mtime or visual preference."""
    eligible=[]
    for row in rows:
        name=row.get('name','');path=PurePosixPath(name)
        if (not isinstance(name,str) or '\\' in name or path.is_absolute() or '..' in path.parts or
            path.suffix.lower()!='.pptx' or not SHA.fullmatch(row.get('sha256','')) or row.get('host_verified') is not True):
            continue
        eligible.append(row)
    if not eligible:raise ValueError('no_host_verified_PPTX')
    text=unquote(answer or '')
    # The closing answer can reference an output basename in a code span as
    # well as a Markdown link. It cannot confer authority without host proof.
    mentioned=[r for r in eligible if re.search(r'(?<![\w.])'+re.escape(PurePosixPath(r['name']).name)+r'(?![\w.])',text)]
    pool=mentioned or eligible
    if previous_sha256 and len({r['sha256'] for r in pool})>1:
        changed=[r for r in pool if r['sha256']!=previous_sha256]
        if changed:pool=changed
    versions={r['sha256'] for r in pool}
    if len(versions)!=1:raise ValueError('ambiguous_final_PPTX_no_mtime_ranking')
    # Identical-byte renamed/export aliases are one version, not ambiguity.
    chosen=sorted(pool,key=lambda r:(not r['name'].startswith('outputs/'),len(r['name']),r['name']))[0]
    return {**chosen,'selection_rule':'closing_answer_and_host_sha' if mentioned else 'unique_host_sha',
            'same_version_aliases':sorted({r['name'] for r in eligible if r['sha256']==chosen['sha256']}),
            'original_delivery_quality_repaired':False}


def evidence_catalog(context):
    rows=[]
    for item in context['artifact_evidence']:
        rows.append({'kind':'artifact',**item})
    for source in context['source_papers_full_page_text']:
        for page in source['pages']:
            rows.append({'kind':'source_page','ref':page['ref'],'sha256':source['sha256'],
                         'source_id':source['source_id'],'source_page':page['physical_page']})
    for slide in context['slides']:
        rows.append({'kind':'slide_text','ref':slide['text_ref'],'sha256':slide['text_sha256'],'slide':slide['slide']})
    for image in context['image_evidence_manifest']:
        rows.append({'kind':'slide_image','ref':image['ref'],'sha256':image['sha256'],'slide':image['slide']})
    for image in context.get('source_figure_image_evidence',[]):
        rows.append({'kind':'source_image','ref':image['ref'],'sha256':image['sha256'],
                     'source_id':image['source_id'],'source_page':image['physical_page']})
    return [{'evidence_id':f'E{n:04d}',**row} for n,row in enumerate(rows,1)]


def bind_evidence_ids(result,catalog,*,expected_bindings,artifact_id,slide_count):
    """Host resolves explicit IDs; guessed/missing citations do not gain a pass."""
    value=copy.deepcopy(result);index={r['evidence_id']:r for r in catalog}
    if len(index)!=len(catalog):raise ValueError('duplicate_evidence_id')
    for key,wanted in {'artifact_id':artifact_id,**expected_bindings}.items():
        supplied=value.get(key)
        # Avoid requiring the model to copy cryptographic strings. If it does
        # supply a conflicting identity, reject rather than silently rewriting.
        if supplied is not None and supplied!=wanted:raise ValueError('judge_binding_conflict:'+key)
        value[key]=wanted
    changes=[]
    for dimension in value.get('dimensions',[]):
        if not isinstance(dimension,dict):raise ValueError('invalid_dimension')
        evidence=[];invalid=[]
        supplied=dimension.get('evidence',[])
        if not isinstance(supplied,list):raise ValueError('invalid_evidence_array')
        for item in supplied:
            if not isinstance(item,dict):invalid.append('invalid_evidence_item');continue
            if 'evidence_id' not in item:
                evidence.append(item);continue  # Original strict ref/SHA validator still runs.
            proof=index.get(item['evidence_id'])
            if proof is None:invalid.append('unknown_evidence_id');continue
            if any(k in item and item[k]!=proof.get(k) for k in ('ref','sha256','source_id','source_page')):
                invalid.append('conflicting_evidence_identity');continue
            slide=item.get('slide',proof.get('slide'))
            if type(slide) is not int or not 1<=slide<=slide_count:
                invalid.append('missing_or_invalid_slide');continue
            if 'slide' in proof and slide!=proof['slide']:
                invalid.append('evidence_slide_mismatch');continue
            mapped={k:proof[k] for k in ('ref','sha256','source_id','source_page') if k in proof}
            mapped.update(slide=slide,evidence_id=proof['evidence_id'],host_binding='frozen_evidence_id_v2')
            evidence.append(mapped)
        if supplied:dimension['model_original_evidence']=supplied
        dimension['evidence']=evidence
        if invalid:
            dimension['invalid_evidence_ids']=invalid
            # Do not discard a real defect or contradictory model unknown.
            dimension['model_reported_score_before_id_validation']=dimension.get('score')
            dimension.update(score=None,status='unknown',reason='Host: invalid evidence IDs: '+','.join(invalid))
            value.setdefault('critical_unknowns',[]).append('Invalid evidence binding for '+str(dimension.get('id')))
        if any(e.get('host_binding') for e in evidence):changes.append(dimension.get('id'))
    value['host_evidence_binding']={'version':2,'kind':'explicit_frozen_evidence_ids','dimensions_bound':changes,
                                   'adds_scientific_judgement':False}
    return value


def category_costs(receipts,*,generation_ids,review_ids):
    """Charge every attempt to one category; missing charges stay unknown."""
    generation_ids=set(generation_ids);review_ids=set(review_ids)
    if generation_ids&review_ids:raise ValueError('cost_categories_overlap')
    from decimal import Decimal
    result={key:{'requests':0,'known_proxy_usd':Decimal(0),'unknown_cost_requests':0} for key in ('generation','review')}
    seen=set()
    for row in receipts:
        tid=row.get('task_id');kind='generation' if tid in generation_ids else 'review' if tid in review_ids else None
        if kind is None or row.get('response_status') is None:continue
        identity=(tid,row['request_id'])
        if identity in seen:raise ValueError('duplicate_cost_receipt')
        seen.add(identity);part=result[kind];part['requests']+=1;cost=row.get('observed_peak_usd')
        if type(cost) not in (int,float) or not __import__('math').isfinite(cost) or cost<0:part['unknown_cost_requests']+=1
        else:part['known_proxy_usd']+=Decimal(str(cost))
    for part in result.values():part['known_proxy_usd']=str(part['known_proxy_usd'])
    return result


def validate_failed_delivery_review(result, *, artifact_id):
    """Validate a missing-delivery audit without inventing quality or pages.

    A model may put a textual limitation in ``unreviewed``. Preserve that text
    separately; numeric or page-like entries remain invalid. This does not
    turn a missing artifact into a scored deck or change any model score.
    """
    value=copy.deepcopy(result)
    if not isinstance(value,dict) or value.get('artifact_id')!=artifact_id:
        raise ValueError('failure_review_identity_mismatch')
    if type(value.get('task_completion_score')) not in (int,float) or value['task_completion_score']!=0:
        raise ValueError('missing_delivery_completion_must_be_zero')
    if value.get('deck_quality_score','absent') is not None:
        raise ValueError('missing_delivery_quality_must_be_unknown')
    names={'scientific_accuracy','task_fulfillment','narrative','figures_and_sources','visual_readability','usability'}
    dimensions=value.get('dimensions')
    if not isinstance(dimensions,list) or len(dimensions)!=6 or any(not isinstance(d,dict) for d in dimensions) or {d.get('id') for d in dimensions}!=names:
        raise ValueError('failure_review_requires_six_dimensions')
    for dimension in dimensions:
        expected=0 if dimension['id']=='task_fulfillment' else None
        score=dimension.get('score','absent')
        if (score!=expected or (expected==0 and type(score) not in (int,float)) or
            dimension.get('status')!=('failed' if expected==0 else 'unknown')):
            raise ValueError('unsupported_nonexistent_deck_quality')
        if not isinstance(dimension.get('reason'),str) or not dimension['reason'].strip():
            raise ValueError('failure_review_reason_missing')
    if not isinstance(value.get('failure_summary'),str) or not value['failure_summary'].strip():
        raise ValueError('failure_summary_missing')
    coverage=value.get('coverage')
    if not isinstance(coverage,dict) or set(coverage)!={'images_seen','text_seen','unreviewed'} or coverage['images_seen']!=[] or coverage['text_seen']!=[]:
        raise ValueError('failure_review_invented_deck_coverage')
    notes=coverage['unreviewed']
    if not isinstance(notes,list) or any(not isinstance(n,str) or not n.strip() or re.search(r'\d',n) for n in notes):
        raise ValueError('failure_review_invented_unreviewed_pages')
    if notes:
        value['model_original_coverage']=copy.deepcopy(coverage)
        value['unreviewed_delivery_limitations']=notes
        coverage['unreviewed']=[]
    return value
