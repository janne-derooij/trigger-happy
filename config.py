"""Game parameters for "To trigger, or not to trigger".

Change values here; the rest of the app reads from this file.
"""

# --- Workshop set-up -------------------------------------------------------
NUM_GROUPS = 6                  # group numbers 1..NUM_GROUPS can be chosen
ROUNDS_PER_SEASON = 8
RECALIBRATE_AFTER_ROUND = 4     # teams may change their trigger once, after this round
SEASONS = [1, 2]

# --- Dice and floods --------------------------------------------------------
TOTAL_DICE = 6
FLOOD_THRESHOLD = 22            # flood when the sum of all 6 dice >= this value
SEASON1_FORECAST_DICE = 4

# Season 2 lead-time choices: number of forecast dice -> label
LEAD_TIMES = {
    3: "Long lead time (3 forecast dice, 3 outcome dice)",
    4: "Medium lead time (4 forecast dice, 2 outcome dice)",
    5: "Short lead time (5 forecast dice, 1 outcome die)",
}
LEAD_TIME_SHORT = {3: "Long", 4: "Medium", 5: "Short"}

# --- People and costs -------------------------------------------------------
PEOPLE_AFFECTED = 30_000
UNIT = 10_000                   # costs are per 10,000 people
RESPONSE_COST_PER_UNIT = 3      # coins per 10,000 people not reached in a flood
AA_COST_PER_UNIT = {"low": 1, "high": 2}   # coins per 10,000 people assisted with AA
COST_RATIO_LABEL = {
    "low": "Low cost ratio (AA = 1 coin per 10.000)",
    "high": "High cost ratio (AA = 2 coins per 10.000)",
}

# --- Season 2 envelopes -----------------------------------------------------
# Values a team can draw when it activated AND a flood happened.
ENVELOPE_VALUES = [10_000, 20_000, 30_000]

# Probability of each envelope value per lead time (number of forecast dice).
# Only used for the expected-cost curves in the facilitator's Research view,
# NOT for scoring (scoring uses what teams actually draw).
# !!! PLACEHOLDERS: replace with the distribution of your physical envelopes !!!
ENVELOPE_PROBS = {
    3: {10_000: 0.1, 20_000: 0.2, 30_000: 0.7},   # long lead time (4 days)
    4: {10_000: 0.2, 20_000: 0.4, 30_000: 0.4},   # medium lead time (3 days)
    5: {10_000: 0.5, 20_000: 0.3, 30_000: 0.2},   # short lead time (2 days)
}

# --- Dashboard --------------------------------------------------------------
DASHBOARD_REFRESH_SECONDS = 3
