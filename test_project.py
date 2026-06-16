"""Tests for World Cup 2026 Tournament Simulator core logic."""

import random

import pytest

from project import (
    assign_pots,
    build_knockout_bracket,
    draw_groups,
    generate_group_schedule,
    group_standings,
    load_teams_by_name,
    next_round,
    rank_third_place_teams,
    simulate_match,
)
from teams import GROUP_LETTERS, REAL_GROUPS, TEAMS


def _team(name):
    return next(t for t in TEAMS if t["name"] == name)


def test_real_groups_partition():
    """Every team appears exactly once in REAL_GROUPS."""
    all_names = []
    for names in REAL_GROUPS.values():
        assert len(names) == 4
        all_names.extend(names)
    assert len(REAL_GROUPS) == 12
    assert len(all_names) == 48
    team_names = {t["name"] for t in TEAMS}
    assert set(all_names) == team_names
    assert len(all_names) == len(set(all_names))


def test_simulate_match():
    random.seed(42)
    spain = _team("Spain")
    brazil = _team("Brazil")
    result = simulate_match(spain, brazil, allow_draw=True)

    assert set(result.keys()) >= {"home", "away", "home_score", "away_score", "winner"}
    assert result["home"] == "Spain"
    assert result["away"] == "Brazil"
    assert isinstance(result["home_score"], int) and result["home_score"] >= 0
    assert isinstance(result["away_score"], int) and result["away_score"] >= 0

    if result["winner"] is None:
        assert result["home_score"] == result["away_score"]
    elif result["winner"] == result["home"]:
        assert result["home_score"] > result["away_score"]
    else:
        assert result["away_score"] > result["home_score"]

    for i in range(50):
        random.seed(i)
        ko = simulate_match(spain, brazil, allow_draw=False)
        assert ko["winner"] is not None


def test_simulate_match_penalties():
    """Knockout draws must resolve via penalties with stored scores."""
    from project import _draw_probability

    iran = _team("Iran")
    uruguay = _team("Uruguay")
    assert 0.10 <= _draw_probability(iran, uruguay) <= 0.30

    found_penalties = False
    for seed in range(500):
        random.seed(seed)
        result = simulate_match(iran, uruguay, allow_draw=False)
        assert result["winner"] is not None
        if result.get("penalties"):
            found_penalties = True
            assert result["home_score"] == result["away_score"]
            assert "penalty_home" in result
            assert "penalty_away" in result
            assert result["penalty_home"] != result["penalty_away"]
            assert result["penalty_winner"] == result["winner"]
            assert result["penalty_home"] > result["penalty_away"] or result["penalty_away"] > result["penalty_home"]
            break
    assert found_penalties, "Expected at least one penalty shootout in 500 trials"


def test_group_standings_equal_score_is_draw():
    """Equal scores must count as a draw even if winner field is wrong."""
    teams = [
        _team("Turkey"),
        _team("Australia"),
        _team("USA"),
        _team("Paraguay"),
    ]
    results = [{
        "home": "Turkey",
        "away": "Australia",
        "home_score": 0,
        "away_score": 0,
        "winner": "Australia",
    }]
    table = group_standings(teams, results)
    turkey_row = next(r for r in table if r["team"] == "Turkey")
    aus_row = next(r for r in table if r["team"] == "Australia")
    assert turkey_row["drawn"] == 1
    assert aus_row["drawn"] == 1
    assert turkey_row["points"] == 1
    assert aus_row["points"] == 1
    assert turkey_row["won"] == 0
    assert aus_row["won"] == 0


def test_simulate_match_win_never_ties():
    """Win outcomes must never produce equal scores."""
    from project import _pick_scoreline

    random.seed(0)
    for _ in range(100):
        home, away = _pick_scoreline("home_win")
        assert home > away
        home, away = _pick_scoreline("away_win")
        assert away > home


def test_simulate_match_draw_has_no_winner():
    random.seed(0)
    turkey = _team("Turkey")
    australia = _team("Australia")
    for seed in range(500):
        random.seed(seed)
        result = simulate_match(turkey, australia, allow_draw=True)
        if result["home_score"] == result["away_score"]:
            assert result["winner"] is None
            assert not result.get("penalties")
            return
    pytest.skip("No draw produced in 500 trials")


