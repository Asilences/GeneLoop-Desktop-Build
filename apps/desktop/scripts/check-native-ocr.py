"""Actual OCR using the bundled PyMuPDF engine and pinned offline language data."""
from pathlib import Path
import json
import os
import sys
import tempfile

tools = Path(sys.argv[1]).resolve(strict=True)
sys.path.insert(0, str(tools / 'source'))
os.environ.update(GENELOOP_PDF_OCR_ROOT=str(tools / 'ocr'), GENELOOP_DESKTOP_OCR_LOCK='1')
from src.adapters.geneloop_pdf import read_pdf
from src.adapters.desktop_general import verify_native_ocr
verify_native_ocr()
from PIL import Image, ImageDraw, ImageFont
import pymupdf as fitz

with tempfile.TemporaryDirectory(prefix='geneloop-native-ocr-') as private:
    directory = Path(private).resolve()
    assert directory.parent == Path(tempfile.gettempdir()).resolve()
    candidates = [Path('C:/Windows/Fonts/msyh.ttc'), Path('/System/Library/Fonts/PingFang.ttc')]
    font_path = next((p for p in candidates if p.is_file()), None)
    font = ImageFont.truetype(str(font_path), 90) if font_path else ImageFont.load_default(size=90)
    image = Image.new('RGB', (1800, 500), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((70, 60), 'GENELOOP OCR 314159', fill='black', font=font)
    if font_path: draw.text((70, 240), '让研究向前一步', fill='black', font=font)
    source = directory / 'scan.png'
    image.save(source)
    pdf = fitz.open()
    page = pdf.new_page(width=720, height=200)
    page.insert_image(page.rect, filename=str(source))
    data = pdf.tobytes()
    pdf.close()
    result = read_pdf(data, page_number=1)
    assert result['ocr_performed'], result['pages'][0].get('warning')
    assert '314159' in result['text'], result['text']
    print(json.dumps({'actual_ocr': True, 'offline': True, 'platform': sys.platform,
                      'language': result['pages'][0]['ocr_language'],
                      'chinese_fixture': bool(font_path), 'model_requests': 0}))
