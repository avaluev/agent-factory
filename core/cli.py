"""Agent Platform CLI — Main entry point."""
import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(name="agent-platform", help="AI Agent Platform CLI")
console = Console()

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Agent Platform — Self-developing AI agent system."""
    if ctx.invoked_subcommand is None:
        console.print(Panel(
            "[bold green]Agent Platform v0.1.0[/]\n\n"
            "Commands:\n"
            "  [cyan]agent run[/]          — Start interactive agent session\n"
            "  [cyan]agent ingest[/]       — Ingest documents into RAG\n"
            "  [cyan]agent skills[/]       — List/manage agent skills\n"
            "  [cyan]agent workflow[/]     — Run/define workflows\n"
            "  [cyan]agent status[/]       — Show system status\n",
            title="Welcome",
            border_style="green"
        ))

@app.command()
def status():
    """Show system status — model availability, RAG state, memory stats."""
    console.print("[bold]Checking system status...[/]")
    # Implementation in Prompt 2
    console.print("[green]✓ Status check complete[/]")

@app.command()
def run(
    input_file: str = typer.Option(None, help="Input file (md/txt/csv) to process"),
    interactive: bool = typer.Option(True, help="Interactive mode"),
):
    """Start an agent session."""
    console.print("[bold green]Starting agent session...[/]")
    # Implementation in Prompt 2
    
@app.command()
def ingest(path: str = typer.Argument(..., help="Path to file or directory to ingest")):
    """Ingest documents into the RAG knowledge base."""
    console.print(f"[bold]Ingesting: {path}[/]")
    # Implementation in Prompt 3

@app.command()
def skills():
    """List available agent skills."""
    console.print("[bold]Available Skills:[/]")
    # Implementation in Prompt 5

if __name__ == "__main__":
    app()
