from typing import List, Dict, Tuple
import math

def tier_players(pool: List[Dict]) -> List[List[Dict]]:
    """
    Pool items need: {"player_id","name","pos","proj","adp"}
    Tiers by z-score within position; break tier when drop > threshold.
    """
    by_pos = {}
    for p in pool:
        by_pos.setdefault(p["pos"], []).append(p)
    tiers = []
    for pos, players in by_pos.items():
        players.sort(key=lambda x: x["proj"], reverse=True)
        prev = None
        current_tier = []
        for p in players:
            if prev and (prev["proj"] - p["proj"]) > 1.8:  # crude tier break
                tiers.append(current_tier)
                current_tier = []
            current_tier.append(p)
            prev = p
        if current_tier: tiers.append(current_tier)
    # Flatten while keeping tier boundaries (already chunked)
    return tiers

def suggest_pick(available: List[Dict], my_roster_needs: Dict[str,int], picks_until_next:int) -> List[Dict]:
    """
    Score = proj + scarcity + need - reach_penalty
    scarcity: fewer good options remaining at a pos → bonus
    need: if you still need a starter at a pos → bonus
    reach_penalty: don’t reach too far past ADP unless scarcity is high
    """
    # Count remaining quality per position
    quality_cut = 10.0
    remaining_quality = {}
    for p in available:
        remaining_quality[p["pos"]] = remaining_quality.get(p["pos"],0) + (1 if p["proj"] >= quality_cut else 0)

    def score(p):
        scarcity = 2.0 * (1.0 / max(1, remaining_quality.get(p["pos"],1)))
        need_bonus = 2.5 if my_roster_needs.get(p["pos"],0) > 0 else 0.5
        reach = max(0, p.get("pick_num", 0) - p.get("adp_pick", 0))
        reach_pen = 0.02 * reach
        return p["proj"] + scarcity + need_bonus - reach_pen

    ranked = sorted(available, key=score, reverse=True)
    return ranked[:5]
