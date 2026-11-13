import sys
from pathlib import Path

name = sys.argv[1]
start = int(sys.argv[2]) if len(sys.argv) > 2 else 0

text = Path(f"data/text/{name}.txt").read_text()
paras = [p.strip().replace("\n", " ") for p in text.split("\n\n") if len(p.strip()) > 200]

print(f"{name}: {len(paras)} paragraphs, showing {start} to {start + 7}\n")
for i, p in enumerate(paras[start:start + 8], start=start):
    print(f"[{i}] {p}\n")