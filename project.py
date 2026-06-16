import random
from copy import deepcopy

from flask import Flask, redirect, render_template, request, url_for

from teams import FLAGS, GROUP_LETTERS, HOSTS, REAL_GROUPS, TEAMS

app = Flask(__name__)

TOURNAMENT = {}

ROUND_ORDER = [
    "Round of 32",
    "Round of 16",
    "Quarterfinals",
    "Semifinals",
    "Final",
]

ROUND_MATCH_COUNTS = {
    "Round of 32": 16,
    "Round of 16": 8,
    "Quarterfinals": 4,
    "Semifinals": 2,
    "Final": 1,
}

# Groups split by seeding role in the Round of 32.
OTHER_GROUPS = ["A", "B", "C", "D", "G", "H", "I", "J"]
SPECIAL_GROUPS = ["E", "F", "K", "L"]

#Team Setup Functions
def load_teams_by_name(names):
    """Return team dicts for the given team names."""
    lookup = {t["name"]: t for t in TEAMS}
    return [lookup[n] for n in names]

def assign_pots(teams):
    """Bucket teams into 4 pots using each team's hardcoded pot field."""
    pots = {"pot1": [], "pot2": [], "pot3": [], "pot4": []}
    for team in teams:
        pots[f"pot{team['pot']}"].append(team)
    return pots

#Group Draw Functions
def _group_confederation_valid(group_teams):
    """Check confederation constraints for a group."""
    counts = {}
    for team in group_teams:
        conf = team["confederation"]
        counts[conf] = counts.get(conf, 0) + 1
    if counts.get("UEFA", 0) > 2:
        return False
    for conf, count in counts.items():
        if conf != "UEFA" and count > 1:
            return False
    return True

def draw_groups(pots):
    """Draw 12 groups from 4 pots with confederation rules."""
    groups = {letter: [] for letter in GROUP_LETTERS}
    for pot_key in ("pot1", "pot2", "pot3", "pot4"):
        pot_teams = pots[pot_key]
        while True:
            shuffled = pot_teams[:]
            random.shuffle(shuffled)
            group_order = GROUP_LETTERS[:]
            random.shuffle(group_order)
            trial = {letter: groups[letter][:] for letter in GROUP_LETTERS}
            success = True
            for team, letter in zip(shuffled, group_order):
                if team["name"] in HOSTS and letter not in ("A", "B", "C"):
                    success = False
                    break
                candidate = trial[letter] + [team]
                if not _group_confederation_valid(candidate):
                    success = False
                    break
                trial[letter] = candidate
            if success:
                groups = trial
                break
    return groups

def generate_group_schedule(group_teams):
    """Return 3 matchdays of round-robin fixtures for a group of 4."""
    t1, t2, t3, t4 = group_teams
    return [
        [(t1, t2), (t3, t4)],
        [(t1, t3), (t4, t2)],
        [(t1, t4), (t2, t3)],
    ]

#Match Simulation Functions
ELO_DIVISOR = 350

def _win_probability(team_a, team_b):
    """Elo-style win probability for team_a (before draw adjustment)."""
    return 1 / (1 + 10 ** ((team_b["rating"] - team_a["rating"]) / ELO_DIVISOR))

def _draw_probability(team_a, team_b):
    """Draw probability — higher when evenly matched, lower when rating gap is large."""
    rating_diff = abs(team_a["rating"] - team_b["rating"])
    p_a = _win_probability(team_a, team_b)
    closeness = 1 - abs(p_a - 0.5) * 2
    base = 0.08 + 0.17 * closeness
    return max(0.03, base - rating_diff / 4500)

def _pick_scoreline(outcome, team_a=None, team_b=None):
    """Pick plausible goals consistent with the decided outcome.

    Winner goal ceiling scales with the rating gap so a 300+ pt mismatch
    can produce scorelines like 7-1; the loser's tally is weighted toward
    low values rather than drawn uniformly.
    """
    if outcome == "draw":
        score = random.choices([0, 1, 2, 3], weights=[25, 40, 25, 10], k=1)[0]
        return score, score

    # Signed advantage: positive means the winner was the stronger team.
    # Upsets (negative advantage) should produce tight scorelines.
    if team_a and team_b:
        winner_rating = team_a["rating"] if outcome == "home_win" else team_b["rating"]
        loser_rating  = team_b["rating"] if outcome == "home_win" else team_a["rating"]
        advantage = winner_rating - loser_rating
    else:
        advantage = 0

    if advantage >= 300:
        winner_goals = random.choices([1, 2, 3, 4, 5, 6, 7], weights=[4, 9, 18, 22, 22, 15, 10], k=1)[0]
    elif advantage >= 150:
        winner_goals = random.choices([1, 2, 3, 4, 5, 6], weights=[8, 18, 28, 25, 14, 7], k=1)[0]
    elif advantage >= 50:
        winner_goals = random.choices([1, 2, 3, 4, 5], weights=[18, 33, 28, 15, 6], k=1)[0]
    elif advantage >= -50:
        winner_goals = random.choices([1, 2, 3, 4], weights=[25, 38, 27, 10], k=1)[0]
    else:
        # Upset: underdog won, so keep the margin narrow
        winner_goals = random.choices([1, 2, 3], weights=[50, 37, 13], k=1)[0]

    # Loser goals: weighted heavily toward 0, capped strictly below winner
    max_loser = winner_goals - 1
    loser_goals = random.choices(
        range(max_loser + 1),
        weights=[max(1, 40 - i * 15) for i in range(max_loser + 1)],
        k=1,
    )[0]

    if outcome == "home_win":
        return winner_goals, loser_goals
    return loser_goals, winner_goals

