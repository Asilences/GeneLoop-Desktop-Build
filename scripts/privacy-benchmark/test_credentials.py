import os
import sys
import unittest

import run_credentials as credentials


class CredentialAdapterTests(unittest.TestCase):
    def test_uncertain_and_mixed_labels_do_not_become_false_negatives(self):
        self.assertEqual(credentials.truth_status([{'GroundTruth': 'X'}]), 'uncertain')
        self.assertEqual(credentials.truth_status([{'GroundTruth': 'F'}, {'GroundTruth': 'X'}]), 'uncertain')
        self.assertEqual(credentials.truth_status([{'GroundTruth': 'F'}, {'GroundTruth': 'T'}]), 'positive')
        self.assertEqual(credentials.truth_status([{'GroundTruth': 'F'}]), 'negative')

    def test_unicode_and_multiline_credential_values(self):
        text = '甲 abc\nstartAAA\nBBBend'
        rows = [{'GroundTruth': 'T', 'LineStart': 1, 'LineEnd': 1, 'ValueStart': 2, 'ValueEnd': 5},
                {'GroundTruth': 'T', 'LineStart': 2, 'LineEnd': 3, 'ValueStart': 5, 'ValueEnd': 3}]
        self.assertEqual(credentials.extract_positive_values(text, rows), (['abc', 'AAA\nBBB'], 0))

    @unittest.skipUnless(os.environ.get('CRED_DATA_CODE_ROOT'), 'Requires pinned CredData evaluation source')
    def test_upstream_result_formulas_preserve_unlabeled_exclusion(self):
        sys.path.insert(0, os.environ['CRED_DATA_CODE_ROOT'])
        rows = [{'truth': 'positive', 'flagged': True}, {'truth': 'positive', 'flagged': False},
                {'truth': 'negative', 'flagged': True}, {'truth': 'uncertain', 'flagged': True}]
        result = credentials.matrix(rows)
        self.assertEqual((result['true_positive'], result['false_positive'], result['false_negative'], result['uncertain_excluded']), (1, 1, 1, 1))
        self.assertEqual(result['precision'], .5)
        self.assertEqual(result['recall'], .5)


if __name__ == '__main__':
    unittest.main()
