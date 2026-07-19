# Docling MCP: making docling agentic

[![PyPI version](https://img.shields.io/pypi/v/docling-mcp)](https://pypi.org/project/docling-mcp/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/docling-mcp)](https://pypi.org/project/docling-mcp/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Pydantic v2](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pydantic/pydantic/main/docs/badge/v2.json)](https://pydantic.dev)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![License MIT](https://img.shields.io/github/license/saurabh-goyal-saurabh/docling-mcp)](https://opensource.org/licenses/MIT)

A document processing service using the Docling-MCP library and MCP (Model Context Protocol) for tool integration.


## Overview

[Docling](https://github.com/docling-project/docling) MCP is a service that provides tools for document conversion, processing and generation. It uses the Docling library to convert PDF documents into structured formats and provides a caching mechanism to improve performance. The service exposes functionality through a set of tools that can be called by client applications.

## Installation Options

### Remote Mode (Recommended - Lightweight)

For users with access to Docling Serve API:

> **Getting Docling Serve**: Visit [docling-serve](https://github.com/docling-project/docling-serve) for installation guides. You can deploy it from published container images or look for managed Docling SaaS offerings.

```bash
pip install docling-mcp
```

Then configure your environment:
```bash
export DOCLING_SERVICE_URL=https://your-docling-service.example.com
export DOCLING_SERVICE_API_KEY=your-api-key-here
export DOCLING_CONVERSION_MODE=remote
```

### Local Mode (Full Features)

For users who need local conversion or don't have Docling Serve access:

```bash
pip install docling-mcp[local]
```

Then configure your environment:
```bash
export DOCLING_CONVERSION_MODE=local
```

### Hybrid Mode (Best of Both)

Install with local support and enable automatic fallback:

```bash
pip install docling-mcp[local]
```

Configure for remote with fallback:
```bash
export DOCLING_SERVICE_URL=https://your-docling-service.example.com
export DOCLING_CONVERSION_MODE=remote
export DOCLING_FALLBACK_TO_LOCAL=true
```

## Features

- Conversion tools:
    - PDF document conversion to structured JSON format ([DoclingDocument][docling_document])
- Generation tools:
    - Document generation in DoclingDocument, which can be exported to multiple formats
- Local document caching for improved performance
- Support for local files and URLs as document sources
- Memory management for handling large documents
- Logging system for debugging and monitoring
- RAG applications with Milvus upload and retrieval

## Getting started

The easiest way to install Docling MCP and connect it to your client is by launching it via [uvx](https://docs.astral.sh/uv/).

Depending on the transfer protocol required, specify the argument `--transport`, for example

- **`stdio`** used e.g. in Claude for Desktop and LM Studio 

    ```sh
    uvx --from docling-mcp docling-mcp-server --transport stdio
    ```

- **`sse`** used e.g. in Llama Stack

    ```sh
    uvx --from docling-mcp docling-mcp-server --transport sse
    ```


- **`streamable-http`** used e.g. in containers setup

    ```sh
    uvx --from docling-mcp docling-mcp-server --transport streamable-http
    ```

More options are available, e.g. the selection of which toolgroup to launch. Use the `--help` argument to inspect all the CLI options.

For developing the MCP tools further, please refer to the [Developing](CONTRIBUTING.md#developing) section of CONTRIBUTING.md for instructions.

## Integration with MCP clients

One of the easiest ways to experiment with the tools provided by Docling MCP is to leverage an AI desktop client with MCP support.
Most of these clients use a common config interface. Adding Docling MCP in your favorite client is usually as simple as adding the following entry in the configuration file.

```json
{
  "mcpServers": {
    "docling": {
      "command": "uvx",
      "args": [
        "--from=docling-mcp",
        "docling-mcp-server"
      ]
    }
  }
} 
```

When using **[Claude for Desktop](https://claude.ai/download)**, simply edit the config file `claude_desktop_config.json` with the snippet above or the example provided [here](docs/integrations/claude_desktop_config.json).

In **[LM Studio](https://lmstudio.ai/)**, edit the `mcp.json` file with the appropriate section or simply click on the button below for a direct install.

[![Add MCP Server docling to LM Studio](https://files.lmstudio.ai/deeplink/mcp-install-light.svg)](https://lmstudio.ai/install-mcp?name=docling&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb209ZG9jbGluZy1tY3AiLCJkb2NsaW5nLW1jcC1zZXJ2ZXIiXX0%3D)

Other integrations are described in the [integrations] page.

## Examples

### Converting documents

Example of prompt for converting PDF documents:

```prompt
Convert the PDF document at <provide file-path> into DoclingDocument and return its document-key.
```

### Generating documents

Example of prompt for generating new documents:

```prompt
I want you to write a Docling document. To do this, you will create a document first by invoking `create_new_docling_document`. Next you can add a title (by invoking `add_title_to_docling_document`) and then iteratively add new section-headings and paragraphs. If you want to insert lists (or nested lists), you will first open a list (by invoking `open_list_in_docling_document`), next add the list_items (by invoking `add_listitem_to_list_in_docling_document`). After adding list-items, you must close the list (by invoking `close_list_in_docling_document`). Nested lists can be created in the same way, by opening and closing additional lists.

During the writing process, you can check what has been written already by calling the `export_docling_document_to_markdown` tool, which will return the currently written document. At the end of the writing, call `save_docling_document` with an `output_format` of `json`, `html`, or `markdown`; it always returns a ZIP path and an MCP resource URI for the archive.

The document should investigate the impact of tokenizers on the quality of LLMs.
```

## License

The Docling MCP codebase is under MIT license. For individual model usage, please refer to the model licenses found in the original packages.

[docling_document]: https://docling-project.github.io/docling/concepts/docling_document/
[integrations]: https://github.com/saurabh-goyal-saurabh/docling-mcp/tree/main/docs/integrations
