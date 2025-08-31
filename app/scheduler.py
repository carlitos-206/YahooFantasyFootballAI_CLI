# app/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import json
from app.ui import console, print_success, print_error, yahoo_error_to_str

def start_scheduler(y, repo, poll_min: int):
    sch = BackgroundScheduler()

    @sch.scheduled_job(
        "interval",
        minutes=poll_min,
        next_run_time=datetime.now() + timedelta(seconds=10),
    )
    def hourly_fetch():
        try:
            st = y.standings()
            print_success(f"[every_min_fetch] Standings OK — {len(st)} teams")
        except Exception as e:
            # Try to parse Yahoo JSON error nicely
            msg = str(e).strip()
            try:
                if msg.startswith("b'") and msg.endswith("'"):
                    msg = msg[2:-1]  # strip b'...'
                parsed = json.loads(msg)
                err = parsed.get("error", {})
                desc = err.get("description", "Yahoo API error")
                uri = err.get("yahoo:uri") or err.get("uri")
                detail = err.get("detail")
                parts = [f"[bold red]{desc}[/]"]
                if uri:
                    parts.append(f"Endpoint: [cyan]{uri}[/]")
                if detail:
                    parts.append(f"Detail: {detail}")
                console.print(f"[every_min_fetch] ", *parts)
            except Exception:
                # fallback to our general cleaner
                print_error(f"[every_min_fetch] {yahoo_error_to_str(e)}")

    sch.start()
    return sch
