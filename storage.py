"""Database layer (SQLAlchemy Core).

Locally it uses a SQLite file; in the cloud it uses Supabase Postgres via the
connection string in Streamlit secrets. Tables are created automatically.
Only raw inputs are stored; outcomes and costs are always recomputed in game.py,
so a facilitator correction immediately fixes every score.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import (Column, DateTime, Integer, MetaData, String, Table,
                        UniqueConstraint, and_, create_engine, delete, insert,
                        select, update)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

import config as C

metadata = MetaData()

teams = Table(
    "th_teams", metadata,
    Column("group_id", Integer, primary_key=True),
    Column("cost_ratio", String(8), nullable=False),
    Column("updated_at", DateTime(timezone=True)),
)

triggers = Table(
    "th_triggers", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("group_id", Integer, nullable=False),
    Column("season", Integer, nullable=False),
    Column("from_round", Integer, nullable=False),
    Column("tau", Integer, nullable=False),
    Column("n_forecast", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True)),
    UniqueConstraint("group_id", "season", "from_round", name="uq_th_trigger"),
)

rounds = Table(
    "th_rounds", metadata,
    Column("group_id", Integer, primary_key=True),
    Column("season", Integer, primary_key=True),
    Column("round", Integer, primary_key=True),
    Column("forecast_sum", Integer, nullable=False),
    Column("total_sum", Integer),
    Column("envelope", Integer),
    Column("updated_at", DateTime(timezone=True)),
)

settings = Table(
    "th_settings", metadata,
    Column("key", String(64), primary_key=True),
    Column("value", String(256)),
)


def _now():
    return datetime.now(timezone.utc)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15})
    else:
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        eng = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5,
                            pool_recycle=300)
    metadata.create_all(eng)
    return eng


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
def get_setting(eng: Engine, key: str, default: str | None = None) -> str | None:
    with eng.connect() as c:
        v = c.execute(select(settings.c.value).where(settings.c.key == key)).scalar()
    return default if v is None else v


def set_setting(eng: Engine, key: str, value: str) -> None:
    with eng.begin() as c:
        n = c.execute(update(settings).where(settings.c.key == key)
                      .values(value=value)).rowcount
        if n == 0:
            try:
                with c.begin_nested():
                    c.execute(insert(settings).values(key=key, value=value))
            except IntegrityError:
                c.execute(update(settings).where(settings.c.key == key).values(value=value))


def current_season(eng: Engine) -> int:
    return int(get_setting(eng, "current_season", "1"))


# --------------------------------------------------------------------------
# Teams
# --------------------------------------------------------------------------
def get_team(eng: Engine, group_id: int) -> dict | None:
    with eng.connect() as c:
        r = c.execute(select(teams).where(teams.c.group_id == group_id)).mappings().first()
    return dict(r) if r else None


def set_team(eng: Engine, group_id: int, cost_ratio: str) -> None:
    assert cost_ratio in C.AA_COST_PER_UNIT
    with eng.begin() as c:
        n = c.execute(update(teams).where(teams.c.group_id == group_id)
                      .values(cost_ratio=cost_ratio, updated_at=_now())).rowcount
        if n == 0:
            c.execute(insert(teams).values(group_id=group_id, cost_ratio=cost_ratio,
                                           updated_at=_now()))


def delete_team(eng: Engine, group_id: int) -> None:
    """Remove a team and everything it entered."""
    with eng.begin() as c:
        c.execute(delete(rounds).where(rounds.c.group_id == group_id))
        c.execute(delete(triggers).where(triggers.c.group_id == group_id))
        c.execute(delete(teams).where(teams.c.group_id == group_id))


# --------------------------------------------------------------------------
# Triggers
# --------------------------------------------------------------------------
def get_triggers(eng: Engine, group_id: int, season: int) -> list[dict]:
    with eng.connect() as c:
        rs = c.execute(select(triggers).where(and_(triggers.c.group_id == group_id,
                                                   triggers.c.season == season))
                       .order_by(triggers.c.from_round)).mappings().all()
    return [dict(r) for r in rs]


def set_trigger(eng: Engine, group_id: int, season: int, from_round: int,
                tau: int, n_forecast: int) -> None:
    """Insert or replace the trigger that applies from `from_round` on."""
    with eng.begin() as c:
        cond = and_(triggers.c.group_id == group_id, triggers.c.season == season,
                    triggers.c.from_round == from_round)
        n = c.execute(update(triggers).where(cond)
                      .values(tau=tau, n_forecast=n_forecast, updated_at=_now())).rowcount
        if n == 0:
            c.execute(insert(triggers).values(group_id=group_id, season=season,
                                              from_round=from_round, tau=tau,
                                              n_forecast=n_forecast, updated_at=_now()))


def delete_trigger(eng: Engine, group_id: int, season: int, from_round: int) -> None:
    with eng.begin() as c:
        c.execute(delete(triggers).where(and_(triggers.c.group_id == group_id,
                                              triggers.c.season == season,
                                              triggers.c.from_round == from_round)))


# --------------------------------------------------------------------------
# Rounds
# --------------------------------------------------------------------------
def get_rounds(eng: Engine, group_id: int, season: int) -> list[dict]:
    with eng.connect() as c:
        rs = c.execute(select(rounds).where(and_(rounds.c.group_id == group_id,
                                                 rounds.c.season == season))
                       .order_by(rounds.c.round)).mappings().all()
    return [dict(r) for r in rs]


def add_forecast(eng: Engine, group_id: int, season: int, rnd: int, forecast_sum: int) -> bool:
    """Start a round. Returns False if this round already exists (double tap)."""
    try:
        with eng.begin() as c:
            c.execute(insert(rounds).values(group_id=group_id, season=season, round=rnd,
                                            forecast_sum=forecast_sum, updated_at=_now()))
        return True
    except IntegrityError:
        return False


def _round_cond(group_id, season, rnd):
    return and_(rounds.c.group_id == group_id, rounds.c.season == season,
                rounds.c.round == rnd)


def set_total(eng: Engine, group_id: int, season: int, rnd: int, total_sum: int) -> None:
    with eng.begin() as c:
        c.execute(update(rounds).where(_round_cond(group_id, season, rnd))
                  .values(total_sum=total_sum, updated_at=_now()))


def set_envelope(eng: Engine, group_id: int, season: int, rnd: int, envelope: int) -> None:
    with eng.begin() as c:
        c.execute(update(rounds).where(_round_cond(group_id, season, rnd))
                  .values(envelope=envelope, updated_at=_now()))


def admin_save_round(eng: Engine, group_id: int, season: int, rnd: int,
                     forecast_sum: int, total_sum: int | None, envelope: int | None) -> None:
    with eng.begin() as c:
        n = c.execute(update(rounds).where(_round_cond(group_id, season, rnd))
                      .values(forecast_sum=forecast_sum, total_sum=total_sum,
                              envelope=envelope, updated_at=_now())).rowcount
        if n == 0:
            c.execute(insert(rounds).values(group_id=group_id, season=season, round=rnd,
                                            forecast_sum=forecast_sum, total_sum=total_sum,
                                            envelope=envelope, updated_at=_now()))


def delete_round(eng: Engine, group_id: int, season: int, rnd: int) -> None:
    with eng.begin() as c:
        c.execute(delete(rounds).where(_round_cond(group_id, season, rnd)))


def undo_last(eng: Engine, group_id: int, season: int) -> str:
    """Undo the team's most recent entry in this season. Returns what was undone."""
    rs = get_rounds(eng, group_id, season)
    trs = get_triggers(eng, group_id, season)
    if rs:
        last = rs[-1]
        k = last["round"]
        # A recalibration made after round k is newer than round k's data.
        if any(t["from_round"] == k + 1 for t in trs) and last["total_sum"] is not None:
            delete_trigger(eng, group_id, season, k + 1)
            return "trigger change"
        if last["envelope"] is not None:
            set_envelope_null(eng, group_id, season, k)
            return f"envelope of round {k}"
        if last["total_sum"] is not None:
            with eng.begin() as c:
                c.execute(update(rounds).where(_round_cond(group_id, season, k))
                          .values(total_sum=None, updated_at=_now()))
            return f"total of round {k}"
        delete_round(eng, group_id, season, k)
        return f"forecast of round {k}"
    if trs:
        delete_trigger(eng, group_id, season, trs[-1]["from_round"])
        return "season set-up"
    return "nothing"


