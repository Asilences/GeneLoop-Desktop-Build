"""Independent evaluator diagnostics, synthetic sources and manual expected facts."""
import json
import zipfile
from scenarios.paper_proofreading.frontier.oracle import audit,compare,evaluate,uncomment


def project(path,files):
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('geneloop-project.json',json.dumps({'root':'main.tex'}))
        for name,text in files.items():z.writestr(name,text)
    return path


def test_multifile_cross_relations_select_active_bibliography_only(tmp_path):
    p=project(tmp_path/'a.zip',{'main.tex':r'\input{body}\bibliography{refs}',
        'body.tex':r'\citep[see]{A,Missing} % \cite{Ignored}'+'\n'+r'\cite{B}',
        'refs.bib':'@article{A,title={One}}\n@book{B,title={Two}}\n@book{B,title={Duplicate}}\n@book{U,title={Unused}}',
        'inactive.bib':'@book{A,title={Unrelated duplicate}}'})
    r=audit(p)
    assert r['missing']==['Missing'] and r['duplicates']==['B'] and r['unused']==['U']
    assert {i['path'] for i in r['files']}=={'main.tex','body.tex','refs.bib'}
    assert evaluate('C',[p],r)['passed']
    r['missing']=[]
    assert not evaluate('C',[p],r)['passed']


def test_version_relation_propagates_changed_bib_key_to_citing_file_and_ancestor(tmp_path):
    files={'main.tex':r'\input{body}\input{unaffected}\bibliography{refs}',
           'body.tex':r'\cite{A}', 'unaffected.tex':r'\cite{B}',
           'refs.bib':'@article{A,title={One}}\n@article{B,title={Two}}'}
    before=project(tmp_path/'before.zip',files)
    changed={**files,'refs.bib':'@article{B,title={Two}}'}
    after=project(tmp_path/'after.zip',changed)
    r=compare(before,after)
    assert r['introduced_missing']==['A'] and r['resolved_missing']==[]
    assert r['changed_entry_keys']==['A']
    assert r['affected_tex_files']==['body.tex','main.tex']
    assert 'unaffected.tex' not in r['affected_tex_files']
    assert r['after_has_errors'] is True and r['before_files_digest']!=r['after_files_digest']


def test_literal_scope_handles_comments_optional_arguments_and_include_cycles(tmp_path):
    assert uncomment('x\\% kept % removed\n')=='x\\% kept \n'
    p=project(tmp_path/'cycle.zip',{'main.tex':r'\input{body}\bibliography{refs}',
        'body.tex':r'\input{main}\citep[x][y]{A}\newcommand{\cc}[1]{\cite{#1}}',
        'refs.bib':'@article{A,title={One}}'})
    r=audit(p)
    assert r['missing']==[] and r['unresolved']==[]
    assert r['citations']==[{'path':'body.tex','key':'A'}]