def simulate_match(team_a, team_b, allow_draw=True):
    """Simulate a match between two teams and return the result dict."""
    p_a = _win_probability(team_a, team_b)
    p_b = 1 - p_a
    draw_prob = _draw_probability(team_a, team_b)

    p_a_win = p_a * (1 - draw_prob)
    p_b_win = p_b * (1 - draw_prob)

    # Knockout experience: slight edge to the higher-rated team under pressure
    if not allow_draw:
        if team_a["rating"] >= team_b["rating"]:
            p_a_win *= 1.05
        else:
            p_b_win *= 1.05

    outcome = random.choices(
        ["home_win", "draw", "away_win"],
        weights=[p_a_win, draw_prob, p_b_win],
        k=1,
    )[0]

    if outcome == "draw":
        home_score, away_score = _pick_scoreline("draw", team_a, team_b)
        if not allow_draw:
            winner = team_a if random.random() < p_a else team_b
            if winner == team_a:
                pen_home = random.randint(4, 5)
                pen_away = random.randint(2, pen_home - 1)
            else:
                pen_away = random.randint(4, 5)
                pen_home = random.randint(2, pen_away - 1)
            return {
                "home": team_a["name"],
                "away": team_b["name"],
                "home_score": home_score,
                "away_score": away_score,
                "winner": winner["name"],
                "penalties": True,
                "penalty_home": pen_home,
                "penalty_away": pen_away,
                "pen_home": pen_home,
                "pen_away": pen_away,
                "penalty_score": f"{pen_home}-{pen_away}",
                "penalty_winner": winner["name"],
            }
        return {
            "home": team_a["name"],
            "away": team_b["name"],
            "home_score": home_score,
            "away_score": away_score,
            "winner": None,
        }

    home_score, away_score = _pick_scoreline(outcome, team_a, team_b)
    if home_score > away_score:
        winner = team_a["name"]
    elif away_score > home_score:
        winner = team_b["name"]
    elif allow_draw:
        winner = None
    else:
        winner = team_a["name"] if random.random() < p_a else team_b["name"]
        if winner == team_a["name"]:
            pen_home = random.randint(4, 5)
            pen_away = random.randint(2, pen_home - 1)
        else:
            pen_away = random.randint(4, 5)
            pen_home = random.randint(2, pen_away - 1)
        return {
            "home": team_a["name"],
            "away": team_b["name"],
            "home_score": home_score,
            "away_score": away_score,
            "winner": winner,
            "penalties": True,
            "penalty_home": pen_home,
            "penalty_away": pen_away,
            "pen_home": pen_home,
            "pen_away": pen_away,
            "penalty_score": f"{pen_home}-{pen_away}",
            "penalty_winner": winner,
        }

    return {
        "home": team_a["name"],
        "away": team_b["name"],
        "home_score": home_score,
        "away_score": away_score,
        "winner": winner,
    }

#Group Stage Standings
def group_standings(group_teams, results):
    """Compute sorted standings for a group from completed match results."""
    stats = {}
    for team in group_teams:
        stats[team["name"]] = {
            "team": team["name"],
            "played": 0,
            "won": 0,
            "drawn": 0,
            "lost": 0,
            "goals_for": 0,
            "goals_against": 0,
            "goal_diff": 0,
            "points": 0,
        }

    for match in results:
        home = match["home"]
        away = match["away"]
        hs = match["home_score"]
        as_ = match["away_score"]
        stats[home]["played"] += 1
        stats[away]["played"] += 1
        stats[home]["goals_for"] += hs
        stats[home]["goals_against"] += as_
        stats[away]["goals_for"] += as_
        stats[away]["goals_against"] += hs

        if hs == as_ and not match.get("penalties"):
            stats[home]["drawn"] += 1
            stats[away]["drawn"] += 1
            stats[home]["points"] += 1
            stats[away]["points"] += 1
        elif hs > as_:
            stats[home]["won"] += 1
            stats[away]["lost"] += 1
            stats[home]["points"] += 3
        else:
            stats[away]["won"] += 1
            stats[home]["lost"] += 1
            stats[away]["points"] += 3

    for row in stats.values():
        row["goal_diff"] = row["goals_for"] - row["goals_against"]

    return sorted(
        stats.values(),
        key=lambda r: (-r["points"], -r["goal_diff"], -r["goals_for"], r["team"]),
    )


def rank_third_place_teams(all_group_standings):
    """Rank all 12 third-place teams and return the top 8."""
    thirds = [standings[2] for standings in all_group_standings.values()]
    return sorted(
        thirds,
        key=lambda r: (-r["points"], -r["goal_diff"], -r["goals_for"], r["team"]),
    )[:8]


