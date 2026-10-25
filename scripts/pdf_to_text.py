from pathlib import Path
from pypdf import PdfReader

for pdf in Path("data/pdf").glob("*.pdf"):
    reader = PdfReader(pdf)
    pages = [(p.extract_text() or "").strip() for p in reader.pages]
    out = Path("data/text") / f"{pdf.stem}.txt"
    out.write_text("\n\n".join(pages),encoding="utf-8")
    print(f"{pdf.name}:{len(reader.pages)} pages ->{out}")
