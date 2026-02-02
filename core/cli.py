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
            "  [cyan]agent factory[/]      — 🏭 Build system from idea (NEW!)\n"
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

@app.command()
def factory(
    idea: str = typer.Argument(..., help="Your project idea or system concept"),
    detail: str = typer.Option("medium", help="Detail level: low/medium/high"),
    execute: bool = typer.Option(True, help="Execute the plan immediately"),
):
    """🏭 Agent System Factory - Build systems from ideas autonomously."""
    import asyncio
    from core.factory import SystemBuilderFactory
    from core.dev_tools import register_dev_tools
    from rich.progress import Progress, SpinnerColumn, TextColumn

    console.print(Panel(
        f"[bold cyan]🏭 Agent System Factory[/]\n\n"
        f"[yellow]Idea:[/] {idea}\n"
        f"[yellow]Detail Level:[/] {detail}\n"
        f"[yellow]Auto-Execute:[/] {'Yes' if execute else 'No'}",
        title="Factory Mode",
        border_style="cyan"
    ))

    async def run_factory():
        # Register development tools
        register_dev_tools()

        # Initialize factory
        factory_instance = SystemBuilderFactory.instance()

        # Phase 1: Planning
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Creating implementation plan...", total=None)

            project = await factory_instance.create_from_idea(idea, detail)

            progress.update(task, description="[green]✓ Plan created!", completed=True)

        # Show plan summary
        console.print(f"\n[bold green]📋 Plan Summary:[/]")
        console.print(f"  • Project ID: [cyan]{project.id}[/]")
        console.print(f"  • Total Tasks: [cyan]{len(project.tasks)}[/]")
        console.print(f"  • Overview: {project.plan.get('overview', 'N/A')[:200]}...")

        if project.plan.get('tech_stack'):
            console.print(f"\n[bold]🔧 Tech Stack:[/]")
            for tech in project.plan['tech_stack'][:5]:
                console.print(f"  • {tech}")

        console.print(f"\n[bold]📝 Sample Tasks:[/]")
        for task in project.tasks[:5]:
            console.print(f"  [{task['complexity']}] {task['title']}")

        if len(project.tasks) > 5:
            console.print(f"  ... and {len(project.tasks) - 5} more tasks")

        # Phase 2: Execution
        if execute:
            console.print(f"\n[bold yellow]⚡ Starting Execution...[/]\n")

            result = await factory_instance.execute_project(project.id)

            console.print(Panel(
                f"[bold green]✨ Factory Complete![/]\n\n"
                f"[yellow]Project ID:[/] {result['project_id']}\n"
                f"[yellow]Status:[/] {result['status']}\n"
                f"[yellow]Completed:[/] {result['completed_tasks']}/{result['total_tasks']} tasks\n"
                f"[yellow]Success Rate:[/] {result['completion_rate']*100:.1f}%",
                title="🎉 Results",
                border_style="green"
            ))
        else:
            console.print(f"\n[yellow]ℹ️  Plan created but not executed (use --execute to run)[/]")
            console.print(f"   To execute later: agent factory \"{idea}\" --execute")

    asyncio.run(run_factory())

if __name__ == "__main__":
    app()
