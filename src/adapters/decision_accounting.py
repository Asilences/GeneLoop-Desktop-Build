"""Link typed calls to the original account pool; unknown currencies stay separate."""
from pathlib import Path
import os,re,json,stat

def account(context_file,event):
    project=Path(__file__).resolve().parents[2];file=Path(context_file).absolute()
    if not file.is_relative_to(project/'.local') or file.is_symlink() or file.stat().st_mode & 0o077:
        raise ValueError('private host meter context required')
    context=json.loads(file.read_text());home=Path(context['private_root']);root=Path(context['state_root'])
    if (context.get('format')!='geneloop-decision-account-v1' or not home.is_relative_to(project/'.local')
            or root.parent!=home/'rsi' or not (root/'pool.json').is_file()
            or any(p.is_symlink() for p in (file,*file.parents,root,*root.parents))):
        raise ValueError('original account root required')
    if event.get('owner')!=context['owner'] or not re.fullmatch(r'[a-f0-9-]{36}',event.get('call_id','')):
        raise ValueError('decision owner changed')
    record=Path(event['record_directory']).absolute()
    if not record.is_relative_to(project/'.local') or record.is_symlink():raise ValueError('private decision record required')
    cfg=json.loads(Path(context['original_config']).read_text())
    if cfg['state_root']!=str(root) or any(cfg.get(k) is not None for k in ('series_cap_usd','learning_cap_usd')) or cfg['limits']['budget_usd'] is not None:
        raise ValueError('unpriced decision requires the existing unlimited grant; finite grants need verified pricing')
    os.environ['HARLESS_MANAGEMENT_PRIVATE_ROOT']=str(home)
    from .continuous_rsi import writer_lock,STATE_HOME
    from src.motif_core.reuse.experience_registry import read,sha,durable
    with writer_lock(STATE_HOME,'series'):
        pool=read(root/'pool.json');calls=pool.setdefault('decision_calls',{});key=event['call_id'];previous=calls.get(key)
        row={k:event.get(k) for k in ('format','call_id','scene','contract','owner','task_id','parent_call_id','provider','packet_sha256','record_directory','status','started_at','upstream_attempts','elapsed_ms','http_status','reported_usage','provider_reported_cost','provider_cost_currency','reference_cost_usd','invoice_verified','code','charge_unknown')}
        if row['status']=='cost_reconciled':
            if previous is None or previous['status']!='failed' or previous['provider']!='deepseek':raise ValueError('original failed decision required')
            for k in ('owner','task_id','parent_call_id','scene','contract','provider','packet_sha256','record_directory'):
                if previous[k]!=row[k]:raise ValueError('original reconciliation binding changed')
            raw=record/'transport-response.txt';response=read(raw);usage=response.get('usage',{})
            p,c,t=usage.get('prompt_tokens'),usage.get('completion_tokens'),usage.get('total_tokens')
            if any(type(v)is not int or v<0 for v in (p,c,t)) or p+c!=t:raise ValueError('unreconciled original usage')
            cached=usage.get('prompt_tokens_details',{}).get('cached_tokens',0)
            if type(cached)is not int or not 0<=cached<=p:raise ValueError('cache counter changed')
            proof={'format':'geneloop-decision-cost-reconciliation-v1','call_id':key,'original_failed_event_sha256':sha(root/'decision-events'/key/'failed.json'),
             'response_sha256':sha(raw),'reported_usage':usage,'reference_cost_usd':((p-cached)*.30+cached*.006+c*1.20)/1e6,
             'invoice_verified':False,'semantic_result_remains_failed':True}
            target=root/'decision-events'/key/'cost_reconciled.json'
            if target.exists():
                if read(target)!=proof:raise ValueError('original reconciliation changed')
            else:durable(target,proof,exclusive=True)
            pool.setdefault('decision_reconciliations',{})[key]=proof;durable(root/'pool.json',pool)
            return {'linked':True,'reference_cost_usd':proof['reference_cost_usd'],'semantic_result_remains_failed':True}
        if row['status']=='started':
            if previous is not None:
                if previous!=row:raise ValueError('original decision already exists; never cold restart')
                return {'linked':True,'duplicate':True}
        elif previous is None or previous['status']!='started':
            if previous==row:return {'linked':True,'duplicate':True}
            raise ValueError('original decision enrollment missing or already sealed')
        else:
            for k in ('owner','task_id','parent_call_id','scene','contract','provider','packet_sha256','record_directory'):
                if previous[k]!=row[k]:raise ValueError('original decision binding changed')
        # Keep original runs and reservations byte-equivalent; do not insert unknown
        # currencies as zero-dollar completions into the existing USD run meter.
        eventfile=root/'decision-events'/key/(row['status']+'.json')
        if eventfile.exists():
            if read(eventfile)!=row:raise ValueError('decision event changed')
        else:durable(eventfile,row,exclusive=True)
        calls[key]=row;durable(root/'pool.json',pool)
    return {'linked':True,'status':row['status'],'original_pool':str(root/'pool.json')}
