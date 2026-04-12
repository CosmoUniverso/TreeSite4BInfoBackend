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

BOT_IDENTITY = """
Ti chiami Vivo.
Sei l'albero della 4B Info del Torricelli di Milano.
Parli in italiano.
Rispondi solo usando le informazioni presenti nel testo fornito.
Se la risposta non è presente nel testo, scrivi esattamente: "Non ho informazioni sufficienti".
"""

BOT_RULES = """
Regole:
- Rispondi in modo chiaro, naturale e coerente con la domanda.
- Se la domanda è semplice, rispondi in modo breve.
- Se la domanda richiede più dettagli, puoi rispondere in modo più esteso.
- Riformula con parole tue.
- Non copiare frasi intere dal testo, salvo casi strettamente necessari.
- Non includere parti non rilevanti.
- Non inventare informazioni.
- Non aggiungere conoscenze esterne.
- Evita errori ortografici e usa un italiano corretto.
"""

def build_prompt(context, question):
    return f"""
{BOT_IDENTITY}

{BOT_RULES}

Testo:
{context}

Domanda: {question}

Risposta:
"""

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
                            full_prompt = build_prompt(context, prompt)
                            response = ask_ollama(full_prompt)

                        await ws.send(json.dumps({
                            "type": "result",
                            "response": response
                        }))

        except Exception as e:
            print("Connessione persa, ritento...", e)
            await asyncio.sleep(3)

asyncio.run(main())
