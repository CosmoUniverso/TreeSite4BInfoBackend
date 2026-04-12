import requests
from bs4 import BeautifulSoup
import sqlite3
import re

URLS = [
    "https://cosmouniverso.github.io/TreeSite4BInfoSite/",
    "https://cosmouniverso.github.io/TreeSite4BInfoSite/alberi.html",
    "https://cosmouniverso.github.io/TreeSite4BInfoSite/info",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VivoBot/1.0)"
}


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def fetch_page_text(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    return clean_text(text)


def fetch_all_pages(urls):
    pages = []

    for url in urls:
        try:
            print(f"Scarico: {url}")
            text = fetch_page_text(url)

            if text:
                pages.append({
                    "url": url,
                    "text": text
                })
            else:
                print(f"Attenzione: nessun testo utile trovato in {url}")

        except Exception as e:
            print(f"Errore durante il download di {url}: {e}")

    return pages


def chunk_text(text: str, max_chars: int = 700):
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    current = ""

    for p in paragraphs:
        if len(current) + len(p) + 1 <= max_chars:
            current += p + "\n"
        else:
            if current.strip():
                chunks.append(current.strip())
            current = p + "\n"

    if current.strip():
        chunks.append(current.strip())

    return chunks


def build_db(pages):
    conn = sqlite3.connect("knowledge.db")
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS chunks")
    c.execute("""
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_url TEXT NOT NULL,
            text TEXT NOT NULL
        )
    """)

    total_chunks = 0

    for page in pages:
        page_chunks = chunk_text(page["text"])
        for ch in page_chunks:
            c.execute(
                "INSERT INTO chunks (source_url, text) VALUES (?, ?)",
                (page["url"], ch)
            )
            total_chunks += 1

    conn.commit()
    conn.close()

    return total_chunks


if __name__ == "__main__":
    print("Scarico il sito...")
    pages = fetch_all_pages(URLS)

    if not pages:
        print("Nessuna pagina valida scaricata. Database non creato.")
    else:
        print("Salvo nel database...")
        total = build_db(pages)
        print(f"Fatto. knowledge.db pronto con {total} chunk.")
