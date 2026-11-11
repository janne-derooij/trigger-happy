# To trigger, or not to trigger: live game app

A Streamlit app for the anticipatory-action dice game. Teams enter their dice on a
phone; the projector shows a live scoreboard.

## The three views

| Address | Who | What |
|---|---|---|
| `/` | Teams (one phone each) | Pick group → cost setting → lock in trigger → per round: forecast sum, total sum, and in season 2 the envelope after a hit |
| `/?view=dashboard` | Projector | **Scoreboard** (leaderboards per cost setting, outcome per round, cumulative cost), **Trigger helper** (POD/FAR per τ), **Join** (QR code), **Research** (password: expected cost per τ, best trigger, and where each team ended up) |
| `/?view=admin` | Facilitator | Switch season, correct or delete any entry, change triggers, export CSV, reset |

## Game rules as implemented

- A team activates when the forecast sum is **≥ τ**. A flood is a total of **≥ 22**.
- Season 1: 4 forecast dice. An activation reaches all 30.000 people.
- Season 2: lead time picks 3, 4 or 5 forecast dice. After a **hit** the team draws an
  envelope (10.000 / 20.000 / 30.000) and enters it; it pays AA for those people and
  response (3 coins per 10.000) for the rest. A **false alarm** pays for all 30.000.
- After round 4, a team can change τ once (rounds 5–8). The lead time stays fixed.
- Teams can undo their own last entry, so typos are fixed at the table.
- Only raw dice are stored. Outcomes and costs are recomputed every time, so an
  admin correction fixes every score at once.

All parameters are in `config.py`.
**Replace `ENVELOPE_PROBS` with the real distribution of your envelopes.** It only
affects the Research view's expected costs for season 2, not the scores.

## 1. Run it locally (no accounts needed)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Without secrets it uses a local `trigger_happy.db` file and the admin password `admin`.
Open `http://localhost:8501/?view=dashboard` in a second tab. Tests: `pytest tests`.

## 2. Supabase (the shared database)

1. In your Supabase project, click **Connect** and copy the **Session pooler**
   connection string. Use the pooler rather than "Direct connection", because
   Streamlit Cloud can't reach the direct (IPv6) address.
2. Replace `[YOUR-PASSWORD]` with your database password. If it contains special
   characters (`@ : / ? #`), use a password without them to avoid encoding trouble.
3. The app creates its tables (`th_teams`, `th_triggers`, `th_rounds`, `th_settings`)
   on first start; you don't need to run any SQL.

## 3. GitHub

Push this folder to your repository. Leave out `.streamlit/secrets.toml` (it's in `.gitignore`).

## 4. Streamlit Community Cloud

1. **Create app** → choose your repo, branch `main`, main file `app.py`.
2. Under **Advanced settings → Secrets**, paste the contents of
   `.streamlit/secrets.toml.example` with your own values. Set `app_url` once
   you know the app's address, so the Join screen can show the QR code.
3. Deploy, then open `/?view=admin` to check that the database connection works.

## Workshop-day checklist

- [ ] Day before: open the app so Supabase and Streamlit are awake; do a dry run with
      2–3 phones; then **Admin → Reset → Everything**.
- [ ] 10 min before: open the dashboard on the projector (Join view for the QR code).
- [ ] Admin: season is set to 1.
- [ ] After season 1: **Admin → Current season → Season 2**. Team phones switch automatically.
- [ ] After the game: **Admin → Download all rounds (CSV)**.
- [ ] Paper fallback: if a phone dies, the facilitator enters that team's rounds via Admin.