def rank_all_third_place_teams(all_group_standings):
    """Rank all 12 third-place teams (used for display; top 8 advance)."""
    thirds = [standings[2] for standings in all_group_standings.values()]
    return sorted(
        thirds,
        key=lambda r: (-r["points"], -r["goal_diff"], -r["goals_for"], r["team"]),
    )


def build_knockout_bracket(group_standings_by_group, best_thirds):
    """Build Round of 32 matchups using the official seeding rules.

    - Section 1.1 (8 matches): OTHER_GROUPS winners vs. randomly assigned qualifying thirds
    - Section 1.2 (4 matches): OTHER_GROUPS runners-up cross-pairings (2A-2B, 2C-2D, 2G-2H, 2I-2J)
    - Section 1.3 (4 matches): SPECIAL_GROUPS crosses (1E-2F, 1F-2E, 1K-2L, 1L-2K)
    """
    team_lookup = {t["name"]: t for t in TEAMS}

    def get_team(name):
        return deepcopy(team_lookup[name])

    def get_placed(group, place):
        return get_team(group_standings_by_group[group][place]["team"])

    thirds_pool = [get_team(t["team"]) for t in best_thirds]
    random.shuffle(thirds_pool)
    thirds = dict(zip(OTHER_GROUPS, thirds_pool))

    def m(home_g, home_pos, away_g, away_pos=None):
        if away_pos is None:
            # Section 1.1: winner vs random third
            return {"round": "Round of 32", "home": get_placed(home_g, 0),
                    "away": thirds[home_g], "home_slot": f"1st {home_g}", "away_slot": "3rd (assigned)"}
        return {"round": "Round of 32", "home": get_placed(home_g, home_pos),
                "away": get_placed(away_g, away_pos),
                "home_slot": f"{'1st' if home_pos == 0 else '2nd'} {home_g}",
                "away_slot": f"{'1st' if away_pos == 0 else '2nd'} {away_g}"}

    matches = [
        # ── Left half (matches 0-7) ──────────────────────────────────────
        m("A", 0, None),          # 1A vs 3rd
        m("C", 1, "D", 1),        # 2C vs 2D
        m("B", 0, None),          # 1B vs 3rd
        m("E", 0, "F", 1),        # 1E vs 2F
        m("G", 0, None),          # 1G vs 3rd
        m("I", 1, "J", 1),        # 2I vs 2J
        m("H", 0, None),          # 1H vs 3rd
        m("K", 0, "L", 1),        # 1K vs 2L
        # ── Right half (matches 8-15) ────────────────────────────────────
        m("C", 0, None),          # 1C vs 3rd
        m("A", 1, "B", 1),        # 2A vs 2B
        m("D", 0, None),          # 1D vs 3rd
        m("F", 0, "E", 1),        # 1F vs 2E
        m("I", 0, None),          # 1I vs 3rd
        m("G", 1, "H", 1),        # 2G vs 2H
        m("J", 0, None),          # 1J vs 3rd
        m("L", 0, "K", 1),        # 1L vs 2K
    ]

    team_names = [m["home"]["name"] for m in matches] + [m["away"]["name"] for m in matches]
    assert len(set(team_names)) == 32, f"Duplicate teams in Round of 32: {team_names}"

    return matches


def simulate_round(matches):
    """Simulate all matches in a knockout round."""
    results = []
    winners = []
    for match in matches:
        result = simulate_match(match["home"], match["away"], allow_draw=False)
        result["round"] = match["round"]
        results.append(result)
        winner_name = result["winner"]
        winner = match["home"] if winner_name == match["home"]["name"] else match["away"]
        winners.append(winner)
    return results, winners


def next_round(winners, current_round_name, semifinal_losers=None):
    """Pair winners into the next knockout round."""
    if current_round_name == "Semifinals":
        third_place = {
            "round": "Third Place",
            "home": semifinal_losers[0],
            "away": semifinal_losers[1],
        }
        final_matches = [{
            "round": "Final",
            "home": winners[0],
            "away": winners[1],
        }]
        return "Final", final_matches, third_place

    idx = ROUND_ORDER.index(current_round_name)
    next_name = ROUND_ORDER[idx + 1]
    matches = []
    for i in range(0, len(winners), 2):
        matches.append({
            "round": next_name,
            "home": winners[i],
            "away": winners[i + 1],
        })
    return next_name, matches, None


def new_tournament_state(groups):
    """Build initial tournament state from group assignments."""
    schedules = {}
    results = {}
    for letter, group_teams in groups.items():
        schedules[letter] = generate_group_schedule(group_teams)
        results[letter] = []

    return {
        "phase": "groups",
        "groups": groups,
        "schedules": schedules,
        "results": results,
        "current_matchday": 1,
        "bracket": None,
        "final_standings": None,
        "best_thirds": None,
        "eliminated": {
            "group_third": [],
            "group_fourth": [],
            "round_of_32": [],
            "round_of_16": [],
            "quarterfinals": [],
            "semifinals": [],
        },
        "podium": None,
    }


