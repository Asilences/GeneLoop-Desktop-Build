"""Local page evidence for PPT tasks that defer PDF OCR and image reads."""
import hashlib
import re


def read_ppt_pdf_index(data: bytes, *, over_pages: int):
    import pymupdf as fitz

    with fitz.open(stream=data, filetype='pdf') as pdf:
        if pdf.needs_pass:
            raise ValueError('pdf_encrypted')
        if len(pdf) <= over_pages:
            return None
        digest = hashlib.sha256(data).hexdigest()
        pages = []
        for number, page in enumerate(pdf, 1):
            native = page.get_text(sort=True)
            images = page.get_image_info()
            scan = any(fitz.Rect(image['bbox']).get_area() > page.rect.get_area() * .65 for image in images)
            needs_ocr = not native.strip() or (scan and len(re.sub(r'\s', '', native)) < 160)
            row = {'page': number, 'source_id': f'pdf:{digest}:page:{number}',
                   'text': native, 'text_method': 'text_layer', 'ocr_performed': False, 'ocr_needed': needs_ocr,
                   'visual_present': bool(images or page.get_drawings()), 'visual_content_reviewed': False,
                   'captions': re.findall(r'(?im)^\s*(?:fig(?:ure)?\.?\s*\d+|图\s*\d+)[^\n]*(?:\n[^\n]+)?', native),
                   'local_index_excerpt': ' '.join(native.split())[:160], 'visual_reading': 'on_demand'}
            if needs_ocr:
                row['ocr_status'] = 'on_demand'
            pages.append(row)
    return {'pipeline_version': 'ppt-pdf-index-v1', 'sha256': digest, 'page_count': len(pages),
            'pages': pages, 'text': '\n\f\n'.join(row['text'] for row in pages), 'ocr_performed': False,
            'coverage': 'local_pdf_page_index', 'visual_content_reviewed': False,
            'warnings': ['Full text, OCR and page images are available on demand.']}
