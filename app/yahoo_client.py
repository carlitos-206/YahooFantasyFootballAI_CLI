# app/yahoo_client.py
import time
import json
import random
from typing import Callable, Any, Iterable, List, Dict, Optional, Tuple
from yahoo_oauth import OAuth2
from yahoo_fantasy_api import league as yf_league


# ---- Small, readable error type (optional) -----------------------------------
class YahooClientError(RuntimeError):
    def __init__(self, message: str, *, uri: Optional[str] = None, detail: Optional[str] = None):
        self.uri = uri
        self.detail = detail
        super().__init__(message)


def _decode_err_text(e: Exception) -> str:
    """Best-effort to turn Yahoo errors (incl. bytes) into plain text."""
    msg = str(e)
    if msg.startswith("b'") and msg.endswith("'"):
        try:
            msg = bytes(msg[2:-1], "utf-8").decode("unicode_escape")
        except Exception:
            msg = msg[2:-1]
    return msg


def _parse_yahoo_error(e: Exception) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Try to parse Yahoo JSON error for nicer messages.
    Returns (description, uri, detail)
    """
    msg = _decode_err_text(e).strip()
    try:
        parsed = json.loads(msg)
        err = parsed.get("error", {})
        desc = err.get("description") or "Yahoo API error"
        uri = err.get("yahoo:uri") or err.get("uri")
        detail = err.get("detail")
        return desc, uri, detail
    except Exception:
        return msg, None, None


def _looks_temporary(err_text: str) -> bool:
    t = err_text.lower()
    return (
        "temporary problem" in t
        or "please try again shortly" in t
        or "throttle" in t
        or "rate limit" in t
        or "999" in t
        or "unavailable" in t
        or "timeout" in t
    )


class YahooClient:
    def __init__(self, league_id: str, oauth_file: str = "data/yahoo_oauth.json"):
        self.oauth = OAuth2(None, None, from_file=oauth_file)
        try:
            # Some setups don’t expose .session; guard it.
            sess = getattr(self.oauth, "session", None)
            if sess and hasattr(sess, "headers"):
                sess.headers.setdefault(
                    "User-Agent",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
        except Exception:
            pass

        # First run: no tokens yet → interactive login
        if not getattr(self.oauth, "access_token", None):
            self.oauth.get_access_token()

        # Refresh if needed
        if not self.oauth.token_is_valid():
            self.oauth.refresh_access_token()

        self.league_id = league_id
        self._league = None

    def league(self):
        if self._league is None:
            self._league = yf_league.League(self.oauth, self.league_id)
        return self._league

    # --- Retry helper (longer & smarter for Yahoo temp faults) -----------------
    def _retry(self, fn: Callable[[], Any], *, tries=6, base_sleep=0.6, max_sleep=8.0) -> Any:
        """
        Retries on intermittent Yahoo faults (999/500/"temporary problem...").
        - Exponential backoff + jitter
        - Fast-fails on clear auth problems
        """
        last_err = None
        for i in range(tries):
            try:
                return fn()
            except Exception as e:
                last_err = e
                msg = _decode_err_text(e)

                # Fast-fail on clear auth issues
                if any(s in msg for s in ("401", "invalid_grant", "Not authorized")):
                    raise

                # Decide sleep
                sleep = min(base_sleep * (2 ** i), max_sleep)
                # Add jitter (±30%)
                jitter = random.uniform(0.7, 1.3)
                sleep *= jitter

                # If it doesn't look temporary and we're near the end, stop early
                if i >= 2 and not _looks_temporary(msg) and i >= tries - 2:
                    break

                time.sleep(sleep)

        # Out of retries — re-raise with a cleaner message if possible
        desc, uri, detail = _parse_yahoo_error(last_err or Exception("Unknown error"))
        raise YahooClientError(desc, uri=uri, detail=detail)

    # --- Draft status (single fetch + retry) -----------------------------------
    def get_draft_status(self):
        s = self.settings()
        return {"draft_status": s.get("draft_status"), "draft_time": s.get("draft_time")}


    # --- League wrappers --------------------------------------------------------
    def standings(self):
        return self._retry(lambda: self.league().standings())

    def settings(self, ttl_sec: int = 180):
        now = time.time()
        # serve cached during predraft windows to avoid hammering
        if self._settings_cache["data"] and (now - self._settings_cache["ts"] < ttl_sec):
            return self._settings_cache["data"]

        data = self._retry(lambda: self.league().settings())
        # cache only if predraft to be safe
        if (data or {}).get("draft_status", "").lower() == "predraft":
            self._settings_cache = {"ts": now, "data": data}
        else:
            # don’t cache during inprogress/postdraft
            self._settings_cache = {"ts": 0, "data": None}
        return data

    def teams(self):
        return self._retry(lambda: self.league().teams())

    def matchups(self, week: int):
        return self._retry(lambda: self.league().matchups(week))

    def waiver_wire(self):
        # Note: yahoo_fantasy_api uses `waivers()` on League
        return self._retry(lambda: self.league().waivers())

    def free_agents(self, pos: str):
        return self._retry(lambda: self.league().free_agents(pos))

    def players(self, **kw):
        return self._retry(lambda: self.league().players(**kw))

    def draft_results(self):
        return self._retry(lambda: self.league().draft_results())

    def transactions(self):
        return self._retry(lambda: self.league().transactions())

    # ---------- Unified available pool (FA + Waivers) --------------------------
    def available_players(
        self,
        position: Optional[str] = None,
        *,
        include_waivers: bool = True,
        search: Optional[str] = None,
        sort: str = "AR",               # local sort: AR (approx "added recently"), POWN, NAME
        limit: Optional[int] = None,
    ) -> Iterable[dict]:
        """
        Yield normalized available players for the league.

        Combines Yahoo Free Agents (via `free_agents(pos)`) and Waivers (via `waivers()`).
        Since yahoo_fantasy_api doesn't expose the raw V2 filter endpoint directly,
        we merge results client-side and apply optional search/sort/limit here.

        Args:
            position: Optional Yahoo position filter (QB,RB,WR,TE,DEF,K). If None, all core positions.
            include_waivers: Include players currently on waivers as 'available'.
            search: Case-insensitive substring on player full name.
            sort: One of:
                  - "AR"   : pseudo "added recently" (approx by percent-owned asc, then name)
                  - "POWN" : percent owned desc
                  - "NAME" : alphabetical by last, then first
            limit: Max number of rows yielded after sorting/filtering.
        """
        positions = [position] if position else ["QB", "RB", "WR", "TE", "DEF", "K"]

        # Collect Free Agents by position
        pool: List[dict] = []
        for idx, pos in enumerate(positions):
            try:
                fa = self.free_agents(pos) or []
            except YahooClientError as e:
                # If we see a temp fault on one position, short cool-down and continue others
                if _looks_temporary(str(e)):
                    time.sleep(0.5 + random.random() * 0.5)
                    fa = []
                else:
                    # Re-raise non-temporary errors
                    raise
            for item in _coerce_player_dicts(fa):
                item["_availability"] = "FA"
                pool.append(item)

            # Gentle pacing between calls to avoid bursty throttling
            if idx < len(positions) - 1:
                time.sleep(0.15 + random.random() * 0.1)

        # Merge Waivers if requested
        if include_waivers:
            try:
                wv = self.waiver_wire() or []
            except YahooClientError as e:
                if _looks_temporary(str(e)):
                    wv = []
                else:
                    raise
            for item in _coerce_player_dicts(wv):
                item["_availability"] = "W"
                # avoid dupes by player_id
                pid = _from_kv(item, "player_id")
                if pid and not any(_from_kv(x, "player_id") == pid for x in pool):
                    # respect position filter if provided
                    if (not position) or (position in (_eligible_positions(item) or [])):
                        pool.append(item)

        # Normalize to consistent row schema
        rows: List[Dict[str, Any]] = []
        for p in pool:
            pid = _safe_get(p, ["player_id", "0", "player_id"]) or _from_kv(p, "player_id")
            name = _player_name(p)
            team = _from_kv(p, "editorial_team_abbr")
            elig = _eligible_positions(p)
            primary = elig[0] if elig else None
            bye = _bye_week(p)
            pown = _percent_owned(p)
            stat = _from_kv(p, "status")
            inj = _from_kv(p, "injury_note")

            row = {
                "player_id": pid,
                "name": name,
                "team": team,
                "pos": primary,
                "elig": elig,
                "bye": bye,
                "%owned": pown,
                "stat": stat,
                "inj": inj,
                "avail": p.get("_availability", "FA"),
            }

            # Apply search filter if requested
            if search:
                if not (name or ""):
                    continue
                if search.lower() not in name.lower():
                    continue

            rows.append(row)

        # Local sort
        def sort_key_AR(r):
            # Approx "added recently" fallback: less owned first, stable by name
            try:
                own = float(r.get("%owned") or 0.0)
            except Exception:
                own = 0.0
            return (own, r.get("name") or "")

        def sort_key_POWN(r):
            try:
                own = float(r.get("%owned") or 0.0)
            except Exception:
                own = 0.0
            return (-own, r.get("name") or "")

        def sort_key_NAME(r):
            nm = r.get("name") or ""
            parts = nm.split()
            first = parts[0] if parts else ""
            last = parts[-1] if len(parts) > 1 else first
            return (last, first)

        key = (sort or "AR").upper()
        if key == "POWN":
            rows.sort(key=sort_key_POWN)
        elif key == "NAME":
            rows.sort(key=sort_key_NAME)
        else:
            rows.sort(key=sort_key_AR)

        # Enforce limit
        if isinstance(limit, int) and limit >= 0:
            rows = rows[:limit]

        # Yield
        for r in rows:
            yield r


# --- helper extractors (place below the class or in a utils module) -----------

def _coerce_player_dicts(items: Any) -> Iterable[dict]:
    """
    yahoo_fantasy_api sometimes returns lists of dicts with either a 'player' key
    or already-flattened player dicts. Normalize to bare player dicts.
    """
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if isinstance(it, dict):
            if "player" in it and isinstance(it["player"], dict):
                out.append(it["player"])
            else:
                out.append(it)
    return out


def _from_kv(obj, key):
    """Yahoo often uses KV blobs. Try several common shapes to extract `key`."""
    if not isinstance(obj, dict):
        return None

    # Direct lookup first
    if key in obj:
        return obj.get(key)

    kv = obj.get(0)
    if isinstance(kv, dict):
        # Flat {'name':..., 'value':...}
        if kv.get("name") == key:
            return kv.get("value")

        # Arrays of {'name': '...', 'value': '...'}
        for _, maybe_list in kv.items():
            if isinstance(maybe_list, list):
                for item in maybe_list:
                    if isinstance(item, dict) and item.get("name") == key:
                        return item.get("value")
    return None


def _safe_get(obj, keys):
    for k in keys:
        if isinstance(obj, dict) and k in obj:
            obj = obj[k]
        else:
            return None
    return obj


def _player_name(p):
    name = p.get(0, {}).get("name") or p.get("name")
    if isinstance(name, dict):
        first = name.get("first", "")
        last = name.get("last", "")
        return (" ".join([first, last])).strip()
    return name


def _eligible_positions(p):
    """
    Normalize eligible positions across common Yahoo shapes.
    Common:
      {'eligible_positions': {'0': {'position': 'RB'}, '1': {'position': 'WR'}}}
      {'eligible_positions': ['RB', 'WR']}
    """
    ep = p.get("eligible_positions")
    if not ep:
        return []

    # Case A: dict with numeric keys -> each has {'position': 'X'}
    if isinstance(ep, dict):
        positions = []
        i = 0
        while True:
            item = ep.get(str(i))
            if item is None:
                break
            pos = item.get("position")
            if pos:
                positions.append(pos)
            i += 1
        return positions

    # Case B: already a list of strings
    if isinstance(ep, list):
        return [x for x in ep if isinstance(x, str)]

    return []


def _bye_week(p):
    bw = _from_kv(p, "bye_weeks")
    if isinstance(bw, dict):
        # {"week":"14"} or similar
        return bw.get("week")
    return bw


def _percent_owned(p):
    po = p.get("percent_owned") or _from_kv(p, "percent_owned")
    if isinstance(po, dict):
        return po.get("value") or po.get("percent_owned")
    return po


def _stats_map(p):
    stats = p.get("player_stats") or p.get("player_points")
    out = {}
    if not stats:
        return out
    # Try typical shape: stats["stats"]["0"]["stat"]["stat_id"], ["value"]
    try:
        stats_root = stats.get("stats", {})
        i = 0
        while True:
            entry = stats_root.get(str(i))
            if entry is None:
                break
            stat = entry.get("stat", {})
            sid = stat.get("stat_id")
            val = int(stat.get("value")) if isinstance(stat.get("value"), str) and stat.get("value").isdigit() else stat.get("value")
            if sid is not None:
                out[str(sid)] = val
            i += 1
    except Exception:
        pass
    return out
