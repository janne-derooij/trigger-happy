"""To trigger, or not to trigger — live game app.

Views (choose with ?view=...):
  team       (default) phone view for teams: set-up, enter dice, see outcome
  dashboard  projector view: live scoreboard, trigger helper, join QR, research
  admin      facilitator: current season, corrections, resets, export
"""
from __future__ import annotations

import io

import altair as alt
import pandas as pd
import streamlit as st

import config as C
import game as G
import storage as S

st.set_page_config(page_title="To trigger, or not to trigger", page_icon="🎲",
                   layout="wide" if st.query_params.get("view") in ("dashboard", "admin")
                   else "centered")

# Colours (validated reference palette; outcome colours = status palette)
OUTCOME_COLOURS = {G.HIT: "#0ca30c", G.MISS: "#d03b3b", G.FA: "#ec835a",
                   G.CN: "#c9c8c2", "in progress": "#86b6ef"}
GROUP_COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300",
                 "#6250d6", "#e34948"]
RATIO_COLOURS = {"low": "#2a78d6", "high": "#eb6834"}


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------
def _secret(path: list[str], default=None):
    try:
        v = st.secrets
        for p in path:
            v = v[p]
        return v
    except Exception:
        return default


@st.cache_resource
def engine():
    url = _secret(["database", "url"], "sqlite:///trigger_happy.db")
    return S.make_engine(url)


def admin_password() -> str:
    return _secret(["admin_password"], "admin")


