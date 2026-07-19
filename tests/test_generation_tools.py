"""Test the Docling MCP server generation tools."""

import re
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from docling_core.types.doc.base import ImageRefMode

from docling_mcp.logger import setup_logger
from docling_mcp.shared import local_document_cache
from docling_mcp.tools.generation import (
    NewDoclingDocumentOutput,
    SaveDocumentOutput,
    UpdateDocumentOutput,
    add_paragraph_to_docling_document,
    add_table_in_html_format_to_docling_document,
    create_new_docling_document,
    get_docling_document_archive,
    save_docling_document,
)

logger = setup_logger()


@pytest.fixture
def doc_key() -> str:
    reply = create_new_docling_document(prompt="test-document")

    assert isinstance(reply, NewDoclingDocumentOutput)
    key = reply.document_key
    assert key in local_document_cache
    match = re.match(r"[a-fA-F0-9]{32}$", key)
    assert match is not None
    assert reply.prompt == "test-document"

    return key


def test_table_in_html_format_to_docling_document(doc_key: str) -> None:
    html_table: str = (
        "<table><tr><th colspan='2'>Demographics</th></tr><tr><th>Name</th><th>Age"
        "</th></tr><tr><td>John</td><td rowspan='2'>30</td></tr><tr><td>Jane</td></tr>"
        "</table>"
    )

    reply = add_table_in_html_format_to_docling_document(
        document_key=doc_key,
        html_table=html_table,
        table_captions=["Table 2: Complex demographic data with merged cells"],
    )

    assert isinstance(reply, UpdateDocumentOutput)
    assert reply.document_key == doc_key


@pytest.mark.parametrize(
    ("output_format", "extension"),
    [("json", "json"), ("html", "html"), ("markdown", "md")],
)
def test_save_document_in_requested_format(
    output_format: str,
    extension: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_key = "saved-document"
    document = Mock()
    local_document_cache[document_key] = document
    monkeypatch.setattr("docling_mcp.tools.generation.get_cache_dir", lambda: tmp_path)

    def add_image(artifacts_dir: Path) -> None:
        artifacts_dir.mkdir(exist_ok=True)
        (artifacts_dir / "image.png").write_bytes(b"image")

    def save_json(filename: str, artifacts_dir: Path, image_mode: ImageRefMode) -> None:
        Path(filename).write_text("{}", encoding="utf-8")
        add_image(Path(filename).parent / artifacts_dir)

    def save_html(filename: str, artifacts_dir: Path, image_mode: ImageRefMode) -> None:
        Path(filename).write_text(
            "<html><head><style>p { color: red; }</style></head>"
            '<body><p class="text">document</p></body></html>',
            encoding="utf-8",
        )
        add_image(Path(filename).parent / artifacts_dir)

    def save_markdown(
        filename: str,
        artifacts_dir: Path,
        image_mode: ImageRefMode,
        text_width: int,
    ) -> None:
        Path(filename).write_text("document", encoding="utf-8")
        add_image(Path(filename).parent / artifacts_dir)

    document.save_as_json.side_effect = save_json
    document.save_as_html.side_effect = save_html
    document.save_as_markdown.side_effect = save_markdown

    try:
        reply = save_docling_document(document_key, output_format)  # type: ignore[arg-type]
    finally:
        local_document_cache.pop(document_key, None)

    assert isinstance(reply, SaveDocumentOutput)
    assert reply.file_path == str(tmp_path / f"{document_key}-{output_format}.zip")
    assert reply.output_format == output_format
    assert (
        reply.resource_uri == f"docling://documents/{document_key}/{output_format}.zip"
    )

    with ZipFile(reply.file_path) as archive:
        assert f"{document_key}.{extension}" in archive.namelist()
        artifacts_dir = f"{document_key}-{output_format}_artifacts"
        assert f"{artifacts_dir}/" in archive.namelist()
        assert f"{artifacts_dir}/image.png" in archive.namelist()
        if output_format == "html":
            html = archive.read(f"{document_key}.html").decode()
            assert "<style" not in html
            assert "class=" not in html
            assert 'style="color:red"' in html

    if output_format == "json":
        document.save_as_json.assert_called_once_with(
            filename=str(tmp_path / f"{document_key}.json"),
            artifacts_dir=Path(f"{document_key}-json_artifacts"),
            image_mode=ImageRefMode.REFERENCED,
        )
    elif output_format == "html":
        document.save_as_html.assert_called_once_with(
            filename=str(tmp_path / f"{document_key}.html"),
            artifacts_dir=Path(f"{document_key}-html_artifacts"),
            image_mode=ImageRefMode.REFERENCED,
        )
    else:
        document.save_as_markdown.assert_called_once_with(
            filename=str(tmp_path / f"{document_key}.md"),
            artifacts_dir=Path(f"{document_key}-markdown_artifacts"),
            image_mode=ImageRefMode.REFERENCED,
            text_width=72,
        )


def test_document_archive_resource(
    doc_key: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("docling_mcp.tools.generation.get_cache_dir", lambda: tmp_path)
    add_paragraph_to_docling_document(doc_key, "resource body")
    save_docling_document(doc_key, "markdown")

    archive_bytes = get_docling_document_archive(doc_key, "markdown")

    with ZipFile(BytesIO(archive_bytes)) as archive:
        markdown = archive.read(f"{doc_key}.md").decode()
    assert "resource body" in markdown
