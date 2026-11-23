"""Complete-source evidence checks; zero model/API calls."""
from src.adapters.file_management.decision_trial_judge import source_body


def test_office_sources_are_decoded_as_documents_instead_of_utf8_zip(tmp_path):
    from docx import Document
    from openpyxl import Workbook
    p=tmp_path/'a.docx';d=Document();d.add_paragraph('Independent complete body');d.save(p)
    assert source_body(p,tmp_path/'ocr')['text']=='Independent complete body'
    p=tmp_path/'table.xlsx';b=Workbook();b.active.append(['version',2]);b.save(p)
    assert source_body(p,tmp_path/'ocr')['sheets']=={'Sheet':[['version',2]]}


def test_binary_data_is_marked_unreadable_instead_of_inventing_text(tmp_path):
    p=tmp_path/'data.bin';p.write_bytes(b'\xff\x00\xfe')
    assert source_body(p,tmp_path/'ocr')=={'unreadable_binary':True,'bytes':3}
