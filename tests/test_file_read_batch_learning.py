"""Free inference diagnostics. Synthetic rows cannot certify or activate a program."""
import copy
from src.adapters.continuous_motif_learning import repeated_read_scripts

TOOL='mcp__file_management__search_index'

def frame(rows):
    return {'rows':rows,'tools':{TOOL:{'schema':{'type':'object','properties':{'query':{'type':'string'}},'required':['query']},'contract':{'effect':'read'}}},
        'spec':{'objective':'Search current sources'},'scope':{'execution_version':'current'},
        'record':{'selected':[{'entry_id':'parent'}]},'fingerprint':'ordinary-one'}

def row(query,seq):
    return {'name':TOOL,'call_id':'call-'+str(seq),'message_seq':seq,'args':{'query':query},'out':{'query':query,'matches':[]}}

def test_compile_observed_independent_reads_to_typed_parameter_loop():
    f=frame([row('alpha',1),row('beta',2),row('gamma',3)])
    candidates=repeated_read_scripts([f]);assert len(candidates)==1
    c=candidates[0]['compiled']
    assert c['example_parameters']=={'calls':[{'query':'alpha'},{'query':'beta'},{'query':'gamma'}]}
    assert c['parameters_schema']['properties']['calls']['items']==f['tools'][TOOL]['schema']
    assert 'for(const args of p.calls)' in c['source']
    assert 'alpha' not in c['source'] and 'gamma' not in c['source']
    assert c['source_kind']=='compiled_tool_trace' and c['parent_policy_digests']==['parent']
    assert c['witnessed_native_calls']==['call-1','call-2','call-3']
    # A different cardinality/query set still compiles the same parameterized program.
    other=repeated_read_scripts([frame([row('new',4),row('another',5)])])[0]
    assert other['key']==candidates[0]['key']

def test_generated_calls_writes_and_intervening_operations_are_not_independent_batch_evidence():
    for kind in ('generated','write','barrier'):
        f=frame([row('alpha',1),row('beta',2)])
        if kind=='generated':f['rows'][1]['generated']=True
        elif kind=='write':f['tools'][TOOL]['contract']['effect']='write'
        else:f['rows'].insert(1,{'name':'another_tool','message_seq':2,'args':{},'out':{'status':'ok'}})
        assert repeated_read_scripts([f])==[]

def test_output_dependent_cursor_and_redundant_same_read_are_not_compiled_as_independent_inputs():
    f=frame([row('alpha',1),row('beta',2)])
    f['rows'][0]['out']['next_request_id']='beta'
    assert repeated_read_scripts([f])==[]
    assert repeated_read_scripts([frame([row('alpha',1),row('alpha',2)])])==[]

def test_only_verified_native_decisions_qualify_and_original_rows_remain_unchanged():
    f=frame([row('alpha',1),row('beta',2)]);before=copy.deepcopy(f)
    assert repeated_read_scripts([f]) and f==before
    f['rows'][1]['message_seq']=None
    assert repeated_read_scripts([f])==[]


def test_semantic_query_selection_stays_explicit_parameters_while_the_tool_remains_readonly():
    f=frame([row('new query',1),row('another query',2)])
    f['tools'][TOOL]['contract']['effect']='semantic'
    c=repeated_read_scripts([f])[0]['compiled']
    assert c['example_parameters']['calls']==[{'query':'new query'},{'query':'another query'}]
    assert 'new query' not in c['source']
    f['tools'][TOOL]['contract']['effect']='write'
    assert repeated_read_scripts([f])==[]