def fmt_people(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def coins(x) -> str:
    return f"{x:g}"


def group_label(g) -> str:
    return f"Group {int(g)}"


def group_colour_scale(groups):
    groups = sorted(int(g) for g in groups)
    return alt.Scale(domain=[group_label(g) for g in groups],
                     range=[GROUP_COLOURS[(g - 1) % len(GROUP_COLOURS)] for g in groups])


def load_evaluated():
    data = S.load_all(engine())
    ev = G.evaluate(data["rounds"], data["teams"], data["triggers"])
    return data, ev


# --------------------------------------------------------------------------
# TEAM VIEW
# --------------------------------------------------------------------------
def team_view():
    eng = engine()
    g = st.query_params.get("group")
    if g is None:
        st.title("🎲 To trigger, or not to trigger")
        st.write("Which group are you?")
        cols = st.columns(3)
        for i in range(1, C.NUM_GROUPS + 1):
            if cols[(i - 1) % 3].button(f"Group {i}", width="stretch", key=f"g{i}"):
                st.query_params["group"] = str(i)
                st.rerun()
        return
    group = int(g)
    season = S.current_season(eng)

    top = st.columns([3, 1])
    top[0].markdown(f"### Group {group} · Season {season}")
    if top[1].button("Switch group"):
        del st.query_params["group"]
        st.rerun()

    team = S.get_team(eng, group)
    if team is None:
        register_team(group)
        return
    st.caption(C.COST_RATIO_LABEL[team["cost_ratio"]])

    trigs = S.get_triggers(eng, group, season)
    if not trigs:
        season_setup(group, season)
        return

    rounds = S.get_rounds(eng, group, season)
    play_round(group, season, team, trigs, rounds)


def register_team(group: int):
    st.subheader("Welcome! Which cost setting did you get?")
    with st.form("register"):
        ratio = st.radio("Cost of anticipatory action", ["low", "high"],
                         format_func=lambda x: C.COST_RATIO_LABEL[x])
        if st.form_submit_button("Confirm", type="primary", width="stretch"):
            S.set_team(engine(), group, ratio)
            st.rerun()


def theory_hint(n_forecast: int, tau: int):
    s = G.trigger_stats(n_forecast, tau)
    st.caption(f"With τ = {tau}: you activate in about {s['activation_rate']:.0%} of rounds · "
               f"POD ≈ {s['pod']:.0%} · FAR ≈ {s['far']:.0%}"
               if s["activation_rate"] > 0 else f"With τ = {tau} you never activate.")


def season_setup(group: int, season: int):
    st.subheader(f"Set up season {season}")
    if season == 1:
        n = C.SEASON1_FORECAST_DICE
        st.write(f"You play with **{n} forecast dice** and **{C.TOTAL_DICE - n} outcome dice**.")
    else:
        n = st.radio("Choose your lead time", list(C.LEAD_TIMES),
                     index=1, format_func=lambda x: C.LEAD_TIMES[x])
    lo, hi = G.tau_range(n)
    tau = st.number_input(f"Trigger τ: activate when the {n} forecast dice add up to at least…",
                          min_value=lo, max_value=hi, value=None, step=1,
                          placeholder=f"a number from {lo} to {hi}")
    if tau is not None:
        theory_hint(n, int(tau))
    st.info(f"You can change τ once, after round {C.RECALIBRATE_AFTER_ROUND}."
            + (" The lead time stays fixed for the season." if season == 2 else ""))
    if st.button("Lock in my trigger", type="primary", width="stretch",
                 disabled=tau is None):
        S.set_trigger(engine(), group, season, 1, int(tau), n)
        st.rerun()


def outcome_banner(outcome: str, res: dict | None, season: int, rnd: int):
    text = {G.HIT: "✅ Hit: you activated and the flood came.",
            G.MISS: "❌ Miss: a flood, and you did not activate.",
            G.FA: "⚠️ False alarm: you activated, but no flood came.",
            G.CN: "😌 Correct negative: no activation, no flood."}[outcome]
    if res is not None:
        text += (f"\n\nRound {rnd} cost: **{coins(res['total_cost'])} coins** "
                 f"(AA {coins(res['aa_cost'])}, response {coins(res['response_cost'])})")
        if outcome in (G.HIT, G.MISS):
            text += f" · reached ahead of the flood: **{fmt_people(res['people_reached'])}** of 30.000"
    {G.HIT: st.success, G.MISS: st.error, G.FA: st.warning, G.CN: st.info}[outcome](text)


def play_round(group: int, season: int, team: dict, trigs: list[dict], rounds: list[dict]):
    eng = engine()
    trig_df = pd.DataFrame(trigs)
    ev = G.evaluate(pd.DataFrame(rounds, columns=G.ROUND_COLS),
                    pd.DataFrame([team])[G.TEAM_COLS], trig_df)
    done = ev[ev.status == "done"]
    current = ev.iloc[-1] if (not ev.empty and ev.iloc[-1].status != "done") else None
    next_round = len(ev) + 1 if current is None else int(current["round"])
    n = int(trigs[0]["n_forecast"])
    t_now = G.effective_trigger(trig_df, group, season, next_round)
    tau = int(t_now.tau)

    # Progress line
    st.progress(min(len(done), C.ROUNDS_PER_SEASON) / C.ROUNDS_PER_SEASON,
                text=f"{len(done)} of {C.ROUNDS_PER_SEASON} rounds played · "
                     f"trigger τ = {tau} on {n} forecast dice · "
                     f"season cost so far: {coins(done.total_cost.sum())} coins")

    # Result of the round just finished
    if current is None and not done.empty:
        last = done.iloc[-1]
        res = {k: last[k] for k in ("aa_cost", "response_cost", "total_cost", "people_reached")}
        outcome_banner(last.outcome, res, season, int(last["round"]))

    if current is None and next_round > C.ROUNDS_PER_SEASON:
        st.balloons() if st.session_state.get("_celebrated") != (group, season) else None
        st.session_state["_celebrated"] = (group, season)
        st.subheader(f"Season {season} finished 🎉")
        st.metric("Total season cost", f"{coins(done.total_cost.sum())} coins")
        history(ev)
        undo_button(group, season)
        return

    # Optional recalibration between round 4 and 5
    if (current is None and next_round == C.RECALIBRATE_AFTER_ROUND + 1
            and not any(t["from_round"] == next_round for t in trigs)):
        with st.expander("🔁 Recalibrate: change your trigger now? (optional, only once)"):
            lo, hi = G.tau_range(n)
            new_tau = st.number_input("New τ", min_value=lo, max_value=hi, value=tau, step=1)
            theory_hint(n, int(new_tau))
            if st.button("Change trigger for rounds 5–8", width="stretch"):
                S.set_trigger(eng, group, season, next_round, int(new_tau), n)
                st.rerun()

    st.markdown(f"## Round {next_round}")

    if current is None:
        # Step 1: forecast
        lo, hi = G.forecast_range(n)
        with st.form(f"forecast_{season}_{next_round}", clear_on_submit=True):
            f = st.number_input(f"1️⃣ Roll the {n} forecast dice. Their sum:",
                                min_value=lo, max_value=hi, value=None, step=1,
                                placeholder=f"{lo}–{hi}")
            if st.form_submit_button("Submit forecast", type="primary", width="stretch"):
                if f is None:
                    st.error("Enter the forecast sum first.")
                else:
                    S.add_forecast(eng, group, season, next_round, int(f))
                    st.rerun()
    else:
        fsum = int(current.forecast_sum)
        if current.triggered:
            st.error(f"🚨 **ACTIVATE!** Forecast {fsum} ≥ τ {tau}. Pay for anticipatory action.")
        else:
            st.info(f"No activation. Forecast {fsum} < τ {tau}.")

        if pd.isna(current.total_sum):
            # Step 2: total
            lo, hi = G.total_range(n, fsum)
            n_out = C.TOTAL_DICE - n
            with st.form(f"total_{season}_{next_round}", clear_on_submit=True):
                t = st.number_input(
                    f"2️⃣ Roll the {n_out} outcome {'die' if n_out == 1 else 'dice'}. "
                    f"Sum of ALL {C.TOTAL_DICE} dice:",
                    min_value=lo, max_value=hi, value=None, step=1, placeholder=f"{lo}–{hi}")
                if st.form_submit_button("Submit total", type="primary", width="stretch"):
                    if t is None:
                        st.error("Enter the total of all dice first.")
                    else:
                        S.set_total(eng, group, season, next_round, int(t))
                        st.rerun()
        else:
            # Step 3 (season 2 hit): envelope
            outcome_banner(current.outcome, None, season, next_round)
            st.markdown("3️⃣ **Draw an envelope.** How many people did you reach in time?")
            cols = st.columns(len(C.ENVELOPE_VALUES))
            for col, v in zip(cols, C.ENVELOPE_VALUES):
                if col.button(fmt_people(v), width="stretch", key=f"env{v}"):
                    S.set_envelope(eng, group, season, next_round, v)
                    st.rerun()

    st.divider()
    history(ev)
    undo_button(group, season)


def history(ev: pd.DataFrame):
    done = ev[ev.status == "done"]
    if done.empty:
        return
    with st.expander("Our rounds so far"):
        tbl = pd.DataFrame({
            "Round": done["round"].astype(int),
            "τ": done.tau.astype(int),
            "Forecast": done.forecast_sum.astype(int),
            "Total": done.total_sum.astype(int),
            "Outcome": done.outcome,
            "Reached": done.people_reached.map(fmt_people),
            "Cost": done.total_cost,
        })
        st.dataframe(tbl, hide_index=True, width="stretch")


def undo_button(group: int, season: int):
    key = f"confirm_undo_{group}_{season}"
    if not st.session_state.get(key):
        if st.button("↩️ Typo? Undo last entry", key=f"undo_{group}_{season}"):
            st.session_state[key] = True
            st.rerun()
    else:
        st.warning("Undo your most recent entry?")
        c1, c2 = st.columns(2)
        if c1.button("Yes, undo", type="primary", width="stretch"):
            what = S.undo_last(engine(), group, season)
            st.session_state[key] = False
            st.toast(f"Undid: {what}")
            st.rerun()
        if c2.button("Cancel", width="stretch"):
            st.session_state[key] = False
            st.rerun()


# --------------------------------------------------------------------------
# DASHBOARD VIEW
# --------------------------------------------------------------------------
def dashboard_view():
    hdr = st.columns([4, 3, 2])
    hdr[0].markdown("## 🎲 To trigger, or not to trigger")
    mode = hdr[1].segmented_control(
        "View", ["Scoreboard", "Trigger helper", "Join", "Research"],
        default="Scoreboard", label_visibility="collapsed", key="dash_mode")
    if mode == "Scoreboard":
        choice = hdr[2].segmented_control(
            "Season", ["Current", "Season 1", "Season 2", "Total"], default="Current",
            label_visibility="collapsed", key="dash_season")
        live_scoreboard(choice or "Current")
    elif mode == "Trigger helper":
        trigger_helper()
    elif mode == "Join":
        join_screen()
    elif mode == "Research":
        if require_admin("research"):
            research_view()


@st.fragment(run_every=C.DASHBOARD_REFRESH_SECONDS)
def live_scoreboard(choice: str):
    data, ev = load_evaluated()
    cur = S.current_season(engine())
    seasons = {"Current": [cur], "Season 1": [1], "Season 2": [2], "Total": [1, 2]}[choice]
    ev = ev[ev.season.isin(seasons)]
    teams = data["teams"]
    if teams.empty:
        st.info("Waiting for teams to join… (open the **Join** view to show the QR code)")
        return

    summ = G.summarise(ev, data["triggers"])
    done = ev[ev.status == "done"]

    # KPI strip
    k = st.columns(5)
    k[0].metric("Season" if len(seasons) == 1 else "Seasons", " + ".join(map(str, seasons)))
    k[1].metric("Teams", len(teams))
    k[2].metric("Rounds played", len(done))
    k[3].metric("Floods", int(done.flood.sum()) if not done.empty else 0)
    reached = int(done.people_reached.sum()) if not done.empty else 0
    affected = int(done.people_affected.sum()) if not done.empty else 0
    k[4].metric("Reached before the flood", f"{fmt_people(reached)} / {fmt_people(affected)}")

    # Leaderboards
    cols = st.columns(2)
    for col, ratio in zip(cols, ["low", "high"]):
        with col:
            st.markdown(f"#### 🏆 {C.COST_RATIO_LABEL[ratio]}")
            s = summ[summ.cost_ratio == ratio]
            missing = sorted(set(teams[teams.cost_ratio == ratio].group_id) - set(s.group_id))
            if s.empty and not missing:
                st.caption("No teams in this setting yet.")
                continue
            pct = lambda v: "–" if pd.isna(v) else f"{v:.0%}"  # noqa: E731
            z = [0] * len(missing)
            tbl = pd.DataFrame({
                "Team": [f"G{g}" for g in s.group_id] + [f"G{g}" for g in missing],
                "Total": list(s.total_cost) + z,
                "AA": list(s.aa_cost) + z,
                "Resp.": list(s.response_cost) + z,
                "Trigger": list(s.trigger) + [G.trigger_label(data["triggers"], g, seasons)
                                              for g in missing],
                "Rnds": list(s.rounds) + z,
                "H": list(s.hits) + z,
                "M": list(s.misses) + z,
                "FA": list(s.false_alarms) + z,
                "CN": list(s.correct_negatives) + z,
                "POD": [pct(v) for v in s.pod] + ["–"] * len(missing),
                "FAR": [pct(v) for v in s.far] + ["–"] * len(missing),
            })
            tbl.insert(0, "#", range(1, len(tbl) + 1))
            st.dataframe(
                tbl, hide_index=True, width="stretch",
                column_config={
                    "#": st.column_config.NumberColumn(width=30),
                    "Team": st.column_config.TextColumn(width=50),
                    "Total": st.column_config.NumberColumn("💰 Total", format="%g", width=70),
                    "AA": st.column_config.NumberColumn(format="%g", width=45),
                    "Resp.": st.column_config.NumberColumn(format="%g", width=50),
                    **{c: st.column_config.NumberColumn(width=36)
                       for c in ["Rnds", "H", "M", "FA", "CN"]},
                    "POD": st.column_config.TextColumn(width=48),
                    "FAR": st.column_config.TextColumn(width=48),
                })

    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### Outcome per round")
        st.altair_chart(outcome_board(ev, teams, seasons), width="stretch")
    with right:
        st.markdown("#### Cumulative cost")
        ch = cumulative_chart(done, seasons)
        if ch is None:
            st.caption("Appears after the first completed round.")
        else:
            st.altair_chart(ch, width="stretch")


def outcome_board(ev: pd.DataFrame, teams: pd.DataFrame, seasons):
    multi = len(seasons) > 1
    grid = []
    for g in sorted(teams.group_id):
        for s in seasons:
            for r in range(1, C.ROUNDS_PER_SEASON + 1):
                grid.append({"group_id": int(g), "season": s, "round": r})
    grid = pd.DataFrame(grid)
    df = grid.merge(ev, on=["group_id", "season", "round"], how="left")
    df["state"] = df.apply(lambda x: x.outcome if x.status == "done"
                           else ("in progress" if isinstance(x.status, str) else "not played"),
                           axis=1)
    df = df[df.state != "not played"].copy()
    grid["Team"] = grid.group_id.map(group_label)
    grid["x"] = grid.apply(lambda x: f"S{x.season}·R{x['round']}" if multi else str(x["round"]),
                           axis=1)
    df["Team"] = df.group_id.map(group_label)
    df["x"] = df.apply(lambda x: f"S{x.season}·R{x['round']}" if multi else str(x["round"]), axis=1)
    df["label"] = df.state.map({**G.OUTCOME_SHORT, "in progress": "…"})
    df["ratio"] = df.cost_ratio.map({"low": "low", "high": "high"})
    df["detail"] = df.apply(
        lambda x: (f"forecast {int(x.forecast_sum)} vs τ {int(x.tau)}"
                   + (f", total {int(x.total_sum)}" if pd.notna(x.total_sum) else ""))
        if pd.notna(x.tau) and pd.notna(x.forecast_sum) else "", axis=1)
    x_order = list(dict.fromkeys(grid.x))
    y_order = [group_label(g) for g in sorted(teams.group_id)]
    xenc = alt.X("x:O", sort=x_order, title="Round", axis=alt.Axis(labelAngle=0, ticks=False,
                                                                     domain=False))
    yenc = alt.Y("Team:O", sort=y_order, title=None,
                 axis=alt.Axis(ticks=False, domain=False, labelFontSize=13, labelColor="#0b0b0b"))
    bg = alt.Chart(grid).mark_rect(color="#f2f1ee", cornerRadius=4, stroke="white",
                                   strokeWidth=2).encode(x=xenc, y=yenc)
    dom = list(OUTCOME_COLOURS)
    tiles = alt.Chart(df).mark_rect(cornerRadius=4, stroke="white", strokeWidth=2).encode(
        x=xenc, y=yenc,
        color=alt.Color("state:N", scale=alt.Scale(domain=dom, range=list(OUTCOME_COLOURS.values())),
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("Team:N"), alt.Tooltip("x:N", title="Round"),
                 alt.Tooltip("state:N", title="Outcome"), alt.Tooltip("detail:N", title="Dice"),
                 alt.Tooltip("total_cost:Q", title="Cost")])
    text = alt.Chart(df).mark_text(fontWeight="bold", fontSize=14, color="#0b0b0b").encode(
        x=xenc, y=yenc, text="label:N")
    h = max(46 * len(y_order), 120)
    return (bg + tiles + text).properties(height=h)


def cumulative_chart(done: pd.DataFrame, seasons):
    if done.empty:
        return None
    d = done.sort_values(["group_id", "season", "round"]).copy()
    d["step"] = (d.season - min(seasons)) * C.ROUNDS_PER_SEASON + d["round"]
    d["cum_cost"] = d.groupby("group_id").total_cost.cumsum()
    d["Team"] = d.group_id.map(group_label)
    d["Setting"] = d.cost_ratio.map({"low": "Low cost ratio", "high": "High cost ratio"})
    # prepend a zero point per team so lines start at 0
    zeros = d.groupby(["group_id", "Team", "Setting"], as_index=False).first()
    zeros["step"], zeros["cum_cost"] = 0, 0.0
    d = pd.concat([zeros, d], ignore_index=True)
    scale = group_colour_scale(d.group_id.unique())
    xmax = C.ROUNDS_PER_SEASON * len(seasons)
    rules_df = pd.DataFrame({"x": [C.RECALIBRATE_AFTER_ROUND + 0.5 + C.ROUNDS_PER_SEASON * i
                                   for i in range(len(seasons))]})
    panels = []
    for setting in ["Low cost ratio", "High cost ratio"]:
        ds = d[d.Setting == setting]
        if ds.empty:
            continue
        base = alt.Chart(ds).encode(
            x=alt.X("step:Q", title="Round", scale=alt.Scale(domain=[0, xmax]),
                    axis=alt.Axis(tickMinStep=1, grid=False)),
            y=alt.Y("cum_cost:Q", title="Coins spent"),
            color=alt.Color("Team:N", scale=scale, legend=alt.Legend(orient="bottom", title=None)))
        lines = base.mark_line(strokeWidth=2.5)
        pts = base.mark_point(filled=True, size=50, opacity=1).encode(
            tooltip=["Team", alt.Tooltip("step:Q", title="Round"),
                     alt.Tooltip("cum_cost:Q", title="Coins so far")])
        rules = alt.Chart(rules_df).mark_rule(strokeDash=[4, 4], color="#8a8983").encode(x="x:Q")
        last = ds.sort_values("step").groupby("group_id", as_index=False).last()
        last["short"] = last.group_id.map(lambda g: f"G{int(g)}")
        labels = alt.Chart(last).mark_text(align="left", dx=7, fontSize=12, fontWeight="bold",
                                           color="#52514e").encode(
            x="step:Q", y="cum_cost:Q", text="short:N")
        panels.append(alt.layer(rules, lines, pts, labels)
                      .properties(title=setting, height=135))
    return alt.vconcat(*panels, spacing=8).configure_view(stroke=None) \
        .configure_title(anchor="start", fontSize=13) \
        .configure_axis(labelFontSize=11, titleFontSize=11)


def trigger_helper():
    st.markdown("#### How does the trigger τ change detection and false alarms?")
    n = st.segmented_control("Forecast dice", list(C.LEAD_TIMES), default=C.SEASON1_FORECAST_DICE,
                             format_func=lambda x: f"{x} forecast dice ({C.LEAD_TIME_SHORT[x].lower()} lead time)",
                             key="helper_n") or C.SEASON1_FORECAST_DICE
    t = G.theory_table(n)
    t = t[t.activation_rate > 0]
    long = t.melt(id_vars="tau", value_vars=["pod", "far", "activation_rate"],
                  var_name="measure", value_name="value")
    long["measure"] = long.measure.map({"pod": "POD: floods we act on",
                                        "far": "FAR: activations that were false alarms",
                                        "activation_rate": "Share of rounds we activate"})
    dom = ["POD: floods we act on", "FAR: activations that were false alarms",
           "Share of rounds we activate"]
    ch = alt.Chart(long).mark_line(point=alt.OverlayMarkDef(size=60, filled=True),
                                   strokeWidth=2.5).encode(
        x=alt.X("tau:O", title="Trigger τ (activate when forecast dice ≥ τ)",
                axis=alt.Axis(labelAngle=0)),
        y=alt.Y("value:Q", title=None, axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
        color=alt.Color("measure:N", scale=alt.Scale(domain=dom,
                                                     range=["#2a78d6", "#eb6834", "#8a8983"]),
                        legend=alt.Legend(orient="top", title=None, labelLimit=400)),
        tooltip=["tau", "measure", alt.Tooltip("value:Q", format=".0%")]).properties(height=380)
    st.altair_chart(ch, width="stretch")
    st.caption(f"A flood happens in {G.flood_probability():.0%} of rounds. "
               "POD = floods we activated for ÷ all floods. FAR = false alarms ÷ all activations.")
    tbl = t[["tau", "activation_rate", "pod", "far"]].rename(columns={
        "tau": "τ", "activation_rate": "Activate", "pod": "POD", "far": "FAR"})
    with st.expander("Table"):
        st.dataframe(tbl, hide_index=True, column_config={
            c: st.column_config.NumberColumn(format="percent") for c in ["Activate", "POD", "FAR"]})


def join_screen():
    url = _secret(["app_url"], "")
    url = st.text_input("App address", value=url, help="Set app_url in secrets to fill this in.")
    if not url:
        st.info("Enter the public address of this app to show a QR code.")
        return
    import segno
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="png", scale=14, border=2)
    c1, c2 = st.columns([1, 1])
    c1.image(buf.getvalue(), width="stretch")
    c2.markdown(f"## Scan to join\n\n1. Scan the code with one phone per team\n"
                f"2. Pick your group number\n3. Choose your cost setting\n"
                f"4. Lock in your trigger\n\n`{url}`")


def require_admin(key: str) -> bool:
    if st.session_state.get("is_admin"):
        return True
    with st.form(f"pw_{key}"):
        pw = st.text_input("Facilitator password", type="password")
        if st.form_submit_button("Unlock"):
            if pw == admin_password():
                st.session_state["is_admin"] = True
                st.rerun()
            else:
                st.error("Wrong password")
    return False


def research_view():
    st.markdown("#### Which trigger would have been best on average?")
    st.caption("Expected cost over an 8-round season, computed exactly from the dice. "
               "Season 2 uses the envelope probabilities in config.py.")
    season = st.segmented_control("Season", [1, 2], default=1, format_func=lambda s: f"Season {s}",
                                  key="research_season") or 1
    ns = [C.SEASON1_FORECAST_DICE] if season == 1 else list(C.LEAD_TIMES)
    rows = []
    for ratio in ["low", "high"]:
        for n in ns:
            lo, hi = G.tau_range(n)
            for tau in range(lo, hi + 1):
                rows.append({"ratio": ratio, "n": n, "tau": tau,
                             "Setting": f"{ratio.capitalize()} cost ratio",
                             "Lead time": C.LEAD_TIME_SHORT[n],
                             "cost": C.ROUNDS_PER_SEASON *
                             G.expected_cost_per_round(n, tau, ratio, season)})
    df = pd.DataFrame(rows)
    best = df.loc[df.groupby(["ratio", "n"]).cost.idxmin()]

    data, ev = load_evaluated()
    played = G.summarise(ev[ev.season == season], data["triggers"])
    pts = []
    for r in played.itertuples():
        tr = data["triggers"]
        t1 = tr[(tr.group_id == r.group_id) & (tr.season == season) & (tr.from_round == 1)]
        if t1.empty or r.rounds == 0:
            continue
        pts.append({"Setting": f"{r.cost_ratio.capitalize()} cost ratio",
                    "Lead time": C.LEAD_TIME_SHORT[int(t1.n_forecast.iloc[0])],
                    "tau": int(t1.tau.iloc[0]),
                    "cost": r.total_cost / r.rounds * C.ROUNDS_PER_SEASON,
                    "Team": group_label(r.group_id)})
    pts = pd.DataFrame(pts, columns=["Setting", "Lead time", "tau", "cost", "Team"])

    for setting in ["Low cost ratio", "High cost ratio"]:
        st.markdown(f"**{setting}**")
        d = df[df.Setting == setting]
        colour = alt.Color("Lead time:N", scale=alt.Scale(domain=["Long", "Medium", "Short"],
                                                          range=GROUP_COLOURS[:3]),
                           legend=alt.Legend(orient="top") if season == 2 else None)
        line = alt.Chart(d).mark_line(strokeWidth=2.5).encode(
            x=alt.X("tau:Q", title="Trigger τ (initial)", axis=alt.Axis(tickMinStep=1)),
            y=alt.Y("cost:Q", title="Expected season cost (coins)"),
            color=colour, tooltip=["Lead time", "tau", alt.Tooltip("cost:Q", format=".1f")])
        b = best[best.Setting == setting]
        star = alt.Chart(b).mark_point(shape="diamond", size=200, filled=True).encode(
            x="tau:Q", y="cost:Q", color=colour,
            tooltip=["Lead time", alt.Tooltip("tau:Q", title="Best τ"),
                     alt.Tooltip("cost:Q", format=".1f")])
        layers = [line, star]
        p = pts[pts.Setting == setting]
        if not p.empty:
            layers.append(alt.Chart(p).mark_point(size=110, filled=True, color="#0b0b0b",
                                                  shape="circle").encode(
                x="tau:Q", y="cost:Q",
                tooltip=["Team", "Lead time", "tau", alt.Tooltip("cost:Q", format=".1f",
                                                                 title="Actual cost (per 8 rounds)")]))
            layers.append(alt.Chart(p).mark_text(dy=-14, fontSize=13, color="#0b0b0b").encode(
                x="tau:Q", y="cost:Q", text="Team"))
        st.altair_chart(alt.layer(*layers).properties(height=300), width="stretch")
    st.caption("◆ best trigger in expectation · ● what each team actually paid (scaled to 8 rounds), "
               "at its initial τ")
    st.dataframe(best.assign(cost=best.cost.round(1))[["Setting", "Lead time", "tau", "cost"]]
                 .rename(columns={"tau": "Best τ", "cost": "Expected season cost"}),
                 hide_index=True)


# --------------------------------------------------------------------------
# ADMIN VIEW
# --------------------------------------------------------------------------
def admin_view():
    st.title("Facilitator")
    if not require_admin("admin"):
        return
    eng = engine()
    if admin_password() == "admin":
        st.warning("Using the default password 'admin'. Set admin_password in secrets.")

    cur = S.current_season(eng)
    c1, c2 = st.columns([2, 3])
    new = c1.segmented_control("Current season (what team phones show)", C.SEASONS, default=cur,
                               format_func=lambda s: f"Season {s}", key="adm_season")
    if new and new != cur:
        S.set_setting(eng, "current_season", str(new))
        st.success(f"Teams now play season {new}")
        st.rerun()
    c2.markdown("Links: [Team view](./) · [Dashboard](./?view=dashboard)")

    data, ev = load_evaluated()
    st.subheader("Teams")
    if data["teams"].empty:
        st.caption("No teams yet.")
    else:
        overview = []
        for t in data["teams"].sort_values("group_id").itertuples():
            row = {"Team": group_label(t.group_id), "Cost ratio": t.cost_ratio}
            for s in C.SEASONS:
                e = ev[(ev.group_id == t.group_id) & (ev.season == s)]
                row[f"S{s} trigger"] = G.trigger_label(data["triggers"], int(t.group_id), [s])
                row[f"S{s} rounds done"] = int((e.status == "done").sum())
                pend = e[e.status != "done"]
                row[f"S{s} waiting for"] = "" if pend.empty else \
                    ("total" if pend.iloc[-1].status == "forecast" else "envelope")
            overview.append(row)
        st.dataframe(pd.DataFrame(overview), hide_index=True, width="stretch")

    st.subheader("Correct an entry")
    groups = list(range(1, C.NUM_GROUPS + 1))
    a, b, c = st.columns(3)
    g = a.selectbox("Group", groups, key="adm_g")
    s = b.selectbox("Season", C.SEASONS, index=C.SEASONS.index(cur), key="adm_s")
    r = c.selectbox("Round", list(range(1, C.ROUNDS_PER_SEASON + 1)), key="adm_r")
    existing = next((x for x in S.get_rounds(eng, g, s) if x["round"] == r), None)
    with st.form("adm_round"):
        x1, x2, x3 = st.columns(3)
        f = x1.number_input("Forecast sum", 0, 36, value=existing["forecast_sum"] if existing else None)
        t = x2.number_input("Total sum (empty = not rolled yet)", 0, 36,
                            value=existing["total_sum"] if existing else None)
        env_opts = [None] + C.ENVELOPE_VALUES
        e = x3.selectbox("Envelope", env_opts,
                         index=env_opts.index(existing["envelope"]) if existing else 0,
                         format_func=lambda v: "—" if v is None else fmt_people(v))
        y1, y2 = st.columns(2)
        if y1.form_submit_button("Save round", type="primary"):
            if f is None:
                st.error("A round needs at least a forecast sum.")
            else:
                S.admin_save_round(eng, g, s, r, int(f), None if t is None else int(t), e)
                st.success("Saved")
                st.rerun()
        if y2.form_submit_button("Delete round"):
            S.delete_round(eng, g, s, r)
            st.success("Deleted")
            st.rerun()

    st.subheader("Team settings and triggers")
    tm = S.get_team(eng, g)
    with st.form("adm_team"):
        ratio = st.radio(f"Cost ratio of group {g}", ["low", "high"],
                         index=0 if not tm or tm["cost_ratio"] == "low" else 1, horizontal=True)
        if st.form_submit_button("Save cost ratio"):
            S.set_team(eng, g, ratio)
            st.rerun()
    trs = S.get_triggers(eng, g, s)
    for tr in trs:
        cc = st.columns([4, 1])
        cc[0].write(f"Season {s}: from round {tr['from_round']}: τ = {tr['tau']}, "
                    f"{tr['n_forecast']} forecast dice")
        if cc[1].button("Delete", key=f"deltr{tr['from_round']}"):
            S.delete_trigger(eng, g, s, tr["from_round"])
            st.rerun()
    with st.form("adm_trigger"):
        z1, z2, z3 = st.columns(3)
        fr = z1.selectbox("Applies from round", [1, C.RECALIBRATE_AFTER_ROUND + 1])
        nf = z2.selectbox("Forecast dice", list(C.LEAD_TIMES),
                          index=list(C.LEAD_TIMES).index(trs[0]["n_forecast"] if trs
                                                         else C.SEASON1_FORECAST_DICE))
        tv = z3.number_input("τ", 0, 31, value=None)
        if st.form_submit_button("Set trigger") and tv is not None:
            S.set_trigger(eng, g, s, fr, int(tv), nf)
            st.rerun()

    st.subheader("Export")
    st.download_button("Download all rounds (CSV)", ev.to_csv(index=False).encode(),
                       "trigger_game_rounds.csv", "text/csv")

    st.subheader("Danger zone")
    with st.form("reset"):
        what = st.radio("Reset", ["Season 1 data", "Season 2 data", "Everything (teams too)"])
        confirm = st.text_input("Type RESET to confirm")
        if st.form_submit_button("Reset"):
            if confirm != "RESET":
                st.error("Type RESET to confirm")
            else:
                if what.startswith("Everything"):
                    S.reset_all(eng)
                else:
                    S.reset_season(eng, 1 if "1" in what else 2)
                st.success("Done")
                st.rerun()
    if st.button("Delete group " + str(g) + " entirely"):
        S.delete_team(eng, g)
        st.rerun()


# --------------------------------------------------------------------------
view = st.query_params.get("view", "team")
if view == "dashboard":
    dashboard_view()
elif view == "admin":
    admin_view()
else:
    team_view()
