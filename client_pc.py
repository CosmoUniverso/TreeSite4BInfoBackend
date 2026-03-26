import asyncio
import websockets
import json
import sqlite3
import subprocess
import re
from nltk.stem.snowball import ItalianStemmer

SERVER_URL = "wss://treesitetorricellirelay.onrender.com/ws/client"
MODEL = "llama3.2:3b"

stemmer = ItalianStemmer()

def normalize(text):
    text = text.lower()
    text = re.sub(r"[^a-zàèéìòùç ]", " ", text)
    words = text.split()
    stems = [stemmer.stem(w) for w in words]
    return stems

def ask_ollama(prompt):
    result = subprocess.run(
        ["ollama", "run", MODEL],
        input=prompt.encode(),
        stdout=subprocess.PIPE
    )
    return result.stdout.decode().strip()

def load_chunks():
    conn = sqlite3.connect("knowledge.db")
    c = conn.cursor()
    c.execute("SELECT text FROM chunks")
    chunks = [row[0] for row in c.fetchall()]
    conn.close()
    return chunks

chunks = load_chunks()
normalized_chunks = [normalize(c) for c in chunks]

def search_chunks(query, top_k=3):
    q_words = normalize(query)
    scores = []

    for i, ch_words in enumerate(normalized_chunks):
        score = sum(1 for w in q_words if w in ch_words)
        if score > 0:
            scores.append((score, chunks[i]))

    scores.sort(reverse=True, key=lambda x: x[0])
    return [c for _, c in scores[:top_k]]

async def main():
    while True:
        try:
            print("Connessione al server Render...")
            async with websockets.connect(SERVER_URL) as ws:
                print("Connesso! In attesa di prompt...")

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)

                    if data.get("type") == "task":
                        prompt = data["prompt"]
                        print(f"\nPrompt: {prompt}")

                        found = search_chunks(prompt)

                        if not found:
                            response = "Non ho informazioni sufficienti nel sito."
                        else:
                            context = "\n\n".join(found)
                            full_prompt = f"""
Rispondi solo usando le informazioni presenti nel testo seguente.
Se la risposta non è presente, di': "Non ho informazioni sufficienti".

Regole:
- Rispondi in modo breve (massimo 3 frasi).
- Riformula con parole tue.
- Non copiare frasi intere dal testo.
- Non includere parti non rilevanti.
- Non aggiungere nulla che non sia nel testo.
- Evita errori ortografici e usa parole italiane corrette.

Testo:
{context}

Domanda: {prompt}

Risposta sintetica:
"""

                            response = ask_ollama(full_prompt)

                        await ws.send(json.dumps({
                            "type": "result",
                            "response": response
                        }))

        except Exception as e:
            print("Connessione persa, ritento...", e)
            await asyncio.sleep(3)

asyncio.run(main())
