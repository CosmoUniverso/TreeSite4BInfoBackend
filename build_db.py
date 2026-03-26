import requests
from bs4 import BeautifulSoup
import sqlite3
import textwrap

URLS = [
    "https://cosmouniverso.github.io/TreeSite4BInfoSite/",
    "https://cosmouniverso.github.io/TreeSite4BInfoSite/alberi.html"
]


def fetch_all_text(urls):
    full_text = ""
    for url in urls:
        html = requests.get(url).text
        soup = BeautifulSoup(html, "html.parser")
        full_text += soup.get_text(separator="\n") + "\n"
    return full_text


def chunk_text(text, max_chars=500):
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    current = ""

    for p in paragraphs:
        if len(current) + len(p) < max_chars:
            current += p + "\n"
        else:
            chunks.append(current.strip())
            current = p + "\n"

    if current:
        chunks.append(current.strip())

    return chunks

def build_db(chunks):
    conn = sqlite3.connect("knowledge.db")
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS chunks")
    c.execute("CREATE TABLE chunks (id INTEGER PRIMARY KEY, text TEXT)")

    for ch in chunks:
        c.execute("INSERT INTO chunks (text) VALUES (?)", (ch,))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    print("Scarico il sito...")
    text = fetch_all_text(URLS)


    print("Creo i chunk...")
    chunks = chunk_text(text)

    print(f"Creati {len(chunks)} chunk")

    print("Salvo nel database...")
    build_db(chunks)

    print("Fatto! knowledge.db pronto.")
