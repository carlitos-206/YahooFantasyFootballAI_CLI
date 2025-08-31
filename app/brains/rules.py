from typing import List, Dict

def suggest_lineup(features: List[Dict], slots: Dict[str, int]) -> List[Dict]:
    """
    Simple heuristic:
    - Sort by (proj - penalty) where penalty factors in injury + tough defense.
    - Fill required slots first (e.g., RB2/WR2/QB/TE), then FLEX.
    """
    def score(f):
        injury_pen = 4.0 if f["injury"] in ("O","IR") else 2.0 if f["injury"] in ("Q","D") else 0.0
        def_pen = (f["def_rank"] - 16) * 0.1  # positive if easier than avg
        return f["proj"] + def_pen - injury_pen

    ranked = sorted(features, key=score, reverse=True)
    lineup = []
    filled = {k: 0 for k in slots}
    for f in ranked:
        pos = f["pos"]
        # place in a matching slot or FLEX
        placed = False
        if pos in filled and filled[pos] < slots[pos]:
            lineup.append({"player_id": f["player_id"], "slot": pos, "score": round(score(f),2)})
            filled[pos] += 1
            placed = True
        if not placed and "FLEX" in filled and filled["FLEX"] < slots["FLEX"] and pos in ("RB","WR","TE"):
            lineup.append({"player_id": f["player_id"], "slot": "FLEX", "score": round(score(f),2)})
            filled["FLEX"] += 1
    return lineup

def suggest_waivers(free_agents_feats, roster_weak_positions=("RB","WR")):
    # Find undervalued FAs vs your worst bench at weak positions
    ranked_fa = sorted(free_agents_feats, key=lambda f: f["proj"], reverse=True)
    return ranked_fa[:5]
