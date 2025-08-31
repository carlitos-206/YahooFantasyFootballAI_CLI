# app/ui.py
from typing import Any, Dict, Optional
import json
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

def banner(title: str):
    console.rule(f"[bold green]{title}[/]")

def print_info(msg: str):
    console.print(f"[cyan]ℹ[/] {msg}")

def print_success(msg: str):
    console.print(f"[green]✔[/] {msg}")

def print_warn(msg: str):
    console.print(f"[yellow]⚠[/] {msg}")

def print_error(msg: str):
    console.print(Panel.fit(Text(msg, style="bold red"), title="Error", border_style="red"))

def yahoo_error_to_str(err: Exception) -> str:
    """
    Normalize yahoo_fantasy_api/yahoo_oauth error payloads (bytes/JSON) to a short message.
    Prefer the 'description' and show the endpoint if present.
    """
    s = str(err).strip()
    if s.startswith("b'") and s.endswith("'"):
        s = s[2:-1]
    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and "error" in obj and isinstance(obj["error"], dict):
            e = obj["error"]
            desc = e.get("description") or e.get("message") or "Yahoo API error"
            uri = e.get("yahoo:uri") or e.get("uri")
            if uri:
                return f"{desc}\nEndpoint: {uri}"
            return desc
        # Fallback: compact JSON
        return json.dumps(obj, separators=(",", ":"))
    except Exception:
        return s


def kv_table(title: str, rows: Dict[str, Any]) -> Table:
    t = Table(title=title, show_lines=False, header_style="bold magenta")
    t.add_column("Key", style="cyan", no_wrap=True)
    t.add_column("Value", style="white")
    for k, v in rows.items():
        t.add_row(str(k), str(v))
    return t

def simple_table(title: str, columns, data):
    t = Table(title=title, show_lines=False, header_style="bold magenta")
    for c in columns:
        t.add_column(c)
    for row in data:
        t.add_row(*[str(row.get(c, "")) for c in columns])
    return t
