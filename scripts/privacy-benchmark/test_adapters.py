"""Checks evaluation coordinate/scoring semantics with independent tiny fixtures."""
import json
from pathlib import Path
import unittest

import run_pii as bench


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bench.CONFIG = json.loads(Path(__file__).with_name('protocol-r1.json').read_text())

    def test_literal_span_conversion_keeps_whitespace_unicode_and_repetition(self):
        self.assertEqual(bench.exact_occurrences('甲 甲 😀甲', '甲'), [(0, 1), (2, 3), (5, 6)])
        self.assertEqual(bench.exact_occurrences(' A A', ' A'), [(0, 2), (2, 4)])
        self.assertEqual(bench.exact_occurrences('abc', ' abc'), [])

    def test_mature_scorer_perfect_missed_and_spurious(self):
        gold = [[{'start': 1, 'end': 4, 'label': 'PERSON'}]]
        score = bench.standard_scores(gold, gold)['overall']['strict']
        self.assertEqual((score['precision'], score['recall'], score['f1']), (1, 1, 1))
        score = bench.standard_scores(gold, [[]])['overall']['strict']
        self.assertEqual((score['missed'], score['recall']), (1, 0))
        score = bench.standard_scores([[]], gold)['overall']['strict']
        self.assertEqual((score['spurious'], score['precision']), (1, 0))

    def test_partial_credit_is_not_full_privacy_coverage(self):
        gold = [[{'start': 1, 'end': 4, 'label': 'PERSON'}]]
        pred = [[{'start': 2, 'end': 4, 'label': 'PERSON'}]]
        score = bench.standard_scores(gold, pred)['overall']
        self.assertEqual(score['strict']['recall'], 0)
        self.assertEqual(score['partial']['recall'], .5)
        chars = bench.character_metrics(' abc ', gold[0], pred[0])
        self.assertEqual(chars['fully_covered_entities'], 0)
        self.assertEqual(chars['covered_gold_chars'], 2)

    def test_semantic_proxy_excludes_gold_and_handles_adjacent_entities(self):
        spans = [{'start': 4, 'end': 6}, {'start': 6, 'end': 8}]
        self.assertEqual(bench.context_chunks('aaaaPIIDbbbb', spans, 4), ['aaaa', 'bbbb'])

    def test_official_operation_spans_use_original_unicode_coordinates(self):
        from presidio_analyzer import RecognizerResult
        from presidio_anonymizer import AnonymizerEngine
        bench.ANONYMIZER = AnonymizerEngine()
        bench.CAPTURE = []
        bench.CAPTURE_ENABLED = True
        bench.capture_operations(bench.ANONYMIZER)
        text = '😀 test@example.com 后续内容'
        bench.ANONYMIZER.anonymize(text=text, analyzer_results=[RecognizerResult('EMAIL_ADDRESS', 2, 18, .9)])
        result = bench.CAPTURE[-1][1]
        bench.CAPTURE_ENABLED = False
        self.assertEqual(result, [{'start': 2, 'end': 18, 'label': 'EMAIL_ADDRESS'}])

    def test_overlapping_types_are_observed_before_output_offsets_change(self):
        from presidio_analyzer import RecognizerResult
        from presidio_anonymizer import AnonymizerEngine
        bench.CAPTURE = []
        bench.CAPTURE_ENABLED = True
        engine = AnonymizerEngine()
        bench.capture_operations(engine)
        source = 'ABCDEFGHIJ KLMNOP'
        result = engine.anonymize(text=source, analyzer_results=[RecognizerResult('PERSON', 0, 8, .9), RecognizerResult('LOCATION', 4, 12, .9)])
        spans = bench.CAPTURE[-1][1]
        bench.CAPTURE_ENABLED = False
        self.assertTrue(spans)
        self.assertTrue(all(0 <= row['start'] < row['end'] <= len(source) for row in spans))
        self.assertEqual(result.text, AnonymizerEngine().anonymize(text=source, analyzer_results=[RecognizerResult('PERSON', 0, 8, .9), RecognizerResult('LOCATION', 4, 12, .9)]).text)


if __name__ == '__main__':
    unittest.main()
