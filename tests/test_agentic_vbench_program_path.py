import hashlib
from pathlib import Path

from scenarios.agentic_vbench.learning import project_program_operand


def boundary(tmp_path):
    source=tmp_path/'code/program.py';source.parent.mkdir();source.write_text('print("actual program")\n')
    return {'workspace':str(tmp_path),'workdir':'/workspace/program','before':{'files':{
        'code/program.py':{'path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}}}}


def test_maps_only_verified_source_operand_and_preserves_shell_and_arguments(tmp_path):
    state=boundary(tmp_path)
    command='python3 /workspace/program/program.py /workspace/program/input.json outputs/fresh && false'
    projected,evidence=project_program_operand(command,state)
    assert projected=='python3 /work/program.py /workspace/program/input.json outputs/fresh && false'
    assert evidence['original_command']==command
    assert evidence['source']==state['before']['files']['code/program.py']


def test_does_not_project_unknown_changed_or_traversing_source(tmp_path):
    state=boundary(tmp_path)
    for command in ('python3 /elsewhere/program.py x y','python3 /workspace/program/../program.py x y',
                    'python3 /workspace/program/unknown.py x y','python3 program.py x y'):
        assert project_program_operand(command,state)==(command,None)
    (Path(state['workspace'])/'code/program.py').write_text('changed\n')
    command='python3 /workspace/program/program.py x y'
    assert project_program_operand(command,state)==(command,None)
