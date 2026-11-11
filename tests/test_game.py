import os
import sys
import threading

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as C  # noqa: E402
import game as G  # noqa: E402
import storage as S  # noqa: E402


# ---------------------------------------------------------------- rules
def test_trigger_is_inclusive():
    assert G.triggered(14, 14)
    assert not G.triggered(13, 14)


def test_flood_threshold():
    assert G.is_flood(22) and not G.is_flood(21)


@pytest.mark.parametrize("trig,flood,out", [(True, True, G.HIT), (True, False, G.FA),
                                            (False, True, G.MISS), (False, False, G.CN)])
def test_classify(trig, flood, out):
    assert G.classify(trig, flood) == out


@pytest.mark.parametrize("ratio,c", [("low", 1), ("high", 2)])
def test_costs_season1(ratio, c):
    assert G.round_result(G.HIT, ratio, 1)["total_cost"] == 3 * c
    assert G.round_result(G.HIT, ratio, 1)["people_reached"] == 30_000
    assert G.round_result(G.FA, ratio, 1)["total_cost"] == 3 * c
    assert G.round_result(G.MISS, ratio, 1)["total_cost"] == 9
    assert G.round_result(G.CN, ratio, 1)["total_cost"] == 0


@pytest.mark.parametrize("ratio,c", [("low", 1), ("high", 2)])
@pytest.mark.parametrize("env", [10_000, 20_000, 30_000])
def test_costs_season2_hit(ratio, c, env):
    r = G.round_result(G.HIT, ratio, 2, env)
    units = env / 10_000
    assert r["aa_cost"] == units * c
    assert r["response_cost"] == (3 - units) * 3
    assert r["people_reached"] == env


def test_season2_false_alarm_pays_full():
    assert G.round_result(G.FA, "low", 2)["total_cost"] == 3
    assert G.round_result(G.FA, "high", 2)["total_cost"] == 6


def test_season2_hit_needs_envelope():
    with pytest.raises(ValueError):
        G.round_result(G.HIT, "low", 2)
    assert G.needs_envelope(2, G.HIT)
    assert not G.needs_envelope(1, G.HIT)
    assert not G.needs_envelope(2, G.FA)


def test_ranges():
    assert G.forecast_range(4) == (4, 24)
    assert G.total_range(4, 15) == (17, 27)
    assert G.total_range(5, 20) == (21, 26)
    assert G.total_range(3, 10) == (13, 28)


# ---------------------------------------------------------------- theory
def test_flood_probability_about_45pct():
    assert abs(G.flood_probability() - 0.4536) < 0.001


def test_theory_extremes():
    always = G.trigger_stats(4, 4)
    assert always["pod"] == pytest.approx(1) and always["activation_rate"] == pytest.approx(1)
    never = G.trigger_stats(4, 25)
    assert never["activation_rate"] == 0


def test_flood_probability_same_for_all_lead_times():
    for n in (3, 4, 5):
        assert G.trigger_stats(n, 0)["p_flood"] == pytest.approx(G.flood_probability())


def test_theory_matches_brute_force():
    import itertools
    hits = fas = floods = 0
    for dice in itertools.product(range(1, 7), repeat=6):
        f, t = sum(dice[:4]), sum(dice)
        floods += t >= 22
        hits += f >= 15 and t >= 22
        fas += f >= 15 and t < 22
    s = G.trigger_stats(4, 15)
    assert s["pod"] == pytest.approx(hits / floods)
    assert s["far"] == pytest.approx(fas / (hits + fas))


def test_best_trigger_season1():
    best = {r: min(range(4, 26), key=lambda t: G.expected_cost_per_round(4, t, r, 1))
            for r in ("low", "high")}
    assert best["low"] < best["high"]   # cheaper AA -> act more often


# ---------------------------------------------------------------- evaluate
def _frames():
    teams = pd.DataFrame({"group_id": [1, 2], "cost_ratio": ["low", "high"]})
    trig = pd.DataFrame({"group_id": [1, 1, 2], "season": [1, 1, 2], "from_round": [1, 5, 1],
                         "tau": [14, 18, 20], "n_forecast": [4, 4, 5]})
    rounds = pd.DataFrame([
        (1, 1, 1, 15, 25, None),   # hit, low -> 3
        (1, 1, 5, 15, 25, None),   # tau now 18 -> miss -> 9
        (1, 1, 6, 12, None, None),  # in progress
        (2, 2, 1, 21, 24, None),   # hit, waiting for envelope
        (2, 2, 2, 22, 23, 20_000),  # hit with envelope, high: 2*2 + 1*3 = 7
        (2, 2, 3, 20, 21, None),   # FA high season 2: 6
    ], columns=G.ROUND_COLS)
    return teams, trig, rounds


