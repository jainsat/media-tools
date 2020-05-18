# libraries
import numpy as np
import matplotlib.pyplot as plt

# Total Bitrate utility
height = [0.0 , 0.0, 2.59/48.0, 2.48/48.0, 0.0]
bars = ('SimpleABR', 'BOLA', 'BBA0', 'BBA2', 'Pensieve')
y_pos = np.arange(len(bars))

plt.bar(y_pos, height, color=['yellow', 'red', 'green', 'blue', 'cyan'], edgecolor='black')
plt.xticks(y_pos, bars)
plt.ylabel("Average value")
plt.xlabel("Rebuffer penalty")
plt.show()

