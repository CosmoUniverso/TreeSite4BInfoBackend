import asyncio
import websockets
import random

URL = "wss://treesitetorricellirelay.onrender.com/ws/client"

# intervallo: tra 5 e 10 minuti (sempre sotto i 15)
MIN_DELAY = 300
MAX_DELAY = 600

async def keep_alive():
    while True:
        try:
            async with websockets.connect(URL) as ws:
                # invia un messaggio minimo per tenere viva la connessione
                await ws.send("ping")
                print("[OK] Connessione attiva, ping inviato")
        except Exception as e:
            print(f"[ERRORE] Connessione persa: {e}")

        delay = random.randint(MIN_DELAY, MAX_DELAY)
        print(f"Prossima connessione tra {delay} secondi")
        await asyncio.sleep(delay)

asyncio.run(keep_alive())
