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


def verify_command_line(command: str, directory: str) -> str:
    """The literal shell line agy must run, cd included.

    agy's shell tool always starts in its own scratch directory, whatever working directory
    the process was launched from. Without an explicit cd it runs somewhere else entirely and
    then reports output it never obtained.
    """
    return f"cd {directory} && {command}"


def verify_loop(command: str, directory: str, max_rounds: int) -> str:
    """Instruction block telling agy to check its own work against a real command."""
    return f"""Check your work before handing it back:
1. Write the code.
2. Run this exact shell command, including the cd — your shell does not start in the right
   directory, so dropping the cd silently checks the wrong thing:
     {verify_command_line(command, directory)}
3. If it fails, read the actual error, fix the cause, and run it again.
4. Repeat up to {max_rounds} times until it passes.

Rules:
- Never edit or weaken the check to make it pass. Fix the code under test.
- If the check itself is genuinely wrong, stop and say so rather than working around it.
- Report only output you actually saw. Do not describe a passing run you did not observe.
- If you cannot get it passing, say exactly what still fails and what you tried.

The caller runs this command itself and drives the retries, so a false claim of success is
caught immediately."""


def verify_retry(command: str, directory: str, attempt: int, output: str) -> str:
    """Feed a real, observed failure back into a warm conversation."""
    return f"""The check still fails. This is the real output, captured by the caller running
the command itself (attempt {attempt}):

$ {verify_command_line(command, directory)}
{output}

Fix the underlying cause and run the command again yourself to confirm. Do not weaken the
check. If this output shows the check itself is wrong rather than the code, say so plainly
instead of working around it."""
