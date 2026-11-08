from copy import deepcopy

from src.adapters.ppt_workflow_learning import discover_workflows
from src.adapters.ppt_write_learning import page_runs


CONTRACTS = {
    'page': {'read_only': False, 'page_write': {'resource_argument': 'project', 'identity_argument': 'page',
        'revision_argument': 'expected_page_sha256', 'version_output': ['sha256']}},
    'deliver': {'read_only': False, 'resource_argument': 'project', 'observed_completion': {
        'success': ['mechanical_status'], 'success_value': 'passed', 'empty_findings': ['findings'], 'collection': ['review_pages']}},
}


def sample(identity, mode='new', count=2):
    project='/work/projects/'+identity
    rows=[]
    for n in range(count):
        args={'project': project, 'page': str(n)+'.svg', 'content': {'title': identity+' private scientific text'}}
        if mode=='revision':args['expected_page_sha256']='a'*64
        rows.append({'name': 'page', 'call_id': identity+'-page-'+str(n), 'arguments': args, 'error': False,
                     'call_sequence':2*n,'result_sequence':2*n+1,'value':{'sha256':'b'*64},'content':[]})
    rows.append({'name':'deliver','call_id':identity+'-delivery','arguments':{'project':project},'error':False,
                 'call_sequence':2*count,'result_sequence':2*count+1,
                 'value':{'mechanical_status':'passed','findings':[],'review_pages':[{'path':'preview.png'}]},'content':[]})
    return {'task_id':identity,'decision_id':identity,'source_signature':'source-'+identity,'question_sha256':'question-'+identity,
            'events_sha256':'events-'+identity,'records':rows,'schemas':{'page':{'type':'object'},'deliver':{'type':'object'}}}


def test_writing_and_revision_are_observed_independent_parameterized_programs():
    for mode in ['new','revision']:
        library=discover_workflows([sample('a',mode),sample('b',mode,3)],[sample('c',mode)],CONTRACTS,'env')
        program=library['programs'][0]
        assert program['status']=='certified'
        assert program['ir']['mode']==mode
        assert program['ir']['writer']['tool']=='page'
        assert program['ir']['delivery']['tool']=='deliver'
        assert program['certification']['independent_replay_decisions']==1
        assert 'private scientific text' not in str(program['ir']) and '/work/' not in str(program['ir'])
        assert program['provenance'][1]['observed_items']==3


def test_unknown_operations_parallel_dependencies_and_real_failure_are_boundaries():
    for mutate in [lambda t:t['records'].insert(1,{'name':'unknown','error':False}),
                   lambda t:t['records'][1].update(call_sequence=0),
                   lambda t:t['records'][-1]['value']['findings'].append({'rule':'overflow'}),
                   lambda t:t['records'][0].update(error=True)]:
        t=sample('a');mutate(t)
        runs=list(page_runs(t,CONTRACTS))
        assert not any(witness['observed_items']==2 for _,witness in runs)


def test_revisions_cannot_be_certified_by_new_writes_or_the_same_source():
    assert not discover_workflows([sample('a'),sample('b')],[sample('c','revision')],CONTRACTS,'env')['programs'][0]['status']=='certified'
    a,b=sample('a'),sample('b');b['source_signature']=a['source_signature']
    assert not discover_workflows([a,b],[sample('c')],CONTRACTS,'env')['programs']
    t=sample('a');t['records'][-1]['arguments']['project']='/another/project'
    assert not list(page_runs(t,CONTRACTS))


def test_changing_the_observed_writer_changes_the_learned_program():
    other=deepcopy(CONTRACTS);other['different']=other.pop('page')
    training=[sample('a'),sample('b')];heldout=[sample('c')]
    for t in training+heldout:
        t['schemas']['different']=t['schemas'].pop('page')
        for row in t['records']:
            if row['name']=='page':row['name']='different'
    p=discover_workflows(training,heldout,other,'env')['programs'][0]
    assert p['ir']['writer']['tool']=='different'


def test_initial_and_revision_records_from_one_document_never_count_as_two_sources():
    a,b,c=sample('a'),sample('b'),sample('c')
    a['source_family']=b['source_family']='same-original-document'
    assert not discover_workflows([a,b],[c],CONTRACTS,'env')['programs']
    b['source_family']='other-document';c['source_family']='same-original-document'
    assert discover_workflows([a,b],[c],CONTRACTS,'env')['programs'][0]['status']=='candidate'


