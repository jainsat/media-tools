# libraries
import numpy as np
import matplotlib.pyplot as plt

# Total Bitrate utility
height = [9800/48.0 , 26150/48.0, 7000/48.0, 7000/48.0, 3550/48.0]
bars = ('SimpleABR', 'BOLA', 'BBA0', 'BBA2', 'Pensieve')
y_pos = np.arange(len(bars))

plt.bar(y_pos, height, color=['yellow', 'red', 'green', 'blue', 'cyan'], edgecolor='black')
plt.xticks(y_pos, bars)
plt.ylabel("Average value")
plt.xlabel("Smoothness penalty")
plt.show()

