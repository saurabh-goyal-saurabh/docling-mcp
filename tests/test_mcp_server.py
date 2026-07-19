"""Test the Docling MCP server tools with a dummy client."""

import base64
import json
from collections.abc import AsyncGenerator
from io import BytesIO
from typing import Any
from zipfile import ZipFile

import anyio
import pytest
from mcp import Tool


@pytest.mark.asyncio
async def test_list_tools(mcp_client: AsyncGenerator[Any, Any]) -> None:
    tools = await mcp_client.list_tools()  # type: ignore[attr-defined]
    assert isinstance(tools, list)
    gold_tools = [
        "is_document_in_local_cache",
        "convert_document_into_docling_document",
        "convert_directory_files_into_docling_document",
        # "convert_attachments_into_docling_document",
        "create_new_docling_document",
        "export_docling_document_to_markdown",
        "save_docling_document",
        "page_thumbnail",
        "add_title_to_docling_document",
        "add_section_heading_to_docling_document",
        "add_paragraph_to_docling_document",
        "open_list_in_docling_document",
        "close_list_in_docling_document",
        "add_list_items_to_list_in_docling_document",
        "add_table_in_html_format_to_docling_document",
        "get_overview_of_document_anchors",
        "search_for_text_in_document_anchors",
        "get_text_of_document_item_at_anchor",
        "update_text_of_document_item_at_anchor",
        "delete_document_items_at_anchors",
    ]

    assert tools == gold_tools


@pytest.mark.asyncio()
async def test_get_tools(mcp_client: AsyncGenerator[Any, Any]) -> None:
    tools: list[Tool] = await mcp_client.get_tools()  # type: ignore[attr-defined]

    sample_tool = next(
        item for item in tools if item.name == "add_paragraph_to_docling_document"
    )
    async with await anyio.open_file(
        "tests/data/gt_tool_add_paragraph.json", encoding="utf-8"
    ) as input_file:
        contents = await input_file.read()
        gold_tool = json.loads(contents)
        assert gold_tool == sample_tool.model_dump()


@pytest.mark.asyncio()
async def test_call_tool(mcp_client: AsyncGenerator[Any, Any]) -> None:
    res = await mcp_client.call_tool(  # type: ignore[attr-defined]
        "create_new_docling_document", {"prompt": "A new Docling document for testing"}
    )

    # always check if there's been a parsing error through `isError`, since no
    # exception will be raised
    assert not res.isError
    assert isinstance(res.content, list)
    assert len(res.content) == 1
    # there are 2 results: text as an MCP TextContent type...
    assert res.content[0].type == "text"
    assert res.content[0].text.startswith('{\n  "document_key": ')
    # ...the structured output
    assert res.structuredContent["prompt"] == "A new Docling document for testing"
    assert len(res.structuredContent["document_key"]) == 32

    # if no structured output, a schema is infered with the field `result`
    res = await mcp_client.call_tool(  # type: ignore[attr-defined]
        "create_new_docling_document", {}
    )
    assert isinstance(res.content, list)
    assert len(res.content) == 1
    assert "validation error" in res.content[0].text
    assert res.structuredContent is None


@pytest.mark.asyncio()
async def test_document_resource_templates(
    mcp_client: AsyncGenerator[Any, Any],
) -> None:
    response = await mcp_client.list_resource_templates()  # type: ignore[attr-defined]
    templates = {
        template.uriTemplate: template.mimeType
        for template in response.resourceTemplates
    }

    assert templates == {
        "docling://documents/{document_key}/{output_format}.zip": "application/zip",
    }


@pytest.mark.asyncio()
async def test_read_document_resource(mcp_client: AsyncGenerator[Any, Any]) -> None:
    created = await mcp_client.call_tool(  # type: ignore[attr-defined]
        "create_new_docling_document", {"prompt": "resource test"}
    )
    document_key = created.structuredContent["document_key"]
    await mcp_client.call_tool(  # type: ignore[attr-defined]
        "add_paragraph_to_docling_document",
        {"document_key": document_key, "paragraph": "resource body"},
    )
    await mcp_client.call_tool(  # type: ignore[attr-defined]
        "save_docling_document",
        {"document_key": document_key, "output_format": "markdown"},
    )

    response = await mcp_client.read_resource(  # type: ignore[attr-defined]
        f"docling://documents/{document_key}/markdown.zip"
    )

    assert len(response.contents) == 1
    assert response.contents[0].mimeType == "application/zip"
    archive_bytes = base64.b64decode(response.contents[0].blob)
    with ZipFile(BytesIO(archive_bytes)) as archive:
        markdown = archive.read(f"{document_key}.md").decode()
    assert "resource body" in markdown
