from delegate_mcp.app.context import AppContext
from delegate_mcp.config import Settings
from delegate_mcp.entrypoints.server import create_server
from delegate_mcp.infra.antigravity import AntigravityRunner
from delegate_mcp.infra.verify import ShellVerifier


def main() -> None:
    """Read settings, wire the worker and verifier, and serve over stdio."""
    settings = Settings()
    ctx = AppContext(settings, AntigravityRunner(settings), ShellVerifier())
    create_server(ctx).run(transport="stdio")


if __name__ == "__main__":
    main()
