"""Tools for generating Docling documents."""

import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import Annotated, Literal
from zipfile import ZIP_DEFLATED, ZipFile

from mcp.server.fastmcp import Image as MCPImage
from mcp.types import ToolAnnotations
from premailer import transform
from pydantic import Field

from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.document import (
    ConversionResult,
)
from docling_core.types.doc.base import ImageRefMode
from docling_core.types.doc.document import (
    ContentLayer,
    DoclingDocument,
    GroupItem,
    LevelNumber,
)
from docling_core.types.doc.labels import (
    DocItemLabel,
    GroupLabel,
)
from docling_core.types.io import DocumentStream

from docling_mcp.docling_cache import get_cache_dir
from docling_mcp.logger import setup_logger
from docling_mcp.shared import local_document_cache, local_stack_cache, mcp

# Create a default project logger
logger = setup_logger()


@dataclass
class NewDoclingDocumentOutput:
    """Output of the create_new_docling_document tool."""

    document_key: Annotated[
        str, Field(description="The unique key that identifies the new document.")
    ]
    prompt: Annotated[str, Field(description="The original prompt.")]


@mcp.tool(
    title="Create new Docling document",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def create_new_docling_document(
    prompt: Annotated[
        str, Field(description="The prompt text to include in the new document.")
    ],
) -> NewDoclingDocumentOutput:
    """Create a new Docling document from a provided prompt string.

    This function generates a new document in the local document cache with the
    provided prompt text. The document is assigned a unique key derived from an MD5
    hash of the prompt text.
    """
    doc = DoclingDocument(name="Generated Document")

    item = doc.add_text(
        label=DocItemLabel.TEXT,
        text=f"prompt: {prompt}",
        content_layer=ContentLayer.FURNITURE,
    )

    document_key = str(uuid.uuid4()).replace("-", "")

    local_document_cache[document_key] = doc
    local_stack_cache[document_key] = [item]

    return NewDoclingDocumentOutput(document_key, prompt)


@dataclass
class ExportDocumentMarkdownOutput:
    """Output of the export_docling_document_to_markdown tool."""

    document_key: Annotated[
        str,
        Field(description="The unique identifier of the document in the local cache."),
    ]
    markdown: Annotated[
        str, Field(description="The representation of the document in markdown format.")
    ]


@mcp.tool(
    title="Export Docling document to markdown format",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def export_docling_document_to_markdown(
    document_key: Annotated[
        str,
        Field(description="The unique identifier of the document in the local cache."),
    ],
    max_size: Annotated[
        int | None, Field(description="The maximum number of characters to return.")
    ] = None,
) -> ExportDocumentMarkdownOutput:
    """Export a document from the local document cache to markdown format.

    This tool converts a Docling document that exists in the local cache into
    a markdown formatted string, which can be used for display or further processing.
    """
    if document_key not in local_document_cache:
        doc_keys = ", ".join(local_document_cache.keys())
        raise ValueError(
            f"document-key: {document_key} is not found. Existing document-keys are: {doc_keys}"
        )

    markdown = local_document_cache[document_key].export_to_markdown()
    if max_size:
        markdown = markdown[:max_size]

    return ExportDocumentMarkdownOutput(document_key, markdown)


@dataclass
class SaveDocumentOutput:
    """Output of the save_docling_document tool."""

    file_path: Annotated[
        str,
        Field(description="The path to the ZIP archive on the server."),
    ]
    output_format: Annotated[
        str,
        Field(description="The format used to save the document."),
    ]
    resource_uri: Annotated[
        str,
        Field(description="The MCP resource URI for retrieving the document."),
    ]


@mcp.tool(
    title="Save Docling document",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def save_docling_document(
    document_key: Annotated[
        str,
        Field(description="The unique identifier of the document in the local cache."),
    ],
    output_format: Annotated[
        Literal["json", "html", "markdown"],
        Field(description="The format in which to save the document."),
    ],
) -> SaveDocumentOutput:
    """Save a cached document and package it as a ZIP archive.

    The archive always contains the requested JSON, HTML, or Markdown document
    and its referenced image-assets directory. HTML CSS is inlined on elements.
    """
    if document_key not in local_document_cache:
        doc_keys = ", ".join(local_document_cache.keys())
        raise ValueError(
            f"document-key: {document_key} is not found. Existing document-keys are: {doc_keys}"
        )

    cache_dir = get_cache_dir()
    doc = local_document_cache[document_key]
    extension = {"json": "json", "html": "html", "markdown": "md"}[output_format]
    document_path = cache_dir / f"{document_key}.{extension}"
    artifacts_path = cache_dir / f"{document_key}-{output_format}_artifacts"
    artifacts_path.mkdir(parents=True, exist_ok=True)
    artifacts_reference = artifacts_path.relative_to(cache_dir)

    if output_format == "json":
        doc.save_as_json(
            filename=str(document_path),
            artifacts_dir=artifacts_reference,
            image_mode=ImageRefMode.REFERENCED,
        )
    elif output_format == "html":
        doc.save_as_html(
            filename=str(document_path),
            artifacts_dir=artifacts_reference,
            image_mode=ImageRefMode.REFERENCED,
        )
        html = document_path.read_text(encoding="utf-8")
        inlined_html = transform(
            html,
            allow_network=False,
            disable_leftover_css=True,
            disable_validation=True,
            keep_style_tags=False,
            remove_classes=True,
        )
        document_path.write_text(inlined_html, encoding="utf-8")
    else:
        doc.save_as_markdown(
            filename=str(document_path),
            artifacts_dir=artifacts_reference,
            image_mode=ImageRefMode.REFERENCED,
            text_width=72,
        )

    archive_path = cache_dir / f"{document_key}-{output_format}.zip"
    with ZipFile(archive_path, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.write(document_path, arcname=document_path.name)
        archive.writestr(f"{artifacts_path.name}/", b"")
        for artifact in artifacts_path.rglob("*"):
            if artifact.is_file():
                archive.write(artifact, arcname=artifact.relative_to(cache_dir))

    return SaveDocumentOutput(
        file_path=str(archive_path),
        output_format=output_format,
        resource_uri=f"docling://documents/{document_key}/{output_format}.zip",
    )


@mcp.resource(
    "docling://documents/{document_key}/{output_format}.zip",
    name="Docling document archive",
    description="Retrieve a saved Docling document ZIP archive.",
    mime_type="application/zip",
)
def get_docling_document_archive(
    document_key: str,
    output_format: Literal["json", "html", "markdown"],
) -> bytes:
    """Retrieve a saved Docling document ZIP archive."""
    archive_path = get_cache_dir() / f"{document_key}-{output_format}.zip"
    if not archive_path.is_file():
        raise ValueError(
            f"Archive not found: {archive_path}. Call save_docling_document first."
        )
    return archive_path.read_bytes()


@mcp.tool(
    title="Generate the thumbnail of a page in the Docling document",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def page_thumbnail(
    document_key: Annotated[
        str,
        Field(description="The unique identifier of the document in the local cache."),
    ],
    page_no: Annotated[
        int, Field(description="The number of the page starting at 1")
    ] = 1,
    size: Annotated[
        int, Field(description="The width of the thumbnail in pixels")
    ] = 300,
) -> MCPImage:
    """Generate a thumbnail image for the requested page.

    This tool takes a document that exists in the local cache and generates a thumnail image for the requested page.
    """
    if document_key not in local_document_cache:
        doc_keys = ", ".join(local_document_cache.keys())
        raise ValueError(
            f"document-key: {document_key} is not found. Existing document-keys are: {doc_keys}"
        )

    doc = local_document_cache[document_key]
    if page_no not in doc.pages:
        raise ValueError(
            f"page_no={page_no}: not found in the document. Available pages are: {', '.join(str(k) for k in doc.pages.keys())}"
        )

    im_ref = doc.pages[page_no].image
    if im_ref is None:
        raise ValueError(
            "The DoclingDocument does not have page images. Please configure your server for generating page images using DOCLING_MCP_KEEP_IMAGES=true."
        )
    im = im_ref.pil_image
    if im is None:
        raise RuntimeError("Server error. The image cannot be loaded in PIL.")
    width = size
    scale = float(width) / im.size[0]
    im.thumbnail((width, int(im.size[1] * scale)))

    cache_dir = get_cache_dir()
    im_file = cache_dir / f"{document_key}-{page_no}.png"
    im.save(im_file, format="PNG")

    return MCPImage(path=im_file, format="png")


@dataclass
class UpdateDocumentOutput:
    """Output of the Docling document content generation tools."""

    document_key: Annotated[
        str,
        Field(description="The unique identifier of the document in the local cache."),
    ]


@mcp.tool(
    title="Add or update title to Docling document",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def add_title_to_docling_document(
    document_key: Annotated[
        str,
        Field(description="The unique identifier of the document in the local cache."),
    ],
    title: Annotated[
        str, Field(description="The title text to add or update to the document.")
    ],
) -> UpdateDocumentOutput:
    """Add or update the title of a document in the local document cache.

    This tool modifies an existing document that has already been processed
    and stored in the local cache. It requires that the document already exists
    in the cache before a title can be added.
    """
    if document_key not in local_document_cache:
        doc_keys = ", ".join(local_document_cache.keys())
        raise ValueError(
            f"document-key: {document_key} is not found. Existing document-keys are: {doc_keys}"
        )

    if len(local_stack_cache[document_key]) == 0:
        raise ValueError(
            f"Stack size is zero for document with document-key: {document_key}. Abort document generation"
        )

    parent = local_stack_cache[document_key][-1]

    if isinstance(parent, GroupItem):
        if parent.label == GroupLabel.LIST or parent.label == GroupLabel.ORDERED_LIST:
            raise ValueError(
                "A list is currently opened. Please close the list before adding a title!"
            )

    item = local_document_cache[document_key].add_title(text=title)
    local_stack_cache[document_key][-1] = item

    return UpdateDocumentOutput(document_key)


@mcp.tool(
    title="Add section heading to Docling document",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def add_section_heading_to_docling_document(
    document_key: Annotated[
        str,
        Field(description="The unique identifier of the document in the local cache."),
    ],
    section_heading: Annotated[
        str, Field(description="The text to use for the section heading.")
    ],
    section_level: Annotated[
        LevelNumber,
        Field(
            description="The level of the heading, starting from 1, where 1 is the highest level."
        ),
    ],
) -> UpdateDocumentOutput:
    """Add a section heading to an existing document in the local document cache.

    This tool inserts a section heading with the specified heading text and level
    into a document that has already been processed and stored in the local cache.
    Section levels typically represent heading hierarchy (e.g., 1 for H1, 2 for H2).
    """
    if document_key not in local_document_cache:
        doc_keys = ", ".join(local_document_cache.keys())
        raise ValueError(
            f"document-key: {document_key} is not found. Existing document-keys are: {doc_keys}"
        )

    if len(local_stack_cache[document_key]) == 0:
        raise ValueError(
            f"Stack size is zero for document with document-key: {document_key}. Abort document generation"
        )

    parent = local_stack_cache[document_key][-1]

    if isinstance(parent, GroupItem):
        if parent.label == GroupLabel.LIST or parent.label == GroupLabel.ORDERED_LIST:
            raise ValueError(
                "A list is currently opened. Please close the list before adding a section-heading!"
            )

    item = local_document_cache[document_key].add_heading(
        text=section_heading, level=section_level
    )
    local_stack_cache[document_key][-1] = item

    return UpdateDocumentOutput(document_key)


@mcp.tool(
    title="Add paragraph to Docling document",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def add_paragraph_to_docling_document(
    document_key: Annotated[
        str,
        Field(description="The unique identifier of the document in the local cache."),
    ],
    paragraph: Annotated[
        str, Field(description="The text content to add as a paragraph.")
    ],
) -> UpdateDocumentOutput:
    """Add a paragraph of text to an existing document in the local document cache.

    This tool inserts a new paragraph under the specified section header and level
    into a document that has already been processed and stored in the cache.
    """
    if document_key not in local_document_cache:
        doc_keys = ", ".join(local_document_cache.keys())
        raise ValueError(
            f"document-key: {document_key} is not found. Existing document-keys are: {doc_keys}"
        )

    if len(local_stack_cache[document_key]) == 0:
        raise ValueError(
            f"Stack size is zero for document with document-key: {document_key}. Abort document generation"
        )

    parent = local_stack_cache[document_key][-1]

    if isinstance(parent, GroupItem):
        if parent.label == GroupLabel.LIST or parent.label == GroupLabel.ORDERED_LIST:
            raise ValueError(
                "A list is currently opened. Please close the list before adding a paragraph!"
            )

    item = local_document_cache[document_key].add_text(
        label=DocItemLabel.TEXT, text=paragraph
    )
    local_stack_cache[document_key][-1] = item

    return UpdateDocumentOutput(document_key)


@mcp.tool(
    title="Open list in Docling document",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def open_list_in_docling_document(
    document_key: Annotated[
        str,
        Field(description="The unique identifier of the document in the local cache."),
    ],
) -> UpdateDocumentOutput:
    """Open a new list group in an existing document in the local document cache.

    This tool creates a new list structure within a document that has already been
    processed and stored in the local cache. It requires that the document already exists
    and that there is at least one item in the document's stack cache.
    """
    if document_key not in local_document_cache:
        doc_keys = ", ".join(local_document_cache.keys())
        raise ValueError(
            f"document-key: {document_key} is not found. Existing document-keys are: {doc_keys}"
        )

    if len(local_stack_cache[document_key]) == 0:
        raise ValueError(
            f"Stack size is zero for document with document-key: {document_key}. Abort document generation"
        )

    item = local_document_cache[document_key].add_group(label=GroupLabel.LIST)
    local_stack_cache[document_key].append(item)

    return UpdateDocumentOutput(document_key)


@mcp.tool(
    title="Close list in Docling document",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def close_list_in_docling_document(
    document_key: Annotated[
        str,
        Field(description="The unique identifier of the document in the local cache."),
    ],
) -> UpdateDocumentOutput:
    """Closes a list group in an existing document in the local document cache.

    This tool closes a previously opened list structure within a document.
    It requires that the document exists and that there is more than one item
    in the document's stack cache.
    """
    if document_key not in local_document_cache:
        doc_keys = ", ".join(local_document_cache.keys())
        raise ValueError(
            f"document-key: {document_key} is not found. Existing document-keys are: {doc_keys}"
        )

    if len(local_stack_cache[document_key]) <= 1:
        raise ValueError(
            f"Stack size is zero for document with document-key: {document_key}. Abort document generation"
        )

    local_stack_cache[document_key].pop()

    return UpdateDocumentOutput(document_key)


@dataclass
class ListItem:
    """A class to represent a list item pairing."""

    list_item_text: Annotated[str, Field(description="The text of a list item.")]
    list_marker_text: Annotated[str, Field(description="The marker of a list item.")]


@mcp.tool(
    title="Add items to list in Docling document",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def add_list_items_to_list_in_docling_document(
    document_key: Annotated[
        str,
        Field(description="The unique identifier of the document in the local cache."),
    ],
    list_items: Annotated[
        list[ListItem],
        Field(description="A list of list_item_text and list_marker_text items."),
    ],
) -> UpdateDocumentOutput:
    """Add list items to an open list in an existing document in the local document cache.

    This tool inserts new list items with the specified text and marker into an
    open list within a document. It requires that the document exists and that
    there is at least one item in the document's stack cache.
    """
    if document_key not in local_document_cache:
        doc_keys = ", ".join(local_document_cache.keys())
        raise ValueError(
            f"document-key: {document_key} is not found. Existing document-keys are: {doc_keys}"
        )

    if len(local_stack_cache[document_key]) == 0:
        raise ValueError(
            f"Stack size is zero for document with document-key: {document_key}. Abort document generation"
        )

    parent = local_stack_cache[document_key][-1]

    if isinstance(parent, GroupItem):
        if parent.label != GroupLabel.LIST and parent.label != GroupLabel.ORDERED_LIST:
            raise ValueError(
                "No list is currently opened. Please open a list before adding list-items!"
            )
    else:
        raise ValueError(
            "No list is currently opened. Please open a list before adding list-items!"
        )

    for list_item in list_items:
        local_document_cache[document_key].add_list_item(
            text=list_item.list_item_text,
            marker=list_item.list_marker_text,
            parent=parent,
        )

    return UpdateDocumentOutput(document_key)


@mcp.tool(
    title="Add HTML table to Docling document",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def add_table_in_html_format_to_docling_document(
    document_key: Annotated[
        str,
        Field(description="The unique identifier of the document in the local cache."),
    ],
    html_table: Annotated[
        str,
        Field(
            description="The HTML string representation of the table to add.",
            examples=[
                "<table><tr><th>Name</th><th>Age</th></tr><tr><td>John</td><td>30</td></tr></table>",
                "<table><tr><th colspan='2'>Demographics</th></tr><tr><th>Name</th><th>Age</th></tr><tr><td>John</td><td rowspan='2'>30</td></tr><tr><td>Jane</td></tr></table>",
            ],
        ),
    ],
    table_captions: Annotated[
        list[str] | None,
        Field(description="A list of caption strings to associate with the table.."),
    ] = None,
    table_footnotes: Annotated[
        list[str] | None,
        Field(description="A list of footnote strings to associate with the table."),
    ] = None,
) -> UpdateDocumentOutput:
    """Add an HTML-formatted table to an existing document in the local document cache.

    This tool parses the provided HTML table string, converts it to a structured table
    representation, and adds it to the specified document. It also supports optional
    captions and footnotes for the table.
    """
    if document_key not in local_document_cache:
        doc_keys = ", ".join(local_document_cache.keys())
        raise ValueError(
            f"document-key: {document_key} is not found. Existing document-keys are: {doc_keys}"
        )

    doc = local_document_cache[document_key]

    if len(local_stack_cache[document_key]) == 0:
        raise ValueError(
            f"Stack size is zero for document with document-key: {document_key}. Abort document generation"
        )

    html_doc: str = f"<html><body>{html_table}</body></html>"

    buff = BytesIO(html_doc.encode("utf-8"))
    doc_stream = DocumentStream(name="tmp", stream=buff)

    # Import DocumentConverter only when needed for HTML table parsing
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as e:
        raise ImportError(
            "HTML table generation requires docling-mcp[local] extra. "
            "Install with: pip install docling-mcp[local]"
        ) from e

    converter = DocumentConverter(allowed_formats=[InputFormat.HTML])
    conv_result: ConversionResult = converter.convert(doc_stream)

    if (
        conv_result.status == ConversionStatus.SUCCESS
        and len(conv_result.document.tables) > 0
    ):
        table = doc.add_table(data=conv_result.document.tables[0].data)

        for _ in table_captions or []:
            caption = doc.add_text(label=DocItemLabel.CAPTION, text=_)
            table.captions.append(caption.get_ref())

        for _ in table_footnotes or []:
            footnote = doc.add_text(label=DocItemLabel.FOOTNOTE, text=_)
            table.footnotes.append(footnote.get_ref())
    else:
        raise ValueError(
            "Could not parse the html string of the table! Please fix the html and try again!"
        )

    return UpdateDocumentOutput(document_key)
