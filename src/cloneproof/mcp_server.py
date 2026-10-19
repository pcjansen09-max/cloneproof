"""MCP server (stdio): lets any MCP-capable agent call cloneproof as a tool.

Install with `pip install "cloneproof[mcp]"`, then add to your agent:
    claude mcp add cloneproof -- cloneproof mcp
"""

from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    try:
        try:
            from mcp.server.mcpserver import MCPServer as FastMCP      # mcp 2.x
        except ImportError:
            from mcp.server.fastmcp import FastMCP                      # mcp 1.x
    except ImportError:
        print('install the MCP extra: pip install "cloneproof[mcp]"')
        return 1

    from .compare import compare
    from .prompt import build_prompt
    from .report import write_all
    from .serve import serve

    mcp = FastMCP("cloneproof")

    @mcp.tool()
    def compare_sites(reference: str, clone: str, quick: bool = True, target: float = 97.0,
                      out_dir: str = ".cloneproof/latest") -> str:
        """Measure a clone against the original. `reference`/`clone` are URLs or folders of static files.
        Returns the score, per-viewport scores and the list of differences (biggest first), plus
        the path of the prompt/report/images. Call again after fixing the source until score >= target."""
        servers = []

        def resolve(t: str) -> str:
            p = Path(t).expanduser()
            if "://" not in t and p.is_dir():
                srv, port = serve(p)
                servers.append(srv)
                return f"http://127.0.0.1:{port}/"
            return t if "://" in t else "https://" + t
        try:
            res = compare(resolve(reference), resolve(clone), out_dir,
                          viewports=("desktop",) if quick else ("desktop", "tablet", "mobile"),
                          noise=not quick)
            write_all(res, build_prompt(res, target=target))
            data = res.to_dict(max_issues=25)
            data["prompt_file"] = str(Path(out_dir) / "report.md")
            return json.dumps(data, indent=2, ensure_ascii=False)
        finally:
            for s in servers:
                s.shutdown()

    mcp.run()
    return 0
