"""Atomic SQLite rebuild from the original Vivo pages and current Vercel text.

The DB is replaced only when at least one source and chunk was successfully fetched.
Requires requests and beautifulsoup4 (already installed for Vivo).
"""
import os
import re
import sqlite3
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URLS = [
    "https://cosmouniverso.github.io/TreeSite4BInfoSite/",
    "https://cosmouniverso.github.io/TreeSite4BInfoSite/alberi.html",
    "https://cosmouniverso.github.io/TreeSite4BInfoSite/info",
    "https://albero-project.vercel.app/",
]
DB = Path(__file__).with_name("knowledge.db")


def chunks_from_html(html: str, max_len: int = 750) -> list[str]:
    doc = BeautifulSoup(html, "html.parser")
    main = doc.select_one("main") or doc.body or doc
    for tag in main.select("script, style, noscript, svg, nav, footer, button, form"):
        tag.decompose()
    selected = []
    for tag in main.select("h1, h2, h3, h4, p, li"):
        if tag.find_parent(["p", "li"]):
            continue
        text = re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()
        if len(text) < 20 or text in selected:
            continue
        selected.append(text)
    # Split long paragraphs, but preserve complete sentences when possible.
    pieces = []
    for p in selected:
        if len(p) <= max_len:
            pieces.append(p)
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", p):
            if len(sentence) <= max_len:
                pieces.append(sentence)
            else:
                pieces.extend(sentence[i:i+max_len] for i in range(0, len(sentence), max_len))

    chunks, buffer = [], ""
    for p in pieces:
        if len(buffer) + len(p) + 1 > max_len and buffer:
            chunks.append(buffer)
            buffer = ""
        buffer = (buffer + "\n" + p).strip()
    if buffer:
        chunks.append(buffer)
    return chunks


def main():
    pages = []
    for url in URLS:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "VivoRAG/2.0"})
            r.raise_for_status()
            chunks = chunks_from_html(r.text)
            print(f"{url}: {len(chunks)} blocchi")
            if chunks:
                pages.extend((url, chunk) for chunk in chunks)
        except requests.RequestException as exc:
            print(f"Fonte saltata: {url}: {exc}")
    # Keep the old DB if all remote sources were unavailable. Extra notes alone
    # are not sufficient evidence for a successful fresh crawl.
    if not pages:
        raise SystemExit("Nessuna pagina remota valida: database conservato")
    # Project notes and separately sourced botany notes are searchable sources.
    for name in ("knowledge_extra.md", "botanica_extra.md"):
        notes = Path(__file__).with_name(name)
        if not notes.exists():
            continue
        text = notes.read_text(encoding="utf-8")
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        for paragraph in paragraphs:
            # Each sourced section is split on sentence boundaries where possible.
            if len(paragraph) > 950:
                parts = re.split(r"(?<=[.!?])\s+", paragraph)
                buf = ""
                for part in parts:
                    if len(buf) + len(part) + 1 > 900 and buf:
                        pages.append((f"file:{name}", buf))
                        buf = ""
                    buf = (buf + " " + part).strip()
                if buf:
                    pages.append((f"file:{name}", buf))
            else:
                pages.append((f"file:{name}", paragraph))
        print(f"Note {name}: {len(paragraphs)} sezioni")
    if not pages:
        raise SystemExit("Nessuna fonte valida: database originale conservato")

    tmp = DB.with_suffix(".db.tmp")
    if tmp.exists():
        tmp.unlink()
    with sqlite3.connect(tmp) as conn:
        conn.execute("CREATE TABLE chunks (id INTEGER PRIMARY KEY, source_url TEXT NOT NULL, text TEXT NOT NULL)")
        conn.executemany("INSERT INTO chunks (source_url, text) VALUES (?, ?)", pages)
        conn.commit()
    # Retain a backup, and use replace on same volume.
    if DB.exists():
        import shutil
        shutil.copy2(DB, DB.with_suffix(".db.bak"))
    os.replace(tmp, DB)
    print(f"Nuovo knowledge.db: {len(pages)} blocchi, backup knowledge.db.bak")

if __name__ == "__main__":
    main()
