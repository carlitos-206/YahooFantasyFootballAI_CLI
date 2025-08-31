def build_lineup_features(roster, opponent_defense, injuries, weather=None):
    # Return a dict per player with rankable features for the brain
    feats = []
    for p in roster:
        feats.append({
            "player_id": p["player_id"],
            "pos": p["position"],
            "proj": p.get("proj_points", 0.0),
            "def_rank": opponent_defense.get(p["position"], 16),
            "injury": p.get("status", "OK"),
            "snap_trend": p.get("snap_trend", 0.0),
            "risk": p.get("volatility", 0.0),
        })
    return feats
