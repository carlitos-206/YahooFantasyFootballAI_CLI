# app/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import json
import random

from app.ui import console, print_success, print_error, print_info, yahoo_error_to_str


def start_scheduler(y, repo, poll_min: int):
    # Coalesce & single instance so bursts don’t stack if Yahoo is slow
    sch = BackgroundScheduler(job_defaults={"coalesce": True, "max_instances": 1})

    # jitter first run a bit so we don't always hit at the top of the minute
    first_run = datetime.now() + timedelta(seconds=10 + int(random.uniform(0, 8)))

    # transient failure tracker in closure
    fail_state = {"count": 0, "muted": False}

    @sch.scheduled_job(
        "interval",
        minutes=poll_min,
        next_run_time=first_run,
        id="every_min_fetch",
    )
    def every_min_fetch():
        try:
            st = y.standings()   # light touch endpoint
            fail_state["count"] = 0
            if fail_state["muted"]:
                print_info("[every_min_fetch] Yahoo recovered; resuming normal cadence.")
                fail_state["muted"] = False
                # restore normal cadence if we previously backed off
                sch.reschedule_job("every_min_fetch", trigger=IntervalTrigger(minutes=poll_min))
            print_success(f"[every_min_fetch] Standings OK — {len(st)} teams")
        except Exception as e:
            fail_state["count"] += 1
            # After first warning, go quiet unless it keeps failing
            if fail_state["count"] == 1:
                print_error(f"[every_min_fetch] {yahoo_error_to_str(e)}")
            elif fail_state["count"] in (5, 10):
                print_error(f"[every_min_fetch] still failing (x{fail_state['count']}): {yahoo_error_to_str(e)}")

            # If flaking repeatedly, back off to 15 min until it recovers
            if fail_state["count"] >= 3 and not fail_state["muted"]:
                sch.reschedule_job("every_min_fetch", trigger=IntervalTrigger(minutes=15))
                print_info("[every_min_fetch] backing off to every 15 min due to Yahoo transient errors…")
                fail_state["muted"] = True

    # Optional: light draft check (kept minimal; you can delete if you prefer)
    @sch.scheduled_job(
        "interval",
        minutes=15,
        next_run_time=datetime.now() + timedelta(seconds=12 + int(random.uniform(0, 8))))
    def draft_check():
        try:
            status = y.get_draft_status()
            # keep it quiet unless live
            if (status.get("draft_status") or "").lower() == "inprogress":
                print_success("🚨 Your draft is LIVE! 🚨")
        except Exception as e:
            # quiet by default; uncomment if you want visibility:
            # print_error(f"[draft_check] {yahoo_error_to_str(e)}")
            pass

    sch.start()
    return sch
