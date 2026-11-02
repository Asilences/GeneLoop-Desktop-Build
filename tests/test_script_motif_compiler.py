"""Deterministic admission diagnostics; not paid task quality evidence."""
import pytest
from src.adapters.script_motif_compiler import compile_script,extract,file_contract

def test_parameterizes_current_file_names(tmp_path):
    a=tmp_path/'first.json';b=tmp_path/'renamed.json'
    a.write_text('{"items":[1,2]}');b.write_text('{"items":[9]}')
    source='import json\nx=json.load(open("%s"))\nprint(len(x["items"]))'
    first=compile_script(source%'first.json',{'first.json':file_contract(a)})
    second=compile_script(source%'renamed.json',{'renamed.json':file_contract(b)})
    assert first['id']==second['id']
    assert 'first.json' not in first['template']
    assert '__MOTIF_INPUT_0__' in first['template']

@pytest.mark.parametrize('source',[
    'import subprocess\nsubprocess.run(["true"])',
    'open("x.json","w").write("bad")',
    'from pathlib import Path\nPath("x.json").unlink()',
    'import zipfile\nzipfile.ZipFile("x.json").extractall("/tmp")',
    'getattr(open,"__call__")("x.json")',
    '_sm_expected.clear()',
    'print(open("/etc/passwd").read()); print(open("x.json").read())',
])
def test_rejects_effectful_or_unbound_programs(source):
    with pytest.raises(ValueError):compile_script(source,{'x.json':{'suffix':'.json','format':'json'}})

def test_does_not_strip_unmodeled_shell_steps():
    for command in ['python3 -c "print(1)" | head','echo before && python3 -c "print(1)"',"python3 - <<'PY'\nprint(1)\nPY\nrm x"]:
        with pytest.raises(ValueError):extract(command)
    assert extract("cd /work && python3 - <<'PY'\nprint(1)\nPY")==('/work','print(1)')

def test_readonly_regex_script_does_not_require_json_ir():
    p=compile_script('import re\ns=open("references.bib").read()\nprint(len(re.findall(r"@article",s)))',{'references.bib':{'suffix':'.bib','format':'text'}})
    assert p['language']=='python'


def test_zip_directory_separator_is_data_but_filesystem_root_stays_unbound():
    inputs={'project.zip':{'suffix':'.zip','format':'zip'}}
    source="import zipfile\nz=zipfile.ZipFile('project.zip')\nprint([p for p in z.namelist() if not p.endswith('/')])"
    assert compile_script(source,inputs)['language']=='python'
    assert compile_script("import posixpath\nprint(posixpath.normpath('a/../b')); print(open('project.zip','rb').read())",inputs)['language']=='python'
    normalization="\nname='a/b'\nbase='a'\nprint('/'.join(name.split('/')))\nprint(base+'/'+name)\nprint('/' in name)\nprint(name.count('/'))"
    assert compile_script(source+normalization,inputs)['language']=='python'
    for extra in ["print(open('/').read())", "print(open('/etc/passwd').read())", "root='/'", "print(open('/'+'etc/passwd').read())"]:
        with pytest.raises(ValueError,match='unbound_path_literal'):
            compile_script(source+'\n'+extra,inputs)


def test_regex_compile_is_distinct_from_python_compile_and_rebinding():
    inputs={'references.bib':{'suffix':'.bib','format':'text'}}
    for alias in ('re','rx'):
        source=f'import re as {alias}\ns=open("references.bib").read()\nprint({alias}.compile(r"@article").findall(s))'
        assert compile_script(source,inputs)['language']=='python'
    for source in ['compile("print(1)","x","exec")',
                   'import json\njson.compile("bad")',
                   'import re\nre=other\nre.compile("bad")',
                   'import re\ndef f(re):\n return re.compile("bad")',
                   'import re\nimport json as re\nre.compile("bad")']:
        with pytest.raises(ValueError):compile_script(source,inputs)


def test_new_saved_source_is_bound_to_current_command_not_old_file(tmp_path):
    (tmp_path/'code').mkdir()
    command="cat > read.py <<'PY'\nprint(open('inputs/current.bib').read())\nPY\npython3 read.py"
    assert extract(command,tmp_path)[1]=="print(open('inputs/current.bib').read())"
    for tail in [' | head','; rm x',' && echo extra']:
        with pytest.raises(ValueError):extract(command+tail,tmp_path)


def test_real_heredoc_forms_keep_body_and_reject_shell_expansion_or_tail():
    for prefix in ["python3 << 'EOF'","python3 - << 'EOF'",'python <<EOF']:
        assert extract(prefix+'\nprint(1)\nEOF')==('/work','print(1)')
    for command in ["python3 <<EOF\nprint('$HOME')\nEOF", "python3 << 'EOF\"\nprint(1)\nEOF", "python3 << 'EOF'\nprint(1)\nEOF\nrm data"]:
        with pytest.raises(ValueError):extract(command)


def test_native_checksum_prefix_requires_same_fixed_input_and_complete_heredoc(tmp_path):
    (tmp_path/'inputs').mkdir()
    (tmp_path/'inputs/source.bib').write_text('@article{A,title={Example}}',encoding='utf-8')
    source="import re\np='inputs/source.bib'\ns=open(p).read()\nprint(len(re.findall(r'@article',s)))"
    command="cd /work && sha256sum inputs/source.bib && python3 - <<'EOF'\n"+source+'\nEOF'
    assert extract(command,tmp_path)==('/work',source)
    for prefix in ['sha256sum -c inputs/source.bib',
                   'sha256sum inputs/source.bib inputs/source.bib',
                   'sha256sum $(echo inputs/source.bib)',
                   'sha256sum inputs/source.bib > checksum.txt',
                   'sha256sum /etc/passwd',
                   'echo ok', 'touch inputs/source.bib']:
        with pytest.raises(ValueError):
            extract(prefix+" && python3 - <<'EOF'\n"+source+'\nEOF',tmp_path)
    with pytest.raises(ValueError):extract(command+'\nrm inputs/source.bib',tmp_path)
    with pytest.raises(ValueError):extract(command.replace("p='inputs/source.bib'","p='inputs/other.bib'"),tmp_path)
    with pytest.raises(ValueError):extract(command)
    with pytest.raises(ValueError):extract("sha256sum inputs/source.bib && python3 -c \"print(1)\"",tmp_path)


def test_current_command_temp_program_is_witnessed_without_reading_host_tmp(tmp_path):
    (tmp_path/'inputs').mkdir()
    (tmp_path/'inputs/source.bib').write_text('@article{A,title={Example}}',encoding='utf-8')
    source="import json\ns=open('inputs/source.bib').read()\nprint(json.dumps({'size':len(s)}))"
    command="cd /work && sha256sum inputs/source.bib && cat > /tmp/count.py <<'EOF'\n"+source+'\nEOF\npython3 /tmp/count.py'
    assert extract(command,tmp_path)[1]==source
    for changed in [command.replace('/tmp/count.py','/etc/count.py'),
                    command.replace('python3 /tmp/count.py','python3 /tmp/other.py'),
                    command+' && rm inputs/source.bib',
                    command.replace("<<'EOF'","<<EOF").replace("'size'","'$HOME'"),
                    command.replace("<<'EOF'",'<<\'EOF"')]:
        with pytest.raises(ValueError):extract(changed,tmp_path)
    with pytest.raises(ValueError):extract('python3 /tmp/count.py',tmp_path)