def set_envelope_null(eng: Engine, group_id: int, season: int, rnd: int) -> None:
    with eng.begin() as c:
        c.execute(update(rounds).where(_round_cond(group_id, season, rnd))
                  .values(envelope=None, updated_at=_now()))


# --------------------------------------------------------------------------
# Bulk
# --------------------------------------------------------------------------
def load_all(eng: Engine) -> dict[str, pd.DataFrame]:
    with eng.connect() as c:
        t = pd.DataFrame(c.execute(select(teams.c.group_id, teams.c.cost_ratio)).mappings().all(),
                         columns=["group_id", "cost_ratio"])
        tr = pd.DataFrame(c.execute(select(triggers.c.group_id, triggers.c.season,
                                           triggers.c.from_round, triggers.c.tau,
                                           triggers.c.n_forecast)).mappings().all(),
                          columns=["group_id", "season", "from_round", "tau", "n_forecast"])
        r = pd.DataFrame(c.execute(select(rounds.c.group_id, rounds.c.season, rounds.c.round,
                                          rounds.c.forecast_sum, rounds.c.total_sum,
                                          rounds.c.envelope)
                                   .order_by(rounds.c.group_id, rounds.c.season,
                                             rounds.c.round)).mappings().all(),
                         columns=["group_id", "season", "round", "forecast_sum",
                                  "total_sum", "envelope"])
    return {"teams": t, "triggers": tr, "rounds": r}


def reset_season(eng: Engine, season: int) -> None:
    with eng.begin() as c:
        c.execute(delete(rounds).where(rounds.c.season == season))
        c.execute(delete(triggers).where(triggers.c.season == season))


def reset_all(eng: Engine) -> None:
    with eng.begin() as c:
        c.execute(delete(rounds))
        c.execute(delete(triggers))
        c.execute(delete(teams))
    set_setting(eng, "current_season", "1")
