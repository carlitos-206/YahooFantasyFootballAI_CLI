# app/yahoo_client.py
import time
import json
import random
from typing import Callable, Any, Iterable, List, Dict
from yahoo_oauth import OAuth2
from yahoo_fantasy_api import league as yf_league

class YahooClient:
    def __init__(self, league_id: str, oauth_file: str = "data/yahoo_oauth.json"):
        self.oauth = OAuth2(None, None, from_file=oauth_file)

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

    # --- Retry helper ---
    def _retry(self, fn: Callable[[], Any], *, tries=3, base_sleep=0.6) -> Any:
        last_err = None
        for i in range(tries):
            try:
                return fn()
            except Exception as e:
                last_err = e
                msg = str(e)
                # if clearly auth, fail fast
                if "401" in msg or "invalid_grant" in msg or "Not authorized" in msg:
                    raise
                time.sleep(base_sleep * (2 ** i))  # exponential backoff
        raise last_err

    # --- League wrappers ---
    def standings(self):
        return self._retry(lambda: self.league().standings())

    def settings(self):
        return self._retry(lambda: self.league().settings())

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

    # ---------- NEW: unified available pool (FA + Waivers) ----------
    def available_players(
        self,
        position: str | None = None,
        *,
        include_waivers: bool = True,
        search: str | None = None,
        sort: str = "AR",               # local sort: AR (added recently*), POWN, NAME
        limit: int | None = None,
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
                  - "AR"   : pseudo "added recently" (we approximate by percent-owned asc, then name)
                  - "POWN" : percent owned desc
                  - "NAME" : alphabetical by last, then first
            limit: Max number of rows yielded after sorting/filtering.
        """
        positions = [position] if position else ["QB", "RB", "WR", "TE", "DEF", "K"]

        # Collect Free Agents by position
        pool: List[dict] = []
        for pos in positions:
            try:
                fa = self.free_agents(pos) or []
            except Exception:
                fa = []
            for item in _coerce_player_dicts(fa):
                item["_availability"] = "FA"
                pool.append(item)

        # Merge Waivers if requested
        if include_waivers:
            try:
                wv = self.waiver_wire() or []
            except Exception:
                wv = []
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
            # If %owned missing, treat as 0 for sorting purposes.
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

        key = sort.upper() if sort else "AR"
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


# --- helper extractors (place below the class or in a utils module) ---

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
    """Yahoo often uses '0': {'name':'x','value':'y'} arrays; find key there."""
    kv = obj.get(0) if isinstance(obj, dict) else None
    if isinstance(kv, dict):
        # not always consistent; try common shapes
        for _, maybe_list in kv.items():
            if isinstance(maybe_list, list):
                for item in maybe_list:
                    if isinstance(item, dict) and item.get("name") == key:
                        return item.get("value")
    # fallback lookups
    return obj.get(key)

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
    ep = _safe_get(p, ["eligible_positions"])
    if not isinstance(ep, list):
        # sometimes under p['eligible_positions'][0]['position']
        try:
            positions = []
            i = 0
            while True:
                pos = ep.get(str(i), {}).get("position")
                if pos is None:
                    break
                positions.append(pos)
                i += 1
            return positions
        except Exception:
            return []
    # already a list
    return ep

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
            val = stat.get("value")
            if sid is not None:
                out[str(sid)] = val
            i += 1
    except Exception:
        pass
    return out