def all_group_matches_done(state):
    """Return True if every group-stage match has been played."""
    for letter in GROUP_LETTERS:
        schedule = state["schedules"][letter]
        played = len(state["results"][letter])
        total = sum(len(md) for md in schedule)
        if played < total:
            return False
    return True


def _get_team_dict(name):
    return next(t for t in TEAMS if t["name"] == name)


def _compute_all_standings(state):
    standings = {}
    for letter in GROUP_LETTERS:
        standings[letter] = group_standings(
            state["groups"][letter],
            state["results"][letter],
        )
    return standings


def _record_group_eliminations(state, standings):
    for letter in GROUP_LETTERS:
        table = standings[letter]
        state["eliminated"]["group_third"].append(table[2]["team"])
        state["eliminated"]["group_fourth"].append(table[3]["team"])


def _finalize_group_stage(state):
    standings = _compute_all_standings(state)
    best_thirds = rank_third_place_teams(standings)
    bracket_matches = build_knockout_bracket(standings, best_thirds)
    _record_group_eliminations(state, standings)
    state["final_standings"] = standings
    state["best_thirds"] = best_thirds
    state["bracket"] = {
        "round_name": "Round of 32",
        "matches": bracket_matches,
        "results": [],
        "round_history": {},
        "all_round_matches": {"Round of 32": deepcopy(bracket_matches)},
        "third_place": None,
        "third_place_result": None,
        "final_result": None,
        "semifinal_losers": [],
    }
    state["phase"] = "knockout"


def _simulate_fixture(state, group_letter, matchday, match_index):
    schedule = state["schedules"][group_letter]
    fixture = schedule[matchday - 1][match_index]
    home, away = fixture
    result = simulate_match(home, away, allow_draw=True)
    state["results"][group_letter].append(result)


def _fixture_already_played(state, group_letter, matchday, match_index):
    """Return True if this specific fixture has already been simulated."""
    home, away = state["schedules"][group_letter][matchday - 1][match_index]
    for result in state["results"][group_letter]:
        if result["home"] == home["name"] and result["away"] == away["name"]:
            return True
    return False


def _fixture_result(state, group_letter, matchday, match_index):
    """Return the result dict for a specific fixture, or None if not played."""
    home, away = state["schedules"][group_letter][matchday - 1][match_index]
    for result in state["results"][group_letter]:
        if result["home"] == home["name"] and result["away"] == away["name"]:
            return result
    return None


def _get_matchday_fixtures(state, matchday):
    """Return all fixtures for a given matchday across all groups."""
    fixtures = []
    is_current = matchday == state["current_matchday"]
    for letter in GROUP_LETTERS:
        for idx, (home, away) in enumerate(state["schedules"][letter][matchday - 1]):
            result = _fixture_result(state, letter, matchday, idx)
            fixtures.append({
                "group": letter,
                "matchday": matchday,
                "index": idx,
                "home": home,
                "away": away,
                "played": result is not None,
                "result": result,
                "simulatable": is_current and result is None,
            })
    return fixtures


def _get_current_matchday_fixtures(state):
    return _get_matchday_fixtures(state, state["current_matchday"])


def _advance_matchday_if_complete(state):
    md = state["current_matchday"]
    all_done = all(f["played"] for f in _get_current_matchday_fixtures(state))
    if not all_done:
        return
    if md < 3:
        state["current_matchday"] = md + 1
    # MD3 complete: stay in "groups" phase until user clicks Continue


def _record_knockout_eliminations(state, results, round_name):
    key_map = {
        "Round of 32": "round_of_32",
        "Round of 16": "round_of_16",
        "Quarterfinals": "quarterfinals",
        "Semifinals": "semifinals",
    }
    key = key_map.get(round_name)
    if not key:
        return
    for result in results:
        loser = result["away"] if result["winner"] == result["home"] else result["home"]
        state["eliminated"][key].append(loser)


def _bracket_match_played(bracket, index):
    return any(r.get("match_index") == index for r in bracket["results"])


def _get_bracket_result(bracket, index):
    for r in bracket["results"]:
        if r.get("match_index") == index:
            return r
    return None


def _format_match_result(result):
    """Format a group-stage match result string for display."""
    if not result:
        return "—"
    return f"{result['home_score']}-{result['away_score']}"


def _format_bracket_score(result):
    """Format knockout score — penalties as (H)h-a(A)."""
    if not result:
        return None
    hs, as_ = result["home_score"], result["away_score"]
    if result.get("penalties"):
        ph = result.get("penalty_home", result.get("pen_home", 0))
        pa = result.get("penalty_away", result.get("pen_away", 0))
        return f"({ph}){hs}-{as_}({pa})"
    return f"{hs}-{as_}"


def _format_fixture_line(result):
    """Format a full fixture line like 'Mexico 2 - 1 South Africa'."""
    if not result:
        return None
    score = _format_match_result(result)
    return f"{result['home']} {score} {result['away']}"


def _third_place_complete(bracket):
    return bracket.get("third_place_result") is not None


