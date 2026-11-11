"""Pure game logic: no Streamlit, no database. Fully unit-tested."""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

import config as C

HIT, MISS, FA, CN = "hit", "miss", "false alarm", "correct negative"
OUTCOMES = [HIT, MISS, FA, CN]
OUTCOME_SHORT = {HIT: "H", MISS: "M", FA: "FA", CN: "CN"}


# --------------------------------------------------------------------------
# Single-round rules
# --------------------------------------------------------------------------
def triggered(forecast_sum: int, tau: int) -> bool:
    """A team activates when the forecast dice add up to AT LEAST tau."""
    return forecast_sum >= tau


def is_flood(total_sum: int) -> bool:
    return total_sum >= C.FLOOD_THRESHOLD


def classify(trig: bool, flood: bool) -> str:
    if trig and flood:
        return HIT
    if trig and not flood:
        return FA
    if flood:
        return MISS
    return CN


def needs_envelope(season: int, outcome: str) -> bool:
    """In season 2 a team draws an envelope only when it activated and a flood came."""
    return season == 2 and outcome == HIT


def round_result(outcome: str, cost_ratio: str, season: int, envelope: int | None = None) -> dict:
    """Costs and people reached for one completed round.

    Season 1: every activation reaches all 30,000 people.
    Season 2: a hit reaches the number on the envelope; the rest need response.
              A false alarm costs a full activation (30,000 people).
    """
    c = C.AA_COST_PER_UNIT[cost_ratio]
    full_units = C.PEOPLE_AFFECTED / C.UNIT
    reached = 0
    aa = resp = 0.0
    if outcome == HIT:
        if season == 1:
            reached = C.PEOPLE_AFFECTED
        else:
            if envelope is None:
                raise ValueError("Season 2 hit needs an envelope value")
            reached = int(envelope)
        aa = reached / C.UNIT * c
        resp = (C.PEOPLE_AFFECTED - reached) / C.UNIT * C.RESPONSE_COST_PER_UNIT
    elif outcome == FA:
        aa = full_units * c
    elif outcome == MISS:
        resp = full_units * C.RESPONSE_COST_PER_UNIT
    return {"aa_cost": aa, "response_cost": resp, "total_cost": aa + resp,
            "people_reached": reached,
            "people_affected": C.PEOPLE_AFFECTED if outcome in (HIT, MISS) else 0}


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------
def forecast_range(n_forecast: int) -> tuple[int, int]:
    return n_forecast, 6 * n_forecast


def total_range(n_forecast: int, forecast_sum: int) -> tuple[int, int]:
    n_out = C.TOTAL_DICE - n_forecast
    return forecast_sum + n_out, forecast_sum + 6 * n_out


def tau_range(n_forecast: int) -> tuple[int, int]:
    """Sensible trigger values: tau = n means 'always activate', 6n+1 'never activate'."""
    return n_forecast, 6 * n_forecast + 1


# --------------------------------------------------------------------------
# Theory: exact probabilities from dice enumeration
# --------------------------------------------------------------------------
@lru_cache(maxsize=None)
def sum_dist(k: int) -> dict[int, float]:
    dist = {0: 1.0}
    for _ in range(k):
        new: dict[int, float] = {}
        for s, p in dist.items():
            for face in range(1, 7):
                new[s + face] = new.get(s + face, 0.0) + p / 6
        dist = new
    return dist


@lru_cache(maxsize=None)
def trigger_stats(n_forecast: int, tau: int) -> dict:
    """POD, FAR, activation rate and per-outcome probabilities for one trigger."""
    f_dist = sum_dist(n_forecast)
    o_dist = sum_dist(C.TOTAL_DICE - n_forecast)
    p = {HIT: 0.0, MISS: 0.0, FA: 0.0, CN: 0.0}
    for fs, pf in f_dist.items():
        trig = fs >= tau
        for os_, po in o_dist.items():
            p[classify(trig, fs + os_ >= C.FLOOD_THRESHOLD)] += pf * po
    p_flood = p[HIT] + p[MISS]
    p_trig = p[HIT] + p[FA]
    return {
        "tau": tau,
        "n_forecast": n_forecast,
        "p_hit": p[HIT], "p_miss": p[MISS], "p_fa": p[FA], "p_cn": p[CN],
        "p_flood": p_flood,
        "activation_rate": p_trig,
        "pod": p[HIT] / p_flood if p_flood else float("nan"),
        "far": p[FA] / p_trig if p_trig else float("nan"),
    }


def flood_probability() -> float:
    return trigger_stats(C.SEASON1_FORECAST_DICE, 0)["p_flood"]


def expected_reached(n_forecast: int, envelope_probs: dict | None = None) -> float:
    probs = (envelope_probs or C.ENVELOPE_PROBS)[n_forecast]
    return sum(v * p for v, p in probs.items()) / sum(probs.values())


def expected_cost_per_round(n_forecast: int, tau: int, cost_ratio: str, season: int,
                            envelope_probs: dict | None = None) -> float:
    s = trigger_stats(n_forecast, tau)
    c = C.AA_COST_PER_UNIT[cost_ratio]
    full = C.PEOPLE_AFFECTED / C.UNIT
    if season == 1:
        hit_cost = full * c
    else:
        r = expected_reached(n_forecast, envelope_probs) / C.UNIT
        hit_cost = r * c + (full - r) * C.RESPONSE_COST_PER_UNIT
    return (s["p_hit"] * hit_cost
            + s["p_fa"] * full * c
            + s["p_miss"] * full * C.RESPONSE_COST_PER_UNIT)


