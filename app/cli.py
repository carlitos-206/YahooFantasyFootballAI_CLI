# app/cli.py
import sys
import typer
from rich.prompt import Prompt
from typing import Optional
import shlex
from app.config import load_settings
from app.yahoo_client import YahooClient
from app.repo import Repo
from app.scheduler import start_scheduler
from app.brains.rules import suggest_lineup, suggest_waivers
from app.brains.draft import suggest_pick
from app.ui import (
    banner, print_info, print_success, print_warn, print_error,
    yahoo_error_to_str, kv_table, simple_table, console
)

app = typer.Typer(help="Fantasy AI CLI")


def _print_commands():
    console.print(
        "Commands: "
        "[bold]available[/], "  # <-- add
        "[bold]lineup[/], [bold]waivers[/], [bold]draft[/], "
        "[bold]ping[/], [bold]help[/], [bold]quit[/]"
    )

def _available_usage():
    console.print(
        "[bold]available[/] — list free agents + waivers\n"
        "  Options:\n"
        "    --pos QB|RB|WR|TE|DEF|K    filter by position\n"
        "    --search TEXT               name substring\n"
        "    --sort AR|POWN|NAME         sort (default AR)\n"
        "    --limit N                   max rows (e.g. 30)\n"
        "    --no-waivers                exclude players on waivers\n"
        "    --jsonl                     output JSON lines\n"
        "\nExamples:\n"
        "  available\n"
        "  available --pos RB --limit 30\n"
        "  available --search smith --sort POWN\n"
    )
def _handle_available(y, argv: str):
    """
    Parse and execute: available [--pos POS] [--search TEXT] [--sort AR|POWN|NAME] [--limit N] [--no-waivers] [--jsonl]
    """
    # Tokenize the rest of the line after 'available'
    tokens = shlex.split(argv)
    pos = None
    search = None
    sort = "AR"
    limit = None
    include_waivers = True
    jsonl = False

    i = 0
    while i < len(tokens):
        t = tokens[i]
        # flags with value
        if t in ("--pos", "-p"):
            i += 1; pos = tokens[i] if i < len(tokens) else None
        elif t.startswith("--pos="):
            pos = t.split("=", 1)[1]
        elif t == "--search":
            i += 1; search = tokens[i] if i < len(tokens) else None
        elif t.startswith("--search="):
            search = t.split("=", 1)[1]
        elif t == "--sort":
            i += 1; sort = (tokens[i] if i < len(tokens) else sort).upper()
        elif t.startswith("--sort="):
            sort = t.split("=", 1)[1].upper()
        elif t == "--limit":
            i += 1
            try:
                limit = int(tokens[i]) if i < len(tokens) else None
            except Exception:
                limit = None
        # boolean flags
        elif t == "--no-waivers":
            include_waivers = False
        elif t == "--jsonl":
            jsonl = True
        # help
        elif t in ("-h", "--help"):
            _available_usage()
            return
        else:
            # allow shorthand like: available RB
            if pos is None and t.upper() in ("QB","RB","WR","TE","DEF","K"):
                pos = t.upper()
            else:
                console.print(f"[yellow]Warning:[/yellow] ignoring unknown option '{t}'")
        i += 1

    try:
        rows = []
        for p in y.available_players(
            position=pos,
            include_waivers=include_waivers,
            search=search,
            sort=sort,
            limit=limit,
        ):
            rows.append({
                "Player": p["name"],
                "Pos": p["pos"],
                "Elig": ",".join(p["elig"] or []),
                "Team": p["team"],
                "Bye": p["bye"],
                "%Own": p["%owned"],
                "Stat": p["stat"],
                "Inj": (p["inj"] or "")[:20] if p.get("inj") else "",
                "Avail": p.get("avail", "FA"),
                "ID": p["player_id"],
            })

        if jsonl:
            for r in rows:
                console.print_json(data=r)
        else:
            if not rows:
                print_warn("No available players found with the given filters.")
            else:
                cols = ["Player", "Pos", "Elig", "Team", "Bye", "%Own", "Stat", "Inj", "Avail", "ID"]
                console.print(simple_table("Available Players", cols, rows))
                print_success(
                    f"Shown: {len(rows)} "
                    f"(pos={pos or 'ANY'}, sort={sort}, waivers={'on' if include_waivers else 'off'})"
                )
    except Exception as e:
        print_error(f"Available error:\n{yahoo_error_to_str(e)}")


