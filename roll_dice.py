import numpy as np

n_f = 4
forecast_dice = np.random.randint(1, 7, n_f)
forecast_sum = np.sum(forecast_dice)

n_o = 2
outcome_dice = np.random.randint(1, 7, n_o)
sum_outcome = np.sum(outcome_dice) + forecast_sum

print("Forecast dice:", forecast_sum)
print("Outcome dice:", sum_outcome)