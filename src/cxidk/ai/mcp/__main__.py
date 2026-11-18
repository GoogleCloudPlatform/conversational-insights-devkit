# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""CLI entrypoint for `cxidk` / `cxidk-mcp` (stdio and Streamable HTTP transports)."""

import argparse
import importlib
import logging
import sys
from typing import List, Optional

import cxidk
from cxidk.ai import policy as ai_policy


def configure_stderr_logging(level: int = logging.INFO) -> None:
    """Configures logging exclusively on `sys.stderr` to protect stdio JSON-RPC.

    Args:
        level: Standard `logging` severity threshold.
    """
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def build_arg_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser for `cxidk` / `cxidk-mcp`.

    Returns:
        Configured `argparse.ArgumentParser` instance.
    """
    parser = argparse.ArgumentParser(
        prog="cxidk-mcp",
        description="Conversational Insights DevKit (cxidk) MCP Server & AI Discovery CLI.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="MCP transport protocol ('stdio' default, or 'http' for Streamable HTTP).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host for HTTP transport (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Bind port for HTTP transport (default: 8080).",
    )
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        default=None,
        help="Enable guarded write tools (`writes` toolset).",
    )
    parser.add_argument(
        "--toolsets",
        default=None,
        help="Comma-separated toolsets to expose (e.g., 'core,transcripts,writes').",
    )
    parser.add_argument(
        "--print-llms-txt",
        action="store_true",
        default=False,
        help="Print the bundled `llms.txt` Markdown API & tool index and exit.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Runs the `cxidk-mcp` server over stdio/HTTP or prints `llms.txt`.

    Args:
        argv: Optional list of CLI arguments (defaults to `sys.argv[1:]`).

    Returns:
        Process exit code (`0` on clean shutdown, `2` if `[mcp]` extras are missing).
    """
    configure_stderr_logging()
    args = build_arg_parser().parse_args(argv)

    if args.print_llms_txt:
        sys.stdout.write(cxidk.get_llms_txt())
        return 0

    try:
        mcp_server = importlib.import_module("cxidk.ai.mcp.server")
    except ModuleNotFoundError as exc:
        sys.stderr.write(
            f"Missing optional MCP dependency ({exc.name}). "
            'Install via `pip install "cxidk[mcp]"` or run '
            '`uvx --from "cxidk[mcp]" cxidk-mcp`.\n'
        )
        return 2

    toolsets_override = ai_policy.parse_csv(args.toolsets) or None
    policy = ai_policy.Policy.from_env(
        transport=args.transport,
        allow_writes=True if args.allow_writes else None,
        toolsets=toolsets_override,
    )

    if args.transport == "stdio":
        srv = mcp_server.build_server(policy=policy)
        srv.run(transport="stdio")
        return 0

    try:
        http_app = importlib.import_module("cxidk.ai.mcp.http_app")
        uvicorn = importlib.import_module("uvicorn")
    except ModuleNotFoundError as exc:
        sys.stderr.write(
            f"Missing optional HTTP dependency ({exc.name}). "
            'Install via `pip install "cxidk[mcp]"`.\n'
        )
        return 2

    app = http_app.build_http_app(policy=policy, host=args.host)
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_config=None,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