def theory_table(n_forecast: int) -> pd.DataFrame:
    lo, hi = tau_range(n_forecast)
    return pd.DataFrame([trigger_stats(n_forecast, t) for t in range(lo, hi + 1)])


# --------------------------------------------------------------------------
# Evaluating played rounds
# --------------------------------------------------------------------------
ROUND_COLS = ["group_id", "season", "round", "forecast_sum", "total_sum", "envelope"]
TRIGGER_COLS = ["group_id", "season", "from_round", "tau", "n_forecast"]
TEAM_COLS = ["group_id", "cost_ratio"]


def effective_trigger(triggers: pd.DataFrame, group_id: int, season: int, rnd: int):
    """Latest trigger whose from_round <= rnd, or None."""
    if triggers is None or triggers.empty:
        return None
    t = triggers[(triggers.group_id == group_id) & (triggers.season == season)
                 & (triggers.from_round <= rnd)]
    if t.empty:
        return None
    return t.sort_values("from_round").iloc[-1]


def evaluate(rounds: pd.DataFrame, teams: pd.DataFrame, triggers: pd.DataFrame) -> pd.DataFrame:
    """One row per entered round with trigger, outcome, costs and a status.

    status: 'forecast' (only forecast entered), 'envelope' (hit awaiting envelope),
            'done' (counts in the scores).
    """
    out_cols = ROUND_COLS + ["cost_ratio", "tau", "n_forecast", "triggered", "flood",
                             "outcome", "status", "aa_cost", "response_cost",
                             "total_cost", "people_reached", "people_affected"]
    if rounds is None or rounds.empty:
        return pd.DataFrame(columns=out_cols)
    ratio = dict(zip(teams.group_id, teams.cost_ratio)) if teams is not None else {}
    rows = []
    for r in rounds.itertuples(index=False):
        g, s, k = int(r.group_id), int(r.season), int(r.round)
        trig_row = effective_trigger(triggers, g, s, k)
        cr = ratio.get(g)
        row = {"group_id": g, "season": s, "round": k,
               "forecast_sum": r.forecast_sum, "total_sum": r.total_sum,
               "envelope": r.envelope, "cost_ratio": cr,
               "tau": None, "n_forecast": None, "triggered": None, "flood": None,
               "outcome": None, "status": "forecast",
               "aa_cost": 0.0, "response_cost": 0.0, "total_cost": 0.0,
               "people_reached": 0, "people_affected": 0}
        if trig_row is not None:
            row["tau"] = int(trig_row.tau)
            row["n_forecast"] = int(trig_row.n_forecast)
            if pd.notna(r.forecast_sum):
                row["triggered"] = triggered(int(r.forecast_sum), int(trig_row.tau))
        if trig_row is not None and cr is not None and pd.notna(r.forecast_sum) \
                and pd.notna(r.total_sum):
            fl = is_flood(int(r.total_sum))
            oc = classify(row["triggered"], fl)
            row["flood"], row["outcome"] = fl, oc
            env = None if pd.isna(r.envelope) else int(r.envelope)
            if needs_envelope(s, oc) and env is None:
                row["status"] = "envelope"
            else:
                row["status"] = "done"
                row.update(round_result(oc, cr, s, env))
        rows.append(row)
    return pd.DataFrame(rows, columns=out_cols)


def summarise(ev: pd.DataFrame, triggers: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-team totals over the rows in `ev` (filter seasons beforehand)."""
    cols = ["group_id", "cost_ratio", "rounds", "hits", "misses", "false_alarms",
            "correct_negatives", "pod", "far", "aa_cost", "response_cost",
            "total_cost", "people_reached", "people_affected", "trigger"]
    done = ev[ev.status == "done"] if not ev.empty else ev
    if done.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for (g, cr), d in done.groupby(["group_id", "cost_ratio"]):
        h = int((d.outcome == HIT).sum())
        m = int((d.outcome == MISS).sum())
        fa = int((d.outcome == FA).sum())
        cn = int((d.outcome == CN).sum())
        rows.append({
            "group_id": int(g), "cost_ratio": cr, "rounds": len(d),
            "hits": h, "misses": m, "false_alarms": fa, "correct_negatives": cn,
            "pod": h / (h + m) if h + m else float("nan"),
            "far": fa / (h + fa) if h + fa else float("nan"),
            "aa_cost": d.aa_cost.sum(), "response_cost": d.response_cost.sum(),
            "total_cost": d.total_cost.sum(),
            "people_reached": int(d.people_reached.sum()),
            "people_affected": int(d.people_affected.sum()),
            "trigger": trigger_label(triggers, int(g), sorted(d.season.unique())),
        })
    return pd.DataFrame(rows, columns=cols).sort_values(["total_cost", "rounds"])


def trigger_label(triggers: pd.DataFrame | None, group_id: int, seasons) -> str:
    """Human label like 'τ 14 → 15' or 'Short, τ 22'."""
    if triggers is None or triggers.empty:
        return ""
    parts = []
    for s in seasons:
        t = triggers[(triggers.group_id == group_id) & (triggers.season == s)] \
            .sort_values("from_round")
        if t.empty:
            continue
        taus = " → ".join(str(int(x)) for x in t.tau)
        lbl = f"τ {taus}"
        if s == 2:
            lbl = f"{C.LEAD_TIME_SHORT.get(int(t.n_forecast.iloc[0]), '')}, {lbl}"
        parts.append(lbl if len(seasons) == 1 else f"S{s}: {lbl}")
    return " | ".join(parts)
