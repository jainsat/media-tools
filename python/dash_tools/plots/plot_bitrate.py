# libraries
import numpy as np
import matplotlib.pyplot as plt

# Total Bitrate utility
height = [52400.0/48.0 , 63900/48.0, 64900/48.0, 64900/48.0, 46300/48.0]
bars = ('SimpleABR', 'BOLA', 'BBA0', 'BBA2', 'Pensieve')
y_pos = np.arange(len(bars))

plt.bar(y_pos, height, color=['yellow', 'red', 'green', 'blue', 'cyan'], edgecolor='black')
plt.xticks(y_pos, bars)
plt.ylabel("Average value")
plt.xlabel("Bitrate utility")
plt.show()

