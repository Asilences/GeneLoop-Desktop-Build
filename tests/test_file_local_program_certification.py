"""A reusable local program need not replace the whole task."""
from src.adapters.continuous_motif_learning import candidate_program_instruction,material_reading_instruction


def test_actual_candidate_certification_accepts_partial_workflow_composition():
    text=candidate_program_instruction({'source':'current parameterized program'},'candidate_certification')
    assert '不必独自完成全部目标' in text
    assert '实际调用候选' in text and '确实不适用或失败则如实报告' in text
    assert '只传 script_id 和 parameters' in text and 'profile_id' not in text


def test_no_candidate_exercise_instruction_enters_ordinary_or_native_reference():
    for role in ['ordinary','native_certification','holdout']:
        assert candidate_program_instruction({'source':'program'},role)==''
    assert candidate_program_instruction({'nodes':[]},'candidate_certification')==''


def test_method_specific_frozen_reading_requirements_are_visible_before_certification():
    spec={'quality':{'delivery_contract':{'require_reads':[{'path':'new.txt','mode':'text'},{'path':'other.txt'}]}}}
    text=material_reading_instruction(spec)
    assert 'new.txt' in text and 'other.txt' not in text
    assert 'TXT/CSV/Word' in text and 'next_request_id=null' in text
    assert material_reading_instruction({})==''
