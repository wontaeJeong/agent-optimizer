"""Synthetic wiring fixture. This is NOT an LLM or an RTL debugging algorithm."""
import json
import sys
from pathlib import Path
agent = Path(__file__).resolve().parents[1]
task = Path(sys.argv[1])
strategy = json.loads((agent / 'configs/strategy.json').read_text())
if strategy.get('repair'):
    for path in task.glob('*.sv'):
        text = path.read_text()
        # Only our explicitly synthetic fixture convention is understood.
        for operator in ['^', '|', '&']:
            text = text.replace("/*FIX:" + operator + "*/ 1'b0", operator)
        path.write_text(text)
print(json.dumps({'fixture': True, 'repaired': bool(strategy.get('repair'))}))
