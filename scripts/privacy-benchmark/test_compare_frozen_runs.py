"""Scoring failures must not become successful masks or ordinary misses."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from compare_frozen_runs import detector_availability, main


class AvailabilityTests(unittest.TestCase):
    def test_partial_masks_are_distinct_from_full_masks(self):
        gold=[{'start':0,'end':2,'label':'PERSON'},
              {'start':3,'end':5,'label':'PERSON'},
              {'start':6,'end':8,'label':'PERSON'}]
        row={'gold':gold,'core':{'error_type':None,
            'pred':[{'start':0,'end':2},{'start':3,'end':4}],
            'chars':{'gold_entities':3,'fully_covered_entities':1},
            'context_chunks':1,'retained_context_chunks':1}}
        result=detector_availability({0:row},'core')
        self.assertEqual(result['observation_statuses'],{'available':1})
        self.assertEqual(result['by_gold_type']['PERSON'],{
            'gold_entities':3,'fully_covered':1,'partially_covered':1,'not_covered':1})

    def test_errors_unknown_and_absent_predictions_do_not_enter_coverage(self):
        rows={0:{'gold':[], 'core':{'error_type':'AssertionError'}},
              1:{'evaluation_status':'evaluation_timeout'},
              2:{'gold':[]}}
        result=detector_availability(rows,'core')
        self.assertEqual(result['by_gold_type'],{})
        self.assertEqual(result['character_and_context_counts'],{})
        self.assertEqual(result['observation_statuses'],{
            'processing_error:AssertionError':1,'evaluation_timeout':1,'not_measured':1})

    def test_full_report_compares_the_same_admitted_types_and_successful_cores(self):
        gold=[{'start':0,'end':2,'label':'PERSON'}]
        def observation(identity):
            prediction={'error_type':None,'pred':gold,
                'chars':{'non_pii_chars':3,'masked_non_pii_chars':0},
                'context_chunks':1,'retained_context_chunks':1}
            return {'id':identity,'gold':gold,'chars':5,'core':prediction,'native':prediction,
                'module':{'accepted':True,'gold_entities':1,'literal_residual_entities':1,
                    'by_gold_type':{'PERSON':{'gold_entities':1,'literal_residual_entities':1}}}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('before-pii','after-pii','before-cred','after-cred'):(root/name).mkdir()
            for dataset in ('zh_formal','zh_chat','en_test'):
                before=[observation(i) for i in range(3)]
                after=[observation(0),observation(1),
                    {'id':2,'gold':gold,'evaluation_status':'evaluation_timeout'}]
                after[0]['module']['literal_residual_entities']=0
                after[0]['module']['by_gold_type']['PERSON']['literal_residual_entities']=0
                after[1]['core']={**after[1]['core'],'error_type':'AssertionError','pred':[]}
                after[1]['module']={'accepted':False,'decision_reason':'credential_detected'}
                for name,rows in [('before-pii',before),('after-pii',after)]:
                    (root/name/(dataset+'-records.jsonl')).write_text(
                        '\n'.join(map(json.dumps,rows)),encoding='utf-8')
            # The real comparison checks the frozen complete credential corpus.
            credentials=[{'file':str(i),'truth':'negative','gitleaks_flagged':False,
                'status':'accepted','accepted':True,'extractable_positive_rows':0,
                'literal_residual_rows':0} for i in range(11030)]
            for name in ('before-cred','after-cred'):
                (root/name/'module-file-records-private.jsonl').write_text(
                    '\n'.join(map(json.dumps,credentials)),encoding='utf-8')
            args=['compare','--previous-pii',str(root/'before-pii'),'--current-pii',str(root/'after-pii'),
                '--previous-credentials',str(root/'before-cred'),'--current-credentials',str(root/'after-cred'),
                '--output',str(root/'summary.json')]
            with patch('sys.argv',args):main()
            result=json.loads((root/'summary.json').read_text(encoding='utf-8'))
            for row in result['pii'].values():
                self.assertEqual(row['completed_comparison_rows'],2)
                self.assertEqual(row['by_gold_type']['PERSON']['lost'],1)
                self.assertEqual(row['same_successful_core_cohort']['rows'],1)
                self.assertEqual(row['same_successful_core_cohort']['by_gold_type']['PERSON']['lost'],0)
                self.assertEqual(row['unknown_gold_entities_by_type'],{'PERSON':1})
                self.assertEqual(row['same_admitted_per_type_availability'],{'available_documents':1})
                self.assertEqual(row['same_admitted_cohort_by_gold_type'],{'PERSON':{
                    'gold_entities':1,'previous_literal_residual_entities':1,'current_literal_residual_entities':0}})


if __name__=='__main__':
    unittest.main()
