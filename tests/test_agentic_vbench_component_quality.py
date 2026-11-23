import json

import pytest
from scenarios.agentic_vbench.component_quality import evaluate


def inputs(tmp_path):
    cfg={'clips':[{'source':'1','duration':1.25},{'source':'2','duration':2.5}]}
    manifest={'segments':[{'source':'1','output':[0,1.25],'source_range':[0,1.25]},
        {'source':'2','output':[1.25,3.75],'source_range':[0,2.5]}]}
    media={str(i)+'.mp4':{'duration_seconds':d,'streams':[{'codec_type':'video','duration':str(d)}]}
        for i,d in ((1,1.25),(2,2.5))}
    return cfg,manifest,media


def check(tmp_path,cfg,manifest,media):
    paths=[tmp_path/name for name in ('instance.json','solution.json','media.json')]
    for path,value in zip(paths,(cfg,manifest,media)):path.write_text(json.dumps(value))
    return evaluate(*paths)


def test_configured_manifest_pass_does_not_claim_storyboard_quality(tmp_path):
    value=check(tmp_path,*inputs(tmp_path))
    assert value['passed'] is True
    assert value['storyboard_quality']=='not_evaluated'
    assert value['segment_count']==2


@pytest.mark.parametrize('fault',['order','gap','truncated','unmeasured','nonfinite'])
def test_rejects_semantically_invalid_or_unmeasured_manifest(tmp_path,fault):
    cfg,m,media=inputs(tmp_path)
    if fault=='order':m['segments'][0]['source']='2'
    if fault=='gap':m['segments'][1]['output'][0]=1.3
    if fault=='truncated':m['segments'][1]['source_range'][1]=2
    if fault=='unmeasured':cfg['clips'][0]['duration']=1.5
    if fault=='nonfinite':m['segments'][0]['output'][1]=float('nan')
    assert check(tmp_path,cfg,m,media)['passed'] is False
