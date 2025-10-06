"""
Main entry point for the travel planning system.
Provides CLI interface and coordinates the entire application.
"""

import asyncio
import click
from typing import Optional
from config import setup_langwatch
from orchestrator import run_orchestrator


def main():
    """Initialize the application and setup LangWatch."""
    setup_langwatch()


@click.command()
@click.argument("request_args", nargs=-1)
@click.option("--request", "request_opt", help="Travel request string")
def main_cli(request_args: tuple, request_opt: Optional[str]) -> None:
    """CLI entrypoint: pass travel request as positional args or --request option."""
    user_request_text = request_opt or " ".join(request_args).strip()
    if not user_request_text:
        user_request_text = click.prompt("Please enter your travel request (or type 'exit' to quit)")
    
    asyncio.run(run_orchestrator(user_request_text))


if __name__ == "__main__":
    main()
    main_cli()
