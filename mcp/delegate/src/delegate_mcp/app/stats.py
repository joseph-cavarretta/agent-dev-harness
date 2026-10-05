from delegate_mcp.app.context import AppContext
from delegate_mcp.core.stats import summarize
from delegate_mcp.infra.delegation_log import read_delegation_log


def delegation_stats(ctx: AppContext, limit: int) -> str:
    """Summarize the delegation log, or say why there is nothing to summarize."""
    log_path = ctx.settings.log_path
    if not log_path.exists():
        return f"No delegation log yet at {log_path}."
    entries = read_delegation_log(log_path)
    if not entries:
        return f"Delegation log at {log_path} has no readable entries."
    return summarize(entries, limit, log_path)
