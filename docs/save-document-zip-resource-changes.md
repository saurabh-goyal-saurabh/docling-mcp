# Docling MCP: Save Tool and ZIP Resource Changes

This document defines the MCP server and client changes required to save a
Docling document as JSON, HTML, or Markdown and download it as a portable ZIP
archive.

## Required behavior

1. `save_docling_document` MUST accept an `output_format` argument.
2. Supported formats MUST be `json`, `html`, and `markdown`.
3. The tool MUST always create and return a ZIP archive, regardless of whether
   the document contains images.
4. Images MUST be written as referenced asset files. Base64-encoded images MUST
   NOT be embedded in JSON, HTML, or Markdown.
5. Every ZIP MUST contain an assets directory, including when the directory is
   empty.
6. Image references inside the document MUST be relative paths that remain valid
   after extracting the ZIP. Server-local absolute paths MUST NOT be emitted.
7. HTML CSS MUST be converted to inline `style` attributes. The final HTML MUST
   NOT depend on a `<style>` block or CSS classes.
8. The MCP server MUST expose only one document-download resource template, with
   MIME type `application/zip`.

## Tool contract

### Tool name

`save_docling_document`

### Input schema

```json
{
  "type": "object",
  "properties": {
    "document_key": {
      "type": "string",
      "description": "The unique identifier of the document in the local cache."
    },
    "output_format": {
      "type": "string",
      "enum": ["json", "html", "markdown"],
      "description": "The format in which to save the document."
    }
  },
  "required": ["document_key", "output_format"]
}
```

### Output schema

```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "Server-local path to the generated ZIP archive."
    },
    "output_format": {
      "type": "string",
      "description": "The selected document format."
    },
    "resource_uri": {
      "type": "string",
      "description": "MCP resource URI from which the ZIP can be downloaded."
    }
  },
  "required": ["file_path", "output_format", "resource_uri"]
}
```

### Example call

```json
{
  "name": "save_docling_document",
  "arguments": {
    "document_key": "a07dfe3a8f4265922dee5f68fc6b3880",
    "output_format": "html"
  }
}
```

### Example result

```json
{
  "file_path": "/server/cache/a07dfe3a8f4265922dee5f68fc6b3880-html.zip",
  "output_format": "html",
  "resource_uri": "docling://documents/a07dfe3a8f4265922dee5f68fc6b3880/html.zip"
}
```

`file_path` is informational and normally cannot be opened directly by a remote
MCP client. Clients MUST use `resource_uri` to retrieve the archive.

## Resource contract

### Resource template

```text
docling://documents/{document_key}/{output_format}.zip
```

Both template parameters are required. `output_format` MUST be one of `json`,
`html`, or `markdown`.

### Resource metadata

```json
{
  "uriTemplate": "docling://documents/{document_key}/{output_format}.zip",
  "name": "Docling document archive",
  "description": "Retrieve a saved Docling document ZIP archive.",
  "mimeType": "application/zip"
}
```

### Resource response

The resource returns binary ZIP data. At the MCP protocol level this is a
`BlobResourceContents` object:

```json
{
  "uri": "docling://documents/a07dfe3a8f4265922dee5f68fc6b3880/html.zip",
  "mimeType": "application/zip",
  "blob": "<base64-encoded ZIP bytes>"
}
```

The `blob` field is base64 because MCP JSON transports binary resources that
way. This is distinct from embedding images as base64 inside the exported
document. The client MUST base64-decode `blob` to recover the ZIP bytes. Some MCP
SDKs perform this decoding automatically; clients should check the SDK type they
receive.

The resource SHOULD return an error instructing the caller to invoke
`save_docling_document` first when the requested archive does not exist.

## ZIP layout

### JSON

```text
{document_key}-json.zip
├── {document_key}.json
└── {document_key}-json_artifacts/
    └── image_....png
```

### HTML