def _simulate_third_place_match(bracket):
    """Simulate the 3rd-place playoff and store the result."""
    if _third_place_complete(bracket) or not bracket.get("third_place"):
        return False
    tp = bracket["third_place"]
    result = simulate_match(tp["home"], tp["away"], allow_draw=False)
    result["round"] = "Third Place"
    bracket["third_place_result"] = result
    return True


def build_bracket_visualization(bracket):
    """Build ordered bracket rounds for display with simulate metadata.

    Always emits every round (R32 through Final) so the full wall-chart
    skeleton is visible from the first day of the knockout stage. Rounds that
    haven't been played yet get TBD placeholder cards (tbd=True, simulatable=False).
    """
    rounds = []
    current_name = bracket["round_name"]
    third_place_round = None

    for round_name in ROUND_ORDER:
        if round_name in bracket.get("round_history", {}):
            # Completed round — show real results
            stored = bracket.get("all_round_matches", {}).get(round_name, [])
            history = bracket["round_history"][round_name]
            entries = []
            for i, result in enumerate(history):
                match = stored[i] if i < len(stored) else {}
                home = match.get("home", result["home"])
                away = match.get("away", result["away"])
                home_name = home["name"] if isinstance(home, dict) else home
                away_name = away["name"] if isinstance(away, dict) else away
                entries.append({
                    "home": home_name,
                    "away": away_name,
                    "result": result,
                    "winner": result["winner"],
                    "simulatable": False,
                    "blocked": False,
                    "match_index": None,
                    "match_type": "bracket",
                    "tbd": False,
                })
            rounds.append({"name": round_name, "matches": entries, "is_current": False})
        elif round_name == current_name:
            # Active round — show current matches with simulate buttons
            if round_name == "Final" and bracket.get("third_place"):
                tp = bracket["third_place"]
                tp_result = bracket.get("third_place_result")
                third_place_round = {
                    "name": "Third Place",
                    "matches": [{
                        "home": tp["home"]["name"],
                        "away": tp["away"]["name"],
                        "result": tp_result,
                        "winner": tp_result["winner"] if tp_result else None,
                        "simulatable": tp_result is None,
                        "blocked": False,
                        "match_index": None,
                        "match_type": "third_place",
                        "tbd": False,
                    }],
                    "is_current": True,
                }

            entries = []
            for i, match in enumerate(bracket["matches"]):
                result = _get_bracket_result(bracket, i)
                final_blocked = (
                    round_name == "Final"
                    and bracket.get("third_place")
                    and not _third_place_complete(bracket)
                )
                entries.append({
                    "home": match["home"]["name"],
                    "away": match["away"]["name"],
                    "result": result,
                    "winner": result["winner"] if result else None,
                    "simulatable": result is None and not final_blocked,
                    "blocked": final_blocked and result is None,
                    "match_index": i,
                    "match_type": "bracket",
                    "tbd": False,
                })
            rounds.append({"name": round_name, "matches": entries, "is_current": True})
        else:
            # Future round — TBD placeholders so the full bracket skeleton is visible
            count = ROUND_MATCH_COUNTS[round_name]
            rounds.append({
                "name": round_name,
                "matches": [
                    {
                        "home": "TBD",
                        "away": "TBD",
                        "result": None,
                        "winner": None,
                        "simulatable": False,
                        "blocked": False,
                        "match_index": None,
                        "match_type": "bracket",
                        "tbd": True,
                    }
                    for _ in range(count)
                ],
                "is_current": False,
            })

    # Handle Third Place round
    if third_place_round:
        final_idx = next(
            (i for i, r in enumerate(rounds) if r["name"] == "Final"),
            len(rounds),
        )
        rounds.insert(final_idx, third_place_round)
    elif bracket.get("third_place") and bracket.get("third_place_result"):
        tp = bracket["third_place"]
        tp_result = bracket["third_place_result"]
        rounds.append({
            "name": "Third Place",
            "matches": [{
                "home": tp["home"]["name"],
                "away": tp["away"]["name"],
                "result": tp_result,
                "winner": tp_result["winner"],
                "simulatable": False,
                "blocked": False,
                "match_index": None,
                "match_type": "third_place",
                "tbd": False,
            }],
            "is_current": False,
        })
    else:
        # Before Semifinals end, third-place teams are not yet known
        rounds.append({
            "name": "Third Place",
            "matches": [{
                "home": "TBD",
                "away": "TBD",
                "result": None,
                "winner": None,
                "simulatable": False,
                "blocked": False,
                "match_index": None,
                "match_type": "third_place",
                "tbd": True,
            }],
            "is_current": False,
        })

    return rounds