def test_simulate_match_favorite_large_gap():
    """Heavy favorite should win the vast majority of non-draw outcomes."""
    argentina = _team("Argentina")
    new_zealand = _team("New Zealand")
    fav_wins = 0
    non_draws = 0
    for seed in range(1000):
        random.seed(seed)
        result = simulate_match(argentina, new_zealand, allow_draw=True)
        if result["winner"] is not None:
            non_draws += 1
            if result["winner"] == "Argentina":
                fav_wins += 1
    assert non_draws > 800
    assert fav_wins / non_draws >= 0.85


def test_simulate_match_close_teams_competitive():
    """Closely-rated teams should produce competitive results."""
    croatia = _team("Croatia")
    japan = _team("Japan")
    croatia_wins = 0
    for seed in range(1000):
        random.seed(seed)
        result = simulate_match(croatia, japan, allow_draw=True)
        if result["winner"] == "Croatia":
            croatia_wins += 1
    assert 400 <= croatia_wins <= 750


def test_group_standings():
    teams = [
        _team("Brazil"),
        _team("Morocco"),
        _team("Scotland"),
        _team("Haiti"),
    ]
    results = [
        {"home": "Brazil", "away": "Morocco", "home_score": 2, "away_score": 0, "winner": "Brazil"},
        {"home": "Scotland", "away": "Haiti", "home_score": 1, "away_score": 1, "winner": None},
        {"home": "Brazil", "away": "Scotland", "home_score": 1, "away_score": 1, "winner": None},
        {"home": "Haiti", "away": "Morocco", "home_score": 0, "away_score": 2, "winner": "Morocco"},
        {"home": "Brazil", "away": "Haiti", "home_score": 3, "away_score": 0, "winner": "Brazil"},
        {"home": "Morocco", "away": "Scotland", "home_score": 2, "away_score": 1, "winner": "Morocco"},
    ]
    table = group_standings(teams, results)

    assert len(table) == 4
    assert table[0]["team"] == "Brazil"
    assert table[0]["points"] == 7
    assert table[1]["team"] == "Morocco"
    assert table[1]["points"] == 6
    assert table[2]["team"] == "Scotland"
    assert table[3]["team"] == "Haiti"


def test_group_standings_empty():
    teams = [_team(n) for n in REAL_GROUPS["A"]]
    table = group_standings(teams, [])
    assert len(table) == 4
    for row in table:
        assert row["played"] == 0
        assert row["points"] == 0


def test_assign_pots():
    pots = assign_pots(TEAMS)
    assert len(pots["pot1"]) == 12
    assert len(pots["pot2"]) == 12
    assert len(pots["pot3"]) == 12
    assert len(pots["pot4"]) == 12

    for team in TEAMS:
        assert team in pots[f"pot{team['pot']}"]

    pot1_codes = {t["code"] for t in pots["pot1"]}
    assert "USA" in pot1_codes
    assert "MEX" in pot1_codes
    assert "CAN" in pot1_codes

    all_assigned = pots["pot1"] + pots["pot2"] + pots["pot3"] + pots["pot4"]
    assert len(all_assigned) == 48
    assert len({t["code"] for t in all_assigned}) == 48


def test_pot_field_totals():
    """Each pot field value appears exactly 12 times."""
    from collections import Counter
    counts = Counter(t["pot"] for t in TEAMS)
    assert counts[1] == 12
    assert counts[2] == 12
    assert counts[3] == 12
    assert counts[4] == 12


def test_draw_groups():
    random.seed(123)
    pots = assign_pots(TEAMS)
    groups = draw_groups(pots)

    assert len(groups) == 12
    all_teams = []
    for letter in GROUP_LETTERS:
        group = groups[letter]
        assert len(group) == 4
        all_teams.extend(group)

        conf_counts = {}
        for team in group:
            conf = team["confederation"]
            conf_counts[conf] = conf_counts.get(conf, 0) + 1
        assert conf_counts.get("UEFA", 0) <= 2
        for conf, count in conf_counts.items():
            if conf != "UEFA":
                assert count <= 1

    assert len(all_teams) == 48
    assert len({t["code"] for t in all_teams}) == 48


