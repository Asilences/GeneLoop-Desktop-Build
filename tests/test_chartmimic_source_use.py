"""Future source use preserves the original held-out task and paired evidence."""
import json
from pathlib import Path

import pytest

from scenarios.chartmimic.source_use import reference,retired_source


def closed_pair(tmp_path):
    arms={}
    for name,mode in [('reuse','successor_reuse'),('baseline','baseline')]:
        trial=tmp_path/name;trial.mkdir()
        (trial/'effective.json').write_text(json.dumps({'task_id':'line_14','role':'successor','mode':mode}))
        (trial/'result.json').write_text(json.dumps({'status':'completed'}))
        arms[name]={'effective':reference(trial/'effective.json'),'result':reference(trial/'result.json')}
    report=tmp_path/'assessment.json'
    report.write_text(json.dumps({'task_id':'line_14','generation_id':'old',
        'evaluation_complete':True,'training_source_eligible':True,'arms':arms}))
    return tmp_path/'reuse',report


def test_retirement_changes_only_declared_future_use(tmp_path):
    trial,report=closed_pair(tmp_path)
    before={name:(trial/name).read_bytes() for name in ('effective.json','result.json')}
    decision=retired_source(trial,'new-generation',report)
    assert decision['original_role']=='successor'
    assert decision['next_generation']=='new-generation'
    assert decision['retirement_evidence']==reference(report)
    assert before=={name:(trial/name).read_bytes() for name in before}


def test_baseline_and_unevaluated_sources_cannot_be_promoted(tmp_path):
    trial,report=closed_pair(tmp_path)
    with pytest.raises(ValueError,match='reuse_side_source'):
        retired_source(tmp_path/'baseline','new-generation',report)
    data=json.loads(report.read_text());data['evaluation_complete']=False
    report.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='closed_evaluated_source'):
        retired_source(trial,'new-generation',report)


def test_changed_or_running_counterpart_does_not_close_the_pair(tmp_path):
    trial,report=closed_pair(tmp_path)
    counterpart=tmp_path/'baseline/result.json';counterpart.write_text(json.dumps({'status':'running'}))
    with pytest.raises(ValueError,match='evidence_changed'):
        retired_source(trial,'new-generation',report)
    data=json.loads(report.read_text());data['arms']['baseline']['result']=reference(counterpart)
    report.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='pair_not_closed'):
        retired_source(trial,'new-generation',report)