def build_wall_chart(bracket):
    """Structure bracket data for the two-sided wall-chart layout.

    Returns left_rounds (R32→R16→QF→SF), center (Final + 3rd Place),
    and right_rounds (SF→QF→R16→R32) for the mirrored converging layout.
    """
    viz = build_bracket_visualization(bracket)

    left_rounds = []
    right_rounds_raw = []
    center = {"final": None, "third_place": None}

    for rd in viz:
        name = rd["name"]
        if name == "Final":
            center["final"] = rd
        elif name == "Third Place":
            center["third_place"] = rd
        else:
            half = len(rd["matches"]) // 2
            left_rounds.append({
                "name": name,
                "matches": rd["matches"][:half],
                "is_current": rd["is_current"],
            })
            right_rounds_raw.append({
                "name": name,
                "matches": rd["matches"][half:],
                "is_current": rd["is_current"],
            })

    # Right side reads center-outward: SF → QF → R16 → R32
    return {
        "left_rounds": left_rounds,
        "right_rounds": list(reversed(right_rounds_raw)),
        "center": center,
    }


def get_projected_r32(state):
    """Compute projected R32 matchups for display during the group stage.

    Section 1.1 slots use an "An assigned 3rd" placeholder because the random
    thirds assignment only happens once, after the group stage is fully complete.
    Sections 1.2 and 1.3 show real projected team names from current standings.
    """
    standings = _compute_all_standings(state)
    team_lookup = {t["name"]: t for t in TEAMS}

    def get_team(name):
        return deepcopy(team_lookup[name])

    def get_placed(group, place):
        return get_team(standings[group][place]["team"])

    tbd3 = {"name": "An assigned 3rd"}

    def m(home_g, home_pos, away_g=None, away_pos=None):
        if away_g is None:
            return {"round": "Round of 32", "home": get_placed(home_g, 0), "away": tbd3,
                    "home_slot": f"1st {home_g}", "away_slot": "3rd (random)"}
        return {"round": "Round of 32", "home": get_placed(home_g, home_pos),
                "away": get_placed(away_g, away_pos),
                "home_slot": f"{'1st' if home_pos == 0 else '2nd'} {home_g}",
                "away_slot": f"{'1st' if away_pos == 0 else '2nd'} {away_g}"}

    return [
        # ── Left half ────────────────────────────────────────────────────
        m("A", 0),            # 1A vs 3rd
        m("C", 1, "D", 1),    # 2C vs 2D
        m("B", 0),            # 1B vs 3rd
        m("E", 0, "F", 1),    # 1E vs 2F
        m("G", 0),            # 1G vs 3rd
        m("I", 1, "J", 1),    # 2I vs 2J
        m("H", 0),            # 1H vs 3rd
        m("K", 0, "L", 1),    # 1K vs 2L
        # ── Right half ───────────────────────────────────────────────────
        m("C", 0),            # 1C vs 3rd
        m("A", 1, "B", 1),    # 2A vs 2B
        m("D", 0),            # 1D vs 3rd
        m("F", 0, "E", 1),    # 1F vs 2E
        m("I", 0),            # 1I vs 3rd
        m("G", 1, "H", 1),    # 2G vs 2H
        m("J", 0),            # 1J vs 3rd
        m("L", 0, "K", 1),    # 1L vs 2K
    ]


def build_projected_wall_chart(projected_r32):
    """Convert projected R32 list into the wall-chart structure used by the bracket template."""
    def _convert(m):
        home = m["home"]["name"] if isinstance(m["home"], dict) else m["home"]
        away = m["away"]["name"] if isinstance(m["away"], dict) else m["away"]
        is_tbd = home in ("TBD", "An assigned 3rd") or away in ("TBD", "An assigned 3rd")
        return {
            "home": "3rd Place (TBD)" if home == "An assigned 3rd" else home,
            "away": "3rd Place (TBD)" if away == "An assigned 3rd" else away,
            "result": None, "winner": None,
            "simulatable": False, "blocked": False,
            "match_index": None, "match_type": "projected",
            "tbd": is_tbd,
        }

    def _tbd():
        return {"home": "TBD", "away": "TBD", "result": None, "winner": None,
                "simulatable": False, "blocked": False,
                "match_index": None, "match_type": "projected", "tbd": True}

    r32 = [_convert(m) for m in projected_r32]

    left_rounds = [
        {"name": "Round of 32",   "matches": r32[:8],                   "is_current": True},
        {"name": "Round of 16",   "matches": [_tbd() for _ in range(4)], "is_current": False},
        {"name": "Quarterfinals", "matches": [_tbd() for _ in range(2)], "is_current": False},
        {"name": "Semifinals",    "matches": [_tbd()],                   "is_current": False},
    ]
    right_rounds_raw = [
        {"name": "Round of 32",   "matches": r32[8:],                   "is_current": True},
        {"name": "Round of 16",   "matches": [_tbd() for _ in range(4)], "is_current": False},
        {"name": "Quarterfinals", "matches": [_tbd() for _ in range(2)], "is_current": False},
        {"name": "Semifinals",    "matches": [_tbd()],                   "is_current": False},
    ]
    return {
        "left_rounds":  left_rounds,
        "right_rounds": list(reversed(right_rounds_raw)),
        "center": {
            "final":       {"matches": [_tbd()], "is_current": False},
            "third_place": {"matches": [_tbd()], "is_current": False},
        },
    }


# --- Flask routes ---

@app.route("/")
def index():
    return render_template("setup.html")