def test_generate_group_schedule():
    teams = [_team(n) for n in REAL_GROUPS["C"]]
    schedule = generate_group_schedule(teams)

    assert len(schedule) == 3
    for matchday in schedule:
        assert len(matchday) == 2

    names = {t["name"] for t in teams}
    for matchday in schedule:
        playing = set()
        for home, away in matchday:
            playing.add(home["name"])
            playing.add(away["name"])
        assert playing == names

    pairs_played = set()
    for matchday in schedule:
        for home, away in matchday:
            pair = tuple(sorted([home["name"], away["name"]]))
            assert pair not in pairs_played
            pairs_played.add(pair)
    assert len(pairs_played) == 6


def test_next_round():
    winners = [_team(n) for n in [
        "Spain", "France", "Brazil", "Argentina",
        "Germany", "England", "Portugal", "Netherlands",
        "Belgium", "Croatia", "USA", "Mexico",
        "Japan", "Morocco", "Colombia", "Uruguay",
    ]]
    name, matches, third = next_round(winners, "Round of 32")
    assert name == "Round of 16"
    assert len(matches) == 8
    assert third is None

    sf_winners = winners[:2]
    sf_losers = winners[2:4]
    name, matches, third = next_round(sf_winners, "Semifinals", sf_losers)
    assert name == "Final"
    assert len(matches) == 1
    assert third is not None
    assert third["round"] == "Third Place"


def test_build_knockout_bracket():
    from project import OTHER_GROUPS

    standings = {}
    for letter, names in REAL_GROUPS.items():
        teams = load_teams_by_name(names)
        fake_results = []
        for i, home_name in enumerate(names):
            for away_name in names[i + 1:]:
                fake_results.append({
                    "home": home_name,
                    "away": away_name,
                    "home_score": 1,
                    "away_score": 0,
                    "winner": home_name,
                })
        standings[letter] = group_standings(teams, fake_results)

    best_thirds = rank_third_place_teams(standings)
    assert len(best_thirds) == 8

    random.seed(42)
    matches = build_knockout_bracket(standings, best_thirds)
    assert len(matches) == 16
    for m in matches:
        assert m["round"] == "Round of 32"
        assert "home" in m and "away" in m

    team_names = [m["home"]["name"] for m in matches] + [m["away"]["name"] for m in matches]
    assert len(team_names) == 32
    assert len(set(team_names)) == 32

    thirds_names = {t["team"] for t in best_thirds}

    # Section 1.1: each OTHER_GROUPS winner is paired with a qualifying third
    other_winner_names = {standings[g][0]["team"] for g in OTHER_GROUPS}
    s11_matches = [m for m in matches if m["home"]["name"] in other_winner_names]
    assert len(s11_matches) == 8
    for m in s11_matches:
        assert m["away"]["name"] in thirds_names, (
            f"{m['home']['name']} should face a qualifying 3rd, got {m['away']['name']}"
        )
    # All 8 thirds used, none repeated
    assigned_thirds = [m["away"]["name"] for m in s11_matches]
    assert set(assigned_thirds) == thirds_names

    # Section 1.2: OTHER_GROUPS runners-up cross-pairings
    for g1, g2 in [("A", "B"), ("C", "D"), ("G", "H"), ("I", "J")]:
        expected_home = standings[g1][1]["team"]
        expected_away = standings[g2][1]["team"]
        assert any(
            m["home"]["name"] == expected_home and m["away"]["name"] == expected_away
            for m in matches
        ), f"Missing runner-up cross: 2{g1} vs 2{g2}"

    # Section 1.3: SPECIAL_GROUPS crosses
    for g1, g2 in [("E", "F"), ("F", "E"), ("K", "L"), ("L", "K")]:
        expected_home = standings[g1][0]["team"]
        expected_away = standings[g2][1]["team"]
        assert any(
            m["home"]["name"] == expected_home and m["away"]["name"] == expected_away
            for m in matches
        ), f"Missing special cross: 1{g1} vs 2{g2}"
