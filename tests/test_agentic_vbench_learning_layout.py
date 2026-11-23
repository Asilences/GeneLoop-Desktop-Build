import json
from pathlib import Path
import tempfile
import unittest
from src.rsi.feedback.capability_feedback import file_ref, verify
from scenarios.agentic_vbench.learning import execution_boundary


class VideoLearningLayoutTests(unittest.TestCase):
    def boundary(self, root):
        work=root/'captured';(work/'code').mkdir(parents=True)
        data=work/'code/spec.json';data.write_text('{"current": 7}')
        value={'workspace':str(work),'workdir':'/workspace/program','call_id':'one',
               'before':{'complete':True,'files':{'code/spec.json':file_ref(data)}}}
        record=root/'original-boundary.json';record.write_text(json.dumps(value))
        return work,data,record

    def test_original_capture_stays_unchanged_and_execution_copy_retains_all_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);work,data,record=self.boundary(root);original=record.read_bytes()
            (work/'outputs/code/model-created-empty').mkdir(parents=True)
            projected=execution_boundary(file_ref(record),root/'projection/before',verify)
            copied=Path(projected['workspace'])
            self.assertTrue((copied/'command-tmp').is_dir())
            self.assertTrue((copied/'outputs/code/model-created-empty').is_dir())
            self.assertFalse((work/'command-tmp').exists())
            self.assertEqual(record.read_bytes(),original)
            self.assertEqual(verify(projected['before']['files']['code/spec.json']),data.read_bytes())
            self.assertEqual(projected['original_boundary'],file_ref(record))

    def test_changed_or_unrecorded_input_is_not_silently_copied(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);work,data,record=self.boundary(root)
            data.write_text('{"current": 8}')
            with self.assertRaises(ValueError):
                execution_boundary(file_ref(record),root/'changed/before',verify)
            (work/'code/unrecorded.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'file_set_changed'):
                execution_boundary(file_ref(record),root/'unrecorded/before',verify)


if __name__=='__main__':
    unittest.main()
