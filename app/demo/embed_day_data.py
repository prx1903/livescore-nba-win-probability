"""Embeds the day data into the demo page: only the line 'const DAY=...;' of the HTML changes.
Usage (from the repository root): python -I app/demo/embed_day_data.py docs/index.html app/demo/day_data.json"""
import sys, json, re
html_path, data_path = sys.argv[1:3]
h = open(html_path, encoding='utf-8').read()
D = json.load(open(data_path, encoding='utf-8'))
m = re.findall(r'^const DAY=.*;$', h, flags=re.M)
assert len(m) == 1, 'DAY line not found'
h = h.replace(m[0], 'const DAY=' + json.dumps(D, ensure_ascii=False, separators=(',', ':')) + ';')
open(html_path, 'w', encoding='utf-8').write(h)
print('embedded:', len(D['games']), 'games,', sum(len(g['ev']) for g in D['games']), 'events')
