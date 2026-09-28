"""Contract tests for the unified V2 parse result.

These lock the shape downstream parsers, the indexer and (eventually) the
upload API depend on.  No test here touches the filesystem beyond the standard
``tmp_path`` fixture, and none of them imports ``app.rag.retriever`` or any
Chroma code, so the suite runs with ``--noconftest`` as well as in the full
run.
"""
from app.rag.parser_result import (
    BlockType,
    ContentBlock,
    DocumentParseResult,
    ParseError,
    ParseStatus,
    ParserType,
    SourceLocation,
    render_block_for_index,
)


def test_status_tokens_are_stable():
    assert {s.value for s in ParseStatus} == {
        "success",
        "partial_success",
        "empty",
        "failed",
    }
    assert ParseStatus.EMPTY is not ParseStatus.FAILED


def test_source_location_omits_unknown_fields():
    location = SourceLocation(file_path="a.pdf", page=3)
    payload = location.as_dict()
    assert payload == {"file_path": "a.pdf", "page": 3}
    assert "sheet" not in payload


def test_source_location_label_is_readable_and_ordered():
    location = SourceLocation(
        file_path="sales.xlsx",
        sheet="2026Q1",
        row_start=2,
        row_end=10,
        column_start=1,
        column_end=4,
    )
    assert location.label() == "sheet=2026Q1 rows=2-10 cols=1-4"


def test_text_block_serializes_content():
    block = ContentBlock(
        block_type=BlockType.TEXT,
        parser_type=ParserType.PYPDF,
        content="revenue grew 12%",
        location=SourceLocation(file_path="r.pdf", page=1),
    )
    payload = block.as_dict()
    assert payload["block_type"] == "text"
    assert payload["parser_type"] == "pypdf"
    assert payload["content"] == "revenue grew 12%"
    assert payload["location"]["page"] == 1


def test_table_block_serializes_rows_and_header_not_content():
    block = ContentBlock(
        block_type=BlockType.TABLE,
        parser_type=ParserType.DOCX_TABLE,
        header=("month", "amount"),
        rows=(("jan", "10"), ("feb", "20")),
        location=SourceLocation(file_path="t.docx", table_index=1),
    )
    payload = block.as_dict()
    assert payload["header"] == ["month", "amount"]
    assert payload["rows"] == [["jan", "10"], ["feb", "20"]]
    assert "content" not in payload


def test_render_block_for_index_keeps_structure_and_location():
    block = ContentBlock(
        block_type=BlockType.TABLE,
        parser_type=ParserType.DOCX_TABLE,
        header=("month", "amount"),
        rows=(("jan", "10"), ("feb", "20")),
        location=SourceLocation(file_path="t.docx", table_index=1),
    )
    rendered = render_block_for_index(block)
    assert "[table=1]" in rendered
    assert rendered.endswith("jan\t10\nfeb\t20")


def test_render_block_for_index_strips_cell_line_breaks():
    block = ContentBlock(
        block_type=BlockType.DATA_ROWS,
        parser_type=ParserType.EXCEL_KB,
        rows=(("a\nb", "c\td"),),
        location=SourceLocation(file_path="s.xlsx", sheet="S1"),
    )
    rendered = render_block_for_index(block)
    assert "\na\nb\n" not in rendered
    assert "a b" in rendered


def test_plain_text_excludes_structured_blocks():
    result = DocumentParseResult.success(
        source="doc.pdf",
        extension=".pdf",
        parsers=[ParserType.PYPDF],
        blocks=[
            ContentBlock(BlockType.TEXT, ParserType.PYPDF, content="first"),
            ContentBlock(
                BlockType.TABLE,
                ParserType.PDF_TABLE,
                rows=(("a", "b"),),
                location=SourceLocation(file_path="doc.pdf", page=2),
            ),
            ContentBlock(BlockType.OCR, ParserType.OCR, content="scanned page"),
        ],
    )
    assert result.plain_text == "first\n\nscanned page"
    assert "a\tb" not in result.plain_text


def test_to_index_text_includes_structured_blocks():
    result = DocumentParseResult.success(
        source="doc.pdf",
        extension=".pdf",
        parsers=[ParserType.PYPDF],
        blocks=[
            ContentBlock(BlockType.TEXT, ParserType.PYPDF, content="first"),
            ContentBlock(
                BlockType.TABLE,
                ParserType.PDF_TABLE,
                header=("h",),
                rows=(("v",),),
                location=SourceLocation(file_path="doc.pdf", page=2, table_index=0),
            ),
        ],
    )
    text = result.to_index_text()
    assert text.startswith("first")
    assert "[page=2 table=0]" in text


def test_failed_result_requires_failure_reason():
    result = DocumentParseResult.failed(
        source="bad.pdf",
        extension=".pdf",
        failure_reason="pypdf raised: EOF marker not found",
        parsers=[ParserType.PYPDF],
    )
    assert result.status is ParseStatus.FAILED
    assert result.failure_reason is not None
    assert result.as_dict()["failure_reason"] == result.failure_reason


def test_empty_is_not_a_silent_success_or_failure():
    result = DocumentParseResult.empty(source="blank.pdf", extension=".pdf")
    assert result.status is ParseStatus.EMPTY
    assert result.blocks == ()
    assert result.as_dict()["status"] == "empty"


def test_parse_error_serializes_code_message_and_retryable():
    error = ParseError(
        code="ocr_low_confidence",
        message="page 3 confidence below threshold",
        parser=ParserType.OCR,
        location=SourceLocation(file_path="scan.pdf", page=3),
        retryable=True,
    )
    payload = error.as_dict()
    assert payload["code"] == "ocr_low_confidence"
    assert payload["parser"] == "ocr"
    assert payload["retryable"] is True
    assert payload["location"]["page"] == 3

def test_failed_result_can_carry_aggregate_errors():
    error = ParseError(
        code="ocr_engine_missing",
        message="OCR requested but no engine provided",
        parser=ParserType.OCR,
        location=SourceLocation(file_path="scan.pdf"),
    )
    result = DocumentParseResult(
        source="scan.pdf",
        extension=".pdf",
        status=ParseStatus.PARTIAL_SUCCESS,
        blocks=(),
        parsers=(ParserType.OCR,),
        errors=(error,),
    )
    assert result.errors == (error,)
    assert result.as_dict()["errors"][0]["code"] == "ocr_engine_missing"