@app.route("/start", methods=["POST"])
def start():
    global TOURNAMENT
    choice = request.form.get("choice", "real")
    if choice == "real":
        groups = {
            letter: load_teams_by_name(names)
            for letter, names in REAL_GROUPS.items()
        }
    else:
        pots = assign_pots(TEAMS)
        groups = draw_groups(pots)
    TOURNAMENT = new_tournament_state(groups)
    return redirect(url_for("preview"))


@app.route("/preview")
def preview():
    if not TOURNAMENT or TOURNAMENT.get("phase") != "groups":
        return redirect(url_for("index"))
    return render_template(
        "group_preview.html",
        state=TOURNAMENT,
        groups=TOURNAMENT["groups"],
        flags=FLAGS,
        group_letters=GROUP_LETTERS,
    )


@app.route("/begin", methods=["POST"])
def begin():
    if not TOURNAMENT:
        return redirect(url_for("index"))
    return redirect(url_for("groups_view"))


@app.route("/groups")
@app.route("/groups/<group_letter>")
def groups_view(group_letter="A"):
    if TOURNAMENT.get("phase") == "knockout":
        return redirect(url_for("bracket_view"))
    if TOURNAMENT.get("phase") == "done":
        return redirect(url_for("results_view"))
    if not TOURNAMENT or TOURNAMENT.get("phase") != "groups":
        return redirect(url_for("index"))

    if group_letter not in GROUP_LETTERS:
        group_letter = "A"

    view_matchday = request.args.get("matchday", type=int)
    if view_matchday is None or view_matchday not in (1, 2, 3):
        view_matchday = TOURNAMENT["current_matchday"]

    standings = _compute_all_standings(TOURNAMENT)
    thirds_ranking = rank_all_third_place_teams(standings)

    idx = GROUP_LETTERS.index(group_letter)
    prev_group = GROUP_LETTERS[(idx - 1) % 12]
    next_group = GROUP_LETTERS[(idx + 1) % 12]

    return render_template(
        "groups.html",
        state=TOURNAMENT,
        fixtures=_get_matchday_fixtures(TOURNAMENT, view_matchday),
        view_matchday=view_matchday,
        standings=standings[group_letter],
        all_standings=standings,
        thirds_ranking=thirds_ranking,
        current_group=group_letter,
        prev_group=prev_group,
        next_group=next_group,
        flags=FLAGS,
        group_letters=GROUP_LETTERS,
        format_result=_format_match_result,
        projected_wall_chart=build_projected_wall_chart(get_projected_r32(TOURNAMENT)),
        groups_complete=all_group_matches_done(TOURNAMENT),
    )


@app.route("/start_knockout", methods=["POST"])
def start_knockout():
    if not TOURNAMENT or TOURNAMENT.get("phase") != "groups":
        return redirect(url_for("index"))
    if not all_group_matches_done(TOURNAMENT):
        return redirect(url_for("groups_view"))
    _finalize_group_stage(TOURNAMENT)
    return redirect(url_for("bracket_view"))


@app.route("/simulate_match", methods=["POST"])
def simulate_match_route():
    group_letter = request.form["group"]
    matchday = int(request.form["matchday"])
    match_index = int(request.form["index"])
    if not _fixture_already_played(TOURNAMENT, group_letter, matchday, match_index):
        _simulate_fixture(TOURNAMENT, group_letter, matchday, match_index)
        _advance_matchday_if_complete(TOURNAMENT)
    if TOURNAMENT.get("phase") == "knockout":
        return redirect(url_for("bracket_view"))
    return redirect(url_for("groups_view", group_letter=group_letter, matchday=matchday))


@app.route("/simulate_matchday", methods=["POST"])
def simulate_matchday_route():
    md = TOURNAMENT["current_matchday"]
    for letter in GROUP_LETTERS:
        for idx in range(len(TOURNAMENT["schedules"][letter][md - 1])):
            if not _fixture_already_played(TOURNAMENT, letter, md, idx):
                _simulate_fixture(TOURNAMENT, letter, md, idx)
    _advance_matchday_if_complete(TOURNAMENT)
    if TOURNAMENT.get("phase") == "knockout":
        return redirect(url_for("bracket_view"))
    return redirect(url_for("groups_view", matchday=TOURNAMENT["current_matchday"]))


@app.route("/bracket")
def bracket_view():
    if TOURNAMENT.get("phase") == "done":
        return redirect(url_for("results_view"))
    if not TOURNAMENT or TOURNAMENT.get("phase") != "knockout":
        return redirect(url_for("index"))

    bracket = TOURNAMENT["bracket"]
    return render_template(
        "bracket.html",
        state=TOURNAMENT,
        bracket=bracket,
        wall_chart=build_wall_chart(bracket),
        flags=FLAGS,
        format_result=_format_match_result,
        format_bracket_score=_format_bracket_score,
    )


