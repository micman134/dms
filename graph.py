import matplotlib.pyplot as plt
import numpy as np

# Data
metrics = ['RSS Feed Collection\nTime (min)', 
           'Article Processing\nTime (sec/article)', 
           'Dashboard Load\nTime (sec)', 
           'Map Rendering Time\n(sec)', 
           'API Response Time\n(sec)', 
           'System Uptime (%)', 
           'Alert Generation\nLatency (sec)']

targets = [5, 30, 3, 2, 5, 99, 10]
achieved = [2.5, 6.5, 1.75, 0.5, 3, 99.5, 4]

fig, ax = plt.subplots(figsize=(12, 8))

y_pos = np.arange(len(metrics))

# Create grouped bars
bar_height = 0.35
ax.barh(y_pos - bar_height/2, targets, bar_height, label='Target', color='#ffc107', alpha=0.8, edgecolor='black')
ax.barh(y_pos + bar_height/2, achieved, bar_height, label='Achieved', color='#28a745', alpha=0.8, edgecolor='black')

ax.set_yticks(y_pos)
ax.set_yticklabels(metrics, fontsize=10)
ax.set_xlabel('Value (lower is better for time metrics, higher for uptime)', fontsize=12, fontweight='bold')
ax.set_title('System Performance: Target vs Achieved', fontsize=14, fontweight='bold')
ax.legend(loc='lower right', fontsize=11)
ax.grid(True, alpha=0.3, axis='x')

# Add value labels
for i, (t, a) in enumerate(zip(targets, achieved)):
    ax.text(t + 0.5, i - bar_height/2, f'{t}', va='center', ha='left', fontsize=8)
    ax.text(a + 0.5, i + bar_height/2, f'{a}', va='center', ha='left', fontsize=8, fontweight='bold')

plt.tight_layout()
plt.savefig('system_performance_horizontal.png', dpi=300, bbox_inches='tight')
plt.show()