def test_evaluate_and_summary():
    teams, trig, rounds = _frames()
    ev = G.evaluate(rounds, teams, trig)
    assert list(ev.status) == ["done", "done", "forecast", "envelope", "done", "done"]
    assert list(ev.outcome[:2]) == [G.HIT, G.MISS]
    assert list(ev.total_cost) == [3, 9, 0, 0, 7, 6]
    summ = G.summarise(ev, trig).set_index("group_id")
    assert summ.loc[1, "total_cost"] == 12 and summ.loc[1, "rounds"] == 2
    assert summ.loc[1, "pod"] == 0.5
    assert summ.loc[2, "far"] == 0.5
    assert summ.loc[2, "people_reached"] == 20_000
    assert summ.loc[1, "trigger"] == "τ 14 → 18"
    assert summ.loc[2, "trigger"] == "Short, τ 20"


# ---------------------------------------------------------------- storage
@pytest.fixture
def eng(tmp_path):
    return S.make_engine(f"sqlite:///{tmp_path / 't.db'}")


def test_storage_flow_and_undo(eng):
    S.set_team(eng, 1, "low")
    S.set_trigger(eng, 1, 1, 1, 14, 4)
    assert S.add_forecast(eng, 1, 1, 1, 15)
    assert not S.add_forecast(eng, 1, 1, 1, 15)      # double tap is ignored
    S.set_total(eng, 1, 1, 1, 25)
    assert S.undo_last(eng, 1, 1) == "total of round 1"
    assert S.undo_last(eng, 1, 1) == "forecast of round 1"
    assert S.undo_last(eng, 1, 1) == "season set-up"
    assert S.get_triggers(eng, 1, 1) == []


def test_undo_recalibration(eng):
    S.set_team(eng, 1, "low")
    S.set_trigger(eng, 1, 1, 1, 14, 4)
    for k in range(1, 5):
        S.add_forecast(eng, 1, 1, k, 15)
        S.set_total(eng, 1, 1, k, 20)
    S.set_trigger(eng, 1, 1, 5, 16, 4)
    assert S.undo_last(eng, 1, 1) == "trigger change"
    assert len(S.get_triggers(eng, 1, 1)) == 1


def test_undo_envelope(eng):
    S.set_team(eng, 1, "low")
    S.set_trigger(eng, 1, 2, 1, 14, 4)
    S.add_forecast(eng, 1, 2, 1, 15)
    S.set_total(eng, 1, 2, 1, 25)
    S.set_envelope(eng, 1, 2, 1, 20_000)
    assert S.undo_last(eng, 1, 2) == "envelope of round 1"


def test_settings_and_reset(eng):
    assert S.current_season(eng) == 1
    S.set_setting(eng, "current_season", "2")
    assert S.current_season(eng) == 2
    S.set_team(eng, 3, "high")
    S.reset_all(eng)
    assert S.load_all(eng)["teams"].empty and S.current_season(eng) == 1


def test_six_teams_concurrently(eng):
    """Six teams play a full season at the same time; nothing is lost."""
    import random
    errors = []

    def play(g):
        try:
            rnd = random.Random(g)
            S.set_team(eng, g, "low" if g % 2 else "high")
            S.set_trigger(eng, g, 1, 1, 14, 4)
            for k in range(1, 9):
                f = sum(rnd.randint(1, 6) for _ in range(4))
                S.add_forecast(eng, g, 1, k, f)
                S.set_total(eng, g, 1, k, f + sum(rnd.randint(1, 6) for _ in range(2)))
                S.load_all(eng)   # dashboard reading at the same time
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=play, args=(g,)) for g in range(1, 7)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    data = S.load_all(eng)
    ev = G.evaluate(data["rounds"], data["teams"], data["triggers"])
    assert len(ev) == 48 and (ev.status == "done").all()
