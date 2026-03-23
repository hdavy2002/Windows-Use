"""
main_humphi.py

Humphi AI — Windows UI assistant.
Uses meta-llama/llama-3.3-70b-instruct:free via OpenRouter.
Scoped to Windows UI tasks only.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from humphi.subscriber import HumphiEventSubscriber, LOG_DIR
from windows_use.cli.setup import create_llm
from windows_use.agent.service import Agent
from windows_use.agent.desktop.views import Browser
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from rich.console import Console

console = Console()

STYLE = Style.from_dict({"prompt": "ansiblue bold"})
QUIT_COMMANDS = {"\\quit", "\\exit", "\\q"}

# Default model — free Llama via OpenRouter
DEFAULT_PROVIDER = "open_router"
DEFAULT_MODEL    = "meta-llama/llama-3.3-70b-instruct:free"

# Tasks we accept — Windows UI only
ALLOWED_KEYWORDS = {
    "find", "open", "show", "where", "locate", "search",
    "settings", "wifi", "bluetooth", "display", "sound", "network",
    "uninstall", "install", "program", "app", "application",
    "folder", "file", "desktop", "taskbar", "start menu",
    "control panel", "device", "printer", "disk", "storage",
    "update", "restart", "shutdown", "sleep", "lock",
    "wallpaper", "theme", "brightness", "volume", "battery",
    "firewall", "vpn", "proxy", "dns", "ip address",
    "startup", "task manager", "processes", "memory", "cpu",
    "clipboard", "screenshot", "snipping",
}

# Tasks we reject — out of scope
BLOCKED_KEYWORDS = {
    "email", "gmail", "outlook", "send mail", "read mail",
    "chrome", "firefox", "edge", "browser", "website", "google",
    "type this", "fill in", "submit form", "login to",
    "whatsapp", "facebook", "instagram", "twitter",
    "youtube", "netflix", "spotify",
}


def _is_windows_ui_task(task: str) -> tuple[bool, str]:
    """
    Check if task is within Windows UI scope.
    Returns (allowed, reason_if_blocked)
    """
    task_lower = task.lower()

    # Check blocked keywords first
    for kw in BLOCKED_KEYWORDS:
        if kw in task_lower:
            return False, f"'{kw}' tasks are handled by app integrations, not Windows UI."

    return True, ""


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Humphi AI — Windows UI Assistant")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--mode", default="normal", choices=["normal", "flash"])
    parser.add_argument("--max-steps", type=int, default=15)
    args = parser.parse_args()

    # Create LLM
    try:
        llm = create_llm(args.provider, args.model)
    except Exception as e:
        console.print(f"[red]Failed to create LLM: {e}[/red]")
        console.print("[yellow]Set key: $env:OPENROUTER_API_KEY='your_key'[/yellow]")
        sys.exit(1)

    subscriber = HumphiEventSubscriber()

    agent = Agent(
        llm=llm,
        mode=args.mode,
        max_steps=args.max_steps,
        use_accessibility=True,
        use_vision=False,
        event_subscriber=subscriber,
        log_to_console=True,
    )

    console.print(f"\n[bold blue]Humphi AI[/bold blue] — Windows Assistant")
    console.print(f"[dim]Model: {args.model}[/dim]")
    console.print(f"[dim]Logs:  {LOG_DIR}[/dim]")
    console.print(f"[dim]Monitor: humphi/monitor.html[/dim]")
    console.print(f"\n[dim]What I can do:[/dim]")
    console.print(f"[dim]  • Find files and folders[/dim]")
    console.print(f"[dim]  • Open Windows Settings[/dim]")
    console.print(f"[dim]  • Launch or uninstall programs[/dim]")
    console.print(f"[dim]  • Show system info[/dim]")
    console.print(f"[dim]Type \\quit to exit[/dim]\n")

    session = PromptSession(style=STYLE)

    while True:
        try:
            task = session.prompt([("class:prompt", "Humphi > ")]).strip()

            if not task:
                continue
            if task.lower() in QUIT_COMMANDS:
                console.print("[dim]Goodbye.[/dim]")
                break

            # Scope check
            allowed, reason = _is_windows_ui_task(task)
            if not allowed:
                console.print(f"[yellow]Out of scope: {reason}[/yellow]")
                console.print("[dim]App integrations like Gmail, WhatsApp etc coming soon.[/dim]\n")
                continue

            subscriber.set_task(task)
            result = agent.invoke(task=task)

            if result and result.error:
                console.print(f"[red]Error: {result.error}[/red]")

        except KeyboardInterrupt:
            console.print("\n[dim]Use \\quit to exit.[/dim]")
            continue
        except EOFError:
            break


if __name__ == "__main__":
    main()
