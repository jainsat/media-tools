# libraries
import numpy as np
import matplotlib.pyplot as plt

# Total Bitrate utility
height = [52.10/48.0 , 63.70/48.0, 64.60/48.0, 64.60/48.0, 42.25/48.0]
bars = ('SimpleABR', 'BOLA', 'BBA0', 'BBA2', 'Pensieve')
y_pos = np.arange(len(bars))

plt.bar(y_pos, height, color=['yellow', 'red', 'green', 'blue', 'cyan'], edgecolor='black')
plt.xticks(y_pos, bars)
plt.ylabel("Average value")
plt.xlabel("Smoothness penalty")
plt.show()

