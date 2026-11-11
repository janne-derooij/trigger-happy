# To trigger, or not to trigger: facilitator guide

A live scoring app for the anticipatory-action dice game. Each team enters its dice
on one phone; the projector shows a live scoreboard. This guide walks you through
facilitating a session from preparation to clean-up.

| Who | Link |
|---|---|
| Teams (one phone per team) | https://trigger-happy-link.streamlit.app |
| Projector | https://trigger-happy-link.streamlit.app/?view=dashboard |
| Facilitator (password protected) | https://trigger-happy-link.streamlit.app/?view=admin |

The facilitator password is the `admin_password` in the app's Secrets on
share.streamlit.io.

---

## Part 1: Preparation (a few days before)

### Step 1. Check the game settings
Open `config.py` and check:
- `NUM_GROUPS`: the number of group buttons teams can pick (default 6).
- `ENVELOPE_PROBS`: the mix of 10.000 / 20.000 / 30.000 envelopes per lead time.
  **Set this to match your physical envelopes.** It only affects the expected costs
  in the Research tab, not the scores.

If you changed anything, push it:
```
git add .
git commit -m "update settings"
git push
```
The app redeploys by itself within a minute or two.

### Step 2. Prepare the physical materials
- Dice: 6 per team (forecast and outcome dice in two colours helps).
- Season-2 envelopes per lead time.
- A sheet with each team's group number and cost setting (low or high). Split the
  teams roughly evenly between low and high.
- A paper scoring sheet as backup.

### Step 3. Dress rehearsal (a day or two before)
1. Open the **facilitator link**, log in, and check that the page shows no errors.
2. Open the **projector link**, click **Join**, and scan the QR code with your phone.
3. Join as 2–3 different groups on different phones or browser tabs, with at least
   one low and one high cost setting.
4. Play 4–5 rounds of season 1 and watch the projector update within a few seconds.
5. Try out on purpose:
   - **Undo last entry** on a phone, to fix a typo.
   - **Recalibrate** after round 4.
   - **Admin → Correct an entry**, to change a round as facilitator.
6. In **Admin**, set the current season to **Season 2**. Check that the phones show the
   lead-time choice, and play until a hit to see the envelope buttons.
7. Clean up: **Admin → Danger zone → Everything (teams too)**, type `RESET`, confirm.

Opening the app the day before also keeps the free Supabase database from pausing.

---

## Part 2: On the day

### Step 4. Before participants arrive (15 minutes)
1. On your own laptop or phone, open the **facilitator link** and log in.
   Check that the current season is **Season 1** and **Admin → Teams** says
   "No teams yet". If old data is there, reset as in step 3.7.
2. On the projector, open the **projector link** and click **Join** to show the QR code.
   If the app was asleep, it can take up to a minute to start; just wait.

### Step 5. Opening and explanation (0:00–0:20)
1. Tell the cost setting to each team (low or high).
2. Each team scans the QR code with **one** phone, taps its group number and chooses
   its cost setting.
3. In **Admin → Teams**, check that every group has joined with the right setting.
   Fix a wrong cost setting under **Team settings and triggers**.

### Step 6. Season 1 (0:20–0:35)
1. Projector: **Trigger helper** with **4 forecast dice**. Explain POD, FAR and the
   share of rounds a team activates for each τ.
2. Teams choose τ on their phone and tap **Lock in my trigger**.
   (The phone also shows POD and FAR for the τ they type.)
3. Projector: **Scoreboard**, season **Current**.
4. Each round, every team:
   1. rolls the 4 forecast dice and enters the sum; the phone says **ACTIVATE** or
      **No activation**;
   2. rolls the 2 outcome dice and enters the sum of **all 6** dice; the phone shows
      the outcome and the cost.
5. **After round 4**: teams that want to change τ open **Recalibrate** on their phone
   *before* entering round 5. The new τ applies to rounds 5–8.
6. After round 8 the phone says "Season 1 finished". Use the scoreboard to discuss:
   which team paid least within each cost setting, and why?