def test_native_object_or_file_payload_choices_do_not_hide_observed_writes():
    contracts=deepcopy(CONTRACTS)
    contracts['page']['page_write']['payload_choice_arguments']=['content','parameters_file']
    traces=[sample('a'),sample('b'),sample('c')]
    schema={'type':'object','properties':{key:{} for key in ['project','page','content','parameters_file']},'required':['project','page']}
    for index,trace in enumerate(traces):
        trace['schemas']['page']=schema
        if index:
            for record in trace['records'][:-1]:
                record['arguments'].pop('content')
                record['arguments']['parameters_file']='/work/parameters.json'
    program=discover_workflows(traces[:2],traces[2:],contracts,'env')['programs'][0]
    assert program['status']=='certified'
    assert program['ir']['writer']['payload_choice_arguments']==['content','parameters_file']
    assert '/work/parameters.json' not in str(program['ir'])
    traces[2]['records'][0]['arguments']['content']={}
    assert not any(w['observed_items']==2 for _,w in page_runs(traces[2],contracts))


def test_only_explicit_review_findings_with_actual_complete_previews_are_learnable():
    contracts=deepcopy(CONTRACTS)
    contracts['deliver']['observed_completion']['allowed_finding_severities']=['review']
    contracts['image']={'read_only':True,'image_output_required':True}
    t=sample('a');delivery=t['records'][-1]
    delivery['value']['findings']=[{'rule':'rendered_text_requires_review','severity':'review'}]
    assert not list(page_runs(t,contracts))
    delivery['value']['review_pages'][0]['sha256']='c'*64
    t['schemas']['image']={'type':'object'}
    t['records'].append({'name':'image','call_id':'preview','arguments':{'file_path':'preview.png'},'error':False,
        'content':[{'type':'image','attachment':{'attachmentId':'sha256:'+'c'*64}}],
        'call_sequence':6,'result_sequence':7,'value':None})
    assert list(page_runs(t,contracts))[0][0]['preview']['tool']=='image'
    for severity in ['error',None,'unrecognized']:
        delivery['value']['findings'][0]['severity']=severity
        assert not list(page_runs(t,contracts))


def test_image_binding_is_learned_from_actual_artifact_reads_not_empty_review_list():
    from src.adapters.ppt_write_learning import observed_preview
    t=sample('a');d=t['records'][-1]
    d['value']['review_pages']=[]
    d['value']['artifacts']=[{'path':'deck.pptx','sha256':'d'*64},{'path':'page.png','sha256':'c'*64}]
    t['schemas']['image']={'type':'object'}
    reads=[{'name':'image','arguments':{'file_path':'page.png'},'error':False,
       'content':[{'type':'image','attachment':{'attachmentId':'sha256:'+'c'*64}}]}]
    contracts={**CONTRACTS,'image':{'read_only':True,'image_output_required':True}}
    preview=observed_preview(reads,d,t,contracts)
    assert preview['collection']==['artifacts'] and preview['path_suffix']=='.png'
    reads[0]['content'][0]['attachment']['attachmentId']='sha256:'+'a'*64
    assert observed_preview(reads,d,t,contracts) is None


def test_native_execution_case_uses_an_independent_source_and_real_recorded_revision():
    from src.adapters.ppt_workflow_certification import execution_case
    library=discover_workflows([sample('a'),sample('b')],[],CONTRACTS,'env')
    program=library['programs'][0];program['ir']['mode']='revision';program['ir']['writer']['tool']='create_ppt_page'
    t=sample('c')
    for row in t['records'][:-1]:
        row['name']='create_ppt_page';row['arguments']['parameters']=row['arguments'].pop('content');row['arguments']['notes']='original source note'
    from copy import deepcopy
    revision=deepcopy(t['records'][1]);revision.update(call_id='current-revision',call_sequence=10,result_sequence=11)
    revision['arguments']['expected_page_sha256']='b'*64;t['records'].append(revision)
    assert execution_case(program,t)['revision_call']=='current-revision'
    t['source_signature']='source-a'
    assert execution_case(program,t) is None


def test_split_precedes_family_witness_selection_so_common_revision_prompts_do_not_starve_learning():
    from src.adapters.ppt_workflow_certification import independent_training
    a,b,c=sample('a','revision'),sample('b','revision'),sample('c','revision')
    a['source_family']='family-a';b['source_family']='family-b';c['source_family']='family-c'
    revised=deepcopy(b);revised['question_sha256']=c['question_sha256'];revised['task_id']='early-sorting-revision'
    training=independent_training([a,revised,b,c],c)
    assert training==[a,b]
    p=discover_workflows(training,[],CONTRACTS,'env')['programs'][0]
    assert p['status']=='candidate' and len(p['provenance'])==2
    assert all(w['question_sha256']!=c['question_sha256'] for w in p['provenance'])