@app.command("run")
def run_command():
    """
    Start the Fantasy AI interactive coach with the hourly Yahoo poller.
    """
    cfg = load_settings()

    # Boot Yahoo + DB + scheduler
    try:
        y = YahooClient(cfg.league_id)
    except Exception as e:
        print_error(f"Failed to initialize Yahoo client:\n{yahoo_error_to_str(e)}")
        raise typer.Exit(code=1)

    try:
        repo = Repo(cfg.db_path)
    except Exception as e:
        print_error(f"Failed to open DB:\n{e}")
        raise typer.Exit(code=1)

    try:
        start_scheduler(y, repo, cfg.poll_interval_min)
        print_info(f"Scheduler running every {cfg.poll_interval_min} min.")
    except Exception as e:
        print_warn(f"Scheduler warning: {e}")

    banner("Fantasy AI Coach")
    console.print("Type natural language or a command.")
    _print_commands()

    # Simple REPL
    while True:
        try:
            q = Prompt.ask("[bold cyan]›[/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            break

        if not q:
            continue

        low = q.lower()

        if low in ("quit", "exit", "q"):
            console.print("[dim]Exiting…[/]")
            break

        if low in ("help", "?"):
            _print_commands()
            continue
        if low.startswith("available"):
            # pass the raw text (minus the command keyword) to the handler
            after = q[len("available"):].strip()
            _handle_available(y, after)
            continue

        if low in ("ping", "health", "check"):
            # Health check with friendly output
            try:
                teams = y.teams()
                settings = y.settings()
                rows = {
                    "League": cfg.league_id,
                    "Teams": len(teams),
                    "Scoring": settings.get("scoring_type", "?"),
                }
                console.print(kv_table("Yahoo Health", rows))
                print_success("Yahoo API reachable.")
            except Exception as e:
                print_error(yahoo_error_to_str(e))
            continue

        if low.startswith("lineup"):
            # TODO: build real features from repo+yahoo
            features = []  # placeholder
            slots = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1}
            try:
                sug = suggest_lineup(features, slots)
                if not sug:
                    print_warn("No lineup suggestions yet (features empty).")
                else:
                    cols = ["player_id", "slot", "score"]
                    console.print(simple_table("Lineup Suggestions", cols, sug))
            except Exception as e:
                print_error(f"Lineup error:\n{yahoo_error_to_str(e)}")
            continue

        if low.startswith("waivers"):
            # TODO: pull free agents and build features
            fa_feats = []  # placeholder
            try:
                sug = suggest_waivers(fa_feats)
                if not sug:
                    print_warn("No waiver suggestions yet (features empty).")
                else:
                    cols = list(sug[0].keys())
                    console.print(simple_table("Top Waiver Targets", cols, sug))
            except Exception as e:
                print_error(f"Waivers error:\n{yahoo_error_to_str(e)}")
            continue

        if low.startswith("draft"):
            # TODO: detect live draft + available pool + needs
            available, needs, picks_until_next = [], {}, 0
            try:
                top = suggest_pick(available, needs, picks_until_next)
                if not top:
                    print_warn("No draft suggestions yet (empty pool).")
                else:
                    cols = list(top[0].keys())
                    console.print(simple_table("Draft Picks (Top 5)", cols, top))
            except Exception as e:
                print_error(f"Draft error:\n{yahoo_error_to_str(e)}")
            continue

        # Basic intent hints
        if "who should i start" in low:
            console.print("Try [bold]lineup[/] to see ranked starters and FLEX.")
        elif "who do i draft" in low or "on the clock" in low:
            console.print("Try [bold]draft[/] to see on-the-clock suggestions.")
        else:
            _print_commands()


@app.command("ping")
def ping():
    """
    Quick connectivity test to Yahoo Fantasy API (non-REPL).
    """
    cfg = load_settings()
    try:
        y = YahooClient(cfg.league_id)
        teams = y.teams()
        settings = y.settings()
        rows = {
            "League": cfg.league_id,
            "Teams": len(teams),
            "Scoring": settings.get("scoring_type", "?"),
        }
        console.print(kv_table("Yahoo Health", rows))
        print_success("Yahoo API reachable.")
    except Exception as e:
        print_error(yahoo_error_to_str(e))
        raise typer.Exit(code=1)

@app.command("available")
def available_command(
    pos: Optional[str] = typer.Option(None, "--pos", help="Filter by position (QB,RB,WR,TE,DEF,K)"),
    search: Optional[str] = typer.Option(None, "--search", help="Substring on player name"),
    sort: str = typer.Option("AR", "--sort", help="Yahoo sort: AR, OR, PTS, etc.", show_default=True),
    page_size: int = typer.Option(25, "--page-size", min=1, max=25, show_default=True),
    pages: int = typer.Option(2, "--pages", min=1, show_default=True),
    jsonl: bool = typer.Option(False, "--jsonl", help="Emit newline-delimited JSON instead of a table"),
):
    """
    List available players (Free Agents + Waivers) for the current league.
    """
    cfg = load_settings()
    try:
        y = YahooClient(cfg.league_id)
    except Exception as e:
        print_error(f"Yahoo init failed:\n{yahoo_error_to_str(e)}")
        raise typer.Exit(code=1)

    try:
        rows = []
        for p in y.available_players(
            status=("FA", "W"),
            position=pos,
            search=search,
            sort=sort,
            count=page_size,
            max_pages=pages,
            include_stats=False,
        ):
            rows.append({
                "Player": p["name"],
                "Pos": p["pos"],
                "Elig": ",".join(p["elig"] or []),
                "Team": p["team"],
                "Bye": p["bye"],
                "%Own": p["%owned"],
                "Stat": p["stat"],   # Q/O/IR, etc.
                "Inj": (p["inj"] or "")[:20] if p.get("inj") else "",
                "ID": p["player_id"],
            })

        if jsonl:
            for r in rows:
                console.print_json(data=r)  # pretty JSON lines
        else:
            if not rows:
                print_warn("No available players found with the given filters.")
            else:
                cols = ["Player", "Pos", "Elig", "Team", "Bye", "%Own", "Stat", "Inj", "ID"]
                console.print(simple_table("Available Players", cols, rows))
                print_success(f"Shown: {len(rows)} (pos={pos or 'ANY'}, sort={sort})")

    except Exception as e:
        print_error(f"Fetch error:\n{yahoo_error_to_str(e)}")
        raise typer.Exit(code=1)

def main():
    # Show help when no subcommand provided
    if len(sys.argv) == 1:
        with console.capture() as cap:
            app("--help")
        console.print(cap.get())
        raise typer.Exit(code=0)
    app()


if __name__ == "__main__":
    main()