### Step 7. Explain onset-time uncertainty (0:35–0:40)
1. In **Admin**, set the current season to **Season 2**. The phones switch by themselves
   (teams may need to tap the screen or refresh).
2. Projector: **Trigger helper**, switching between 3, 4 and 5 forecast dice to show
   how the lead time changes POD and FAR.

### Step 8. Season 2 (0:40–0:55)
1. Each team chooses its lead time (3, 4 or 5 forecast dice) and τ on its phone.
   The lead time is fixed for the whole season.
2. Projector: **Scoreboard**.
3. Each round works as in season 1, with one extra step: after a **hit**
   (activated and flooded), the team draws an envelope and taps the number on it
   (10.000, 20.000 or 30.000).
4. Recalibration after round 4 works as in season 1.
5. At the end, projector: **Scoreboard → Total**. Announce the best team in the low and
   in the high cost setting.

### Step 9. Link to research (0:55–1:05)
1. Projector: **Research** tab (asks for the facilitator password).
2. For each season and cost setting it shows the expected season cost for every τ,
   the best τ (◆) and what each team actually paid (●).
3. Good discussion point: a team can choose well and still be unlucky in 8 rounds,
   and the other way around.

### Step 10. Debrief and afterwards (1:05–1:15)
1. Use the discussion questions from the workshop plan.
2. **Admin → Export → Download all rounds (CSV)** to keep the data.
3. Optional: reset the data so the app is clean for the next session.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| A team typed a wrong number | The team taps **Undo last entry**, or you fix it in **Admin → Correct an entry**. Scores are recalculated at once. |
| A team picked the wrong group | Tap **Switch group** at the top of the phone. If it already entered data under the wrong group, delete that group in **Admin**. |
| A phone dies or a team has no phone | Enter the team's rounds yourself under **Admin → Correct an entry**. |
| A phone still shows season 1 after you switched | Ask the team to refresh the page. |
| The scoreboard doesn't update | Refresh the projector page. |
| "Error" or a blank page | On share.streamlit.io, open the app's **Manage app** panel to read the logs. Most often the database paused: open your project on supabase.com and resume it. |

---

## Game rules as implemented

- A team activates when the forecast sum is **at least τ** (≥). A flood is a total of
  **22 or more**, which happens in about 45% of rounds.
- A flood affects 30.000 people. Response costs 3 coins per 10.000 people not reached.
- AA costs 1 coin (low) or 2 coins (high) per 10.000 people.
- **Season 1**: 4 forecast dice, 2 outcome dice. An activation reaches all 30.000 people.
- **Season 2**: 3, 4 or 5 forecast dice. After a hit, the envelope decides how many
  people are reached; the team pays AA for them and response for the rest.
  A **false alarm** costs a full activation (all 30.000 people).
- 8 rounds per season; τ can be changed once, before round 5.

---

## Technical notes

- **Code**: `app.py` (screens), `game.py` (rules and scoring), `storage.py` (database),
  `config.py` (all parameters). Tests: `pytest tests`.
- **Run locally**: `pip install -r requirements.txt`, then `streamlit run app.py`.
  Without secrets it uses a local `trigger_happy.db` file and the password `admin`.
- **Database**: Supabase Postgres, connected through the **Session pooler** string in
  the app's Secrets. The app creates its tables (`th_teams`, `th_triggers`,
  `th_rounds`, `th_settings`) on first start. Only raw dice are stored; outcomes and
  costs are always recomputed, so a correction fixes every score at once.
- **Secrets** (share.streamlit.io → your app → settings → Secrets):
  ```toml
  admin_password = "..."
  app_url = "https://trigger-happy-link.streamlit.app"

  [database]
  url = "postgresql://postgres.xxxx:PASSWORD@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
  ```
- **Updating the app**: change files, then `git add .`, `git commit -m "..."`,
  `git push`. Streamlit Cloud redeploys automatically.
