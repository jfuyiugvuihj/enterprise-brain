import pandas as pd
from app.common.identity import Principal
from app.documents.preview import build_document_preview


def test_spreadsheet_document_preview_filters_every_sheet(tmp_path):
    filename = tmp_path / '混合表.xlsx'
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        for name in ('明细', '第二张表'):
            pd.DataFrame({'编号': ['FIN-VISIBLE', 'SALES-HIDDEN'],
                          '部门': ['财务', '销售'], '金额': [42, 999]}).to_excel(writer, sheet_name=name, index=False)
    principal = Principal.from_user({'id': 'fin', 'username': 'fin', 'role': 'manager', 'department': '财务'})
    result = build_document_preview(str(filename), principal=principal)
    assert 'FIN-VISIBLE' in result['text'] and '第二张表' in result['text']
    assert 'SALES-HIDDEN' not in result['text'] and '999' not in result['text']
    assert result['row_scope']['rows_in'] == 4
    assert result['row_scope']['rows_visible'] == 2


def test_csv_document_preview_keeps_admin_rows_but_hides_other_departments(tmp_path):
    filename = tmp_path / '混合表.csv'
    pd.DataFrame({'编号': ['FIN', 'HIDDEN'], '部门': ['财务', '销售'], '金额': [42, 999]}).to_csv(filename, index=False)
    finance = Principal.from_user({'id': 'fin', 'username': 'fin', 'role': 'manager', 'department': '财务'})
    administrator = Principal.from_user({'id': 'admin', 'username': 'admin', 'role': 'admin'})
    assert 'HIDDEN' not in build_document_preview(str(filename), principal=finance)['text']
    assert 'HIDDEN' in build_document_preview(str(filename), principal=administrator)['text']
