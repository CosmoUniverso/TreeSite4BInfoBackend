import time
import random
import requests

URL = "https://tuo-server.onrender.com"  # cambia con il tuo

# intervallo: tra 5 e 10 minuti (sempre sotto i 15)
MIN_DELAY = 300
MAX_DELAY = 600

while True:
    try:
        r = requests.get(URL, timeout=10)
        print(f"[OK] Status: {r.status_code}")
    except Exception as e:
        print(f"[ERRORE] {e}")

    delay = random.randint(MIN_DELAY, MAX_DELAY)
    print(f"Prossima richiesta tra {delay} secondi")
    time.sleep(delay)