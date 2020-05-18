# libraries
import numpy as np
import matplotlib.pyplot as plt

# Total Bitrate utility
height = [416.35 , 473.95, 501.59, 501.53, 304.20]
bars = ('SimpleABR', 'BOLA', 'BBA0', 'BBA2', 'Pensieve')
y_pos = np.arange(len(bars))

plt.bar(y_pos, height, color=['yellow', 'red', 'green', 'blue', 'cyan'], edgecolor='black')
plt.xticks(y_pos, bars)
plt.ylabel("Average value")
plt.xlabel("Average QOE")
plt.show()

