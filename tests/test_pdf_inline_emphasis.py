from pypdf import PdfReader

from app.tools import export


def test_report_body_hides_markdown_emphasis_and_keeps_numbers(tmp_path, monkeypatch):
    monkeypatch.setattr(export, 'EXPORT_DIR', str(tmp_path))
    path = export.generate_pdf_report('记录分析', [
        {'type': 'text', 'content': '**总行数**：42 行\n**列数**：3 列\n计算表达式：6 * 7 = 42'},
    ])
    text = '\n'.join(page.extract_text() for page in PdfReader(path).pages)
    assert '**' not in text
    assert '总行数：42' in text and '列数：3' in text
    assert '6 * 7 = 42' in text
