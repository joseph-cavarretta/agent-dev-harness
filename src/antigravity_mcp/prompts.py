PYTHON_STANDARDS = """Code standards:
- Pydantic models for interfaces, Protocols for dependency injection.
- Configuration through BaseSettings only. Never read os.environ directly.
- No lazy imports.
- Solve only what was asked. Keep the diff minimal.
- Comment only where the logic is not self-evident. Do not add docstrings to code you did not change."""

WRITING_STYLE = """Writing style:
- Plain English. Prefer the plainer word: "fill in" over "hydrate", "response shape" over
  "wire format", "slip through silently" over "fail-open".
- Keep precise technical terms that carry specific meaning (BM25, kNN, chunk_id, OOXML).
- Write for a reader who does not already know the subject. Say what a thing is and what it
  does in concrete terms.
- Replace abstractions with the actual consequence: "one edit instead of one per service",
  not "a configuration change".
- Every sentence must earn its place. Cut the ones that do not."""

NO_CUSTOMER_NAMES = (
    "Never write real customer or tenant names. Use <tenant>, <env>, or <customer> placeholders."
)

OBSIDIAN_LINKS = "Link related pages with Obsidian wiki links: [[wiki/folder/page-name]]."


def verify_loop(command: str, directory: str, max_rounds: int) -> str:
    """Instruction block telling agy to iterate against a real command until it passes."""
    return f"""Close the loop yourself. Do not hand back failing work:
1. Write the code.
2. Run this exact command from {directory}:
     {command}
3. If it fails, read the actual error, fix the cause, and run it again.
4. Repeat up to {max_rounds} times until it passes.

Rules for the loop:
- Never edit or weaken the check to make it pass. Fix the code under test.
- If the check itself is genuinely wrong, stop and say so rather than working around it.
- If you cannot get it passing, say exactly what still fails and what you tried.
- End by reporting the command's final output verbatim.

The caller re-runs this command independently, so a false claim of success will be caught."""