def _advance_bracket_round(state):
    """Advance knockout bracket when all matches in the current round are played."""
    bracket = state["bracket"]
    round_name = bracket["round_name"]

    round_results = []
    for i, match in enumerate(bracket["matches"]):
        result = _get_bracket_result(bracket, i)
        if result is None:
            return False
        round_results.append(result)

    winners = []
    for match, result in zip(bracket["matches"], round_results):
        winner_name = result["winner"]
        winner = match["home"] if winner_name == match["home"]["name"] else match["away"]
        winners.append(winner)

    if round_name == "Semifinals":
        bracket["semifinal_losers"] = []
        for match, result in zip(bracket["matches"], round_results):
            loser_name = result["away"] if result["winner"] == result["home"] else result["home"]
            bracket["semifinal_losers"].append(_get_team_dict(loser_name))

    _record_knockout_eliminations(state, round_results, round_name)
    bracket["round_history"][round_name] = deepcopy(round_results)
    if "all_round_matches" not in bracket:
        bracket["all_round_matches"] = {}
    bracket["all_round_matches"][round_name] = deepcopy(bracket["matches"])

    if round_name == "Final":
        bracket["final_result"] = round_results[0]
        if bracket.get("third_place") and not _third_place_complete(bracket):
            return False
        state["phase"] = "done"
        _set_podium(state)
        return True

    if round_name == "Semifinals":
        next_name, next_matches, third_place = next_round(
            winners, round_name, bracket["semifinal_losers"]
        )
        bracket["round_name"] = next_name
        bracket["matches"] = next_matches
        bracket["results"] = []
        bracket["third_place"] = third_place
        bracket["all_round_matches"][next_name] = deepcopy(next_matches)
    else:
        next_name, next_matches, _ = next_round(winners, round_name)
        bracket["round_name"] = next_name
        bracket["matches"] = next_matches
        bracket["results"] = []
        bracket["all_round_matches"][next_name] = deepcopy(next_matches)
    return False


@app.route("/simulate_bracket_match", methods=["POST"])
def simulate_bracket_match_route():
    bracket = TOURNAMENT["bracket"]
    match_type = request.form.get("match_type", "bracket")

    if match_type == "third_place":
        if _third_place_complete(bracket):
            return redirect(url_for("bracket_view"))
        _simulate_third_place_match(bracket)
        return redirect(url_for("bracket_view"))

    index = int(request.form["index"])
    if _bracket_match_played(bracket, index):
        return redirect(url_for("bracket_view"))

    if bracket["round_name"] == "Final" and bracket.get("third_place") and not _third_place_complete(bracket):
        return redirect(url_for("bracket_view"))

    match = bracket["matches"][index]
    result = simulate_match(match["home"], match["away"], allow_draw=False)
    result["round"] = bracket["round_name"]
    result["match_index"] = index
    bracket["results"].append(result)

    if _advance_bracket_round(TOURNAMENT):
        return redirect(url_for("results_view"))

    return redirect(url_for("bracket_view"))


@app.route("/simulate_round", methods=["POST"])
def simulate_round_route():
    bracket = TOURNAMENT["bracket"]

    if bracket["round_name"] == "Final" and bracket.get("third_place"):
        _simulate_third_place_match(bracket)

    for i, m in enumerate(bracket["matches"]):
        if not _bracket_match_played(bracket, i):
            if bracket["round_name"] == "Final" and not _third_place_complete(bracket):
                break
            result = simulate_match(m["home"], m["away"], allow_draw=False)
            result["round"] = bracket["round_name"]
            result["match_index"] = i
            bracket["results"].append(result)

    if _advance_bracket_round(TOURNAMENT):
        return redirect(url_for("results_view"))

    return redirect(url_for("bracket_view"))


def _set_podium(state):
    bracket = state["bracket"]
    final = bracket.get("final_result")
    third = bracket.get("third_place_result")
    if not final:
        return
    champion = final["winner"]
    runner_up = final["away"] if champion == final["home"] else final["home"]
    third_place = third["winner"] if third else None
    fourth = None
    if third:
        fourth = third["away"] if third_place == third["home"] else third["home"]
    state["podium"] = {
        "champion": champion,
        "runner_up": runner_up,
        "third": third_place,
        "fourth": fourth,
        "final_score": _format_bracket_score(final),
        "final_home": final["home"],
        "final_away": final["away"],
        "final_home_score": final["home_score"],
        "final_away_score": final["away_score"],
    }


@app.route("/results")
def results_view():
    if not TOURNAMENT or TOURNAMENT.get("phase") != "done":
        return redirect(url_for("index"))
    qualified_thirds = {t["team"] for t in (TOURNAMENT.get("best_thirds") or [])}
    return render_template(
        "results.html",
        state=TOURNAMENT,
        flags=FLAGS,
        format_bracket_score=_format_bracket_score,
        wall_chart=build_wall_chart(TOURNAMENT["bracket"]),
        all_standings=TOURNAMENT["final_standings"],
        group_letters=GROUP_LETTERS,
        qualified_thirds=qualified_thirds,
    )


@app.route("/reset", methods=["POST"])
def reset():
    global TOURNAMENT
    TOURNAMENT = {}
    return redirect(url_for("index"))


def main():
    # Port 5001 avoids conflict with macOS AirPlay Receiver on port 5000 (HTTP 403).
    app.run(debug=True, host="127.0.0.1", port=5001)


if __name__ == "__main__":
    main()