```text
{document_key}-html.zip
├── {document_key}.html
└── {document_key}-html_artifacts/
    └── image_....png
```

### Markdown

```text
{document_key}-markdown.zip
├── {document_key}.md
└── {document_key}-markdown_artifacts/
    └── image_....png
```

The assets directory MUST be present even when there are no asset files.

## Server implementation requirements

Use Docling's referenced-image mode for every format:

```python
from docling_core.types.doc.base import ImageRefMode

image_mode = ImageRefMode.REFERENCED
```

Pass a relative assets-directory path to Docling. Passing an absolute path causes
Docling to write server-local absolute paths into the exported document.

```python
cache_dir = get_cache_dir()
document_path = cache_dir / f"{document_key}.html"
artifacts_path = cache_dir / f"{document_key}-html_artifacts"
artifacts_reference = artifacts_path.relative_to(cache_dir)

document.save_as_html(
    filename=str(document_path),
    artifacts_dir=artifacts_reference,
    image_mode=ImageRefMode.REFERENCED,
)
```

Use the equivalent arguments with `save_as_json` and `save_as_markdown`.

Before creating an HTML ZIP, inline Docling's generated CSS. The current server
uses `premailer`:

```python
from premailer import transform

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
```

Package the document and assets directory with relative ZIP entry names. The
assets-directory entry MUST be written explicitly so it exists even when empty.

## MCP client workflow

1. Call `convert_document_into_docling_document` and retain `document_key`.
2. Call `save_docling_document` with the key and desired format.
3. Read the resource URI returned by the tool.
4. Verify that the resource MIME type is `application/zip`.
5. Decode the resource blob if the SDK returns base64 text.
6. Save the decoded bytes as a `.zip` file or extract them in memory.
7. Preserve the directory structure when extracting so relative image references
   continue to work.

### Python client example

```python
import base64
from pathlib import Path

from pydantic import AnyUrl

saved = await session.call_tool(
    "save_docling_document",
    {
        "document_key": document_key,
        "output_format": "html",
    },
)

resource_uri = saved.structuredContent["resource_uri"]
resource = await session.read_resource(AnyUrl(resource_uri))
content = resource.contents[0]

if content.mimeType != "application/zip":
    raise ValueError(f"Unexpected MIME type: {content.mimeType}")

zip_bytes = base64.b64decode(content.blob)
Path("document.zip").write_bytes(zip_bytes)
```

### TypeScript client example

```typescript
const saved = await client.callTool({
  name: "save_docling_document",
  arguments: {
    document_key: documentKey,
    output_format: "html",
  },
});

const resourceUri = saved.structuredContent.resource_uri;
const resource = await client.readResource({ uri: resourceUri });
const content = resource.contents[0];

if (content.mimeType !== "application/zip" || !("blob" in content)) {
  throw new Error("Expected an application/zip blob resource");
}

const zipBytes = Buffer.from(content.blob, "base64");
await fs.promises.writeFile("document.zip", zipBytes);
```

## Compatibility changes

The following old behavior is no longer supported:

- Saving Markdown and JSON together in one tool call.
- Returning a raw JSON, HTML, or Markdown file path as the downloadable result.
- Separate text resources for `/json`, `/html`, and `/markdown`.
- HTML or JSON exports containing base64 image data.

Clients MUST use the ZIP resource template and treat its response as binary.

## Acceptance criteria

For each supported output format:

- The tool accepts the format and returns a `.zip` path.
- `resource_uri` matches the documented URI template.
- Reading the resource returns `application/zip` and valid ZIP bytes.
- ZIP CRC validation succeeds.
- The ZIP contains the requested document file.
- The ZIP contains the format-specific assets directory.
- Every exported image reference is relative.
- Every referenced image exists in the ZIP.
- No exported document contains a `data:image/...;base64,...` value.
- No exported document contains the server cache's absolute path.
- HTML contains inline `style` attributes.
- HTML contains no `<style>` element and no dependency on CSS classes.

