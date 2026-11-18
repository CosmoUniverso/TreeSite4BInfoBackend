"""Vivo v2.3: FAQ per intenti, con risposte brevi e dati verificabili.

Fonte meteo: Open-Meteo (ambiente esterno, non sensori sull'albero).
Fonte crescita: API pubblica /api/vivo-status del sito (misurazioni Neon).
Per domande generali su botanica il chiamante usa normalmente Bonsai + RAG.
"""
from __future__ import annotations

from datetime import datetime
import json
import math
import os
import re
import time
import unicodedata
from urllib.request import Request, urlopen

STATUS_URL = os.getenv(
    "VIVO_MEASUREMENTS_URL", "https://albero-project.vercel.app/api/vivo-status"
)
WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude=45.428113&longitude=9.179875"
    "&current=temperature_2m,relative_humidity_2m,apparent_temperature"
    "&timezone=Europe%2FRome"
)
_cache: dict[str, tuple[float, object]] = {}


def _clean(q: str) -> str:
    normalized = unicodedata.normalize("NFKD", q.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", normalized)).strip()


def faq_intent(question: str) -> str | None:
    """Solo intenti riferiti a Vivo. No intercettazione delle domande botaniche generali."""
    q = _clean(question)
    # Intercetta domande sulle funzioni prima delle altre classi.
    if re.search(
        r"\b(?:che )?cosa (?:sai|puoi) fare\b"
        r"|\b(?:quali|che) (?:sono )?(?:le )?tue (?:funzioni|capacita|abilita)\b"
        r"|\bcome puoi aiutarmi\b"
        r"|\bdi cosa (?:sai|puoi) parlare\b"
        r"|\ba cosa servi\b",
        q,
    ):
        return "capabilities"
    if re.search(
        r"\bcome stai\b|\bcome sta vivo\b|\bcome sta (?:l |un )?albero\b"
        r"|\bcome ti senti\b|\bstai bene\b|\bcome va(?: oggi)?\b|\btutto bene\b",
        q,
    ):
        return "status"
    # Domande metriche: la circonferenza va distinta da altezza e crescita.
    if (
        re.search(r"\b(?:tua circonferenza|circonferenza di vivo|circonferenza del tuo tronco)\b", q)
        or ("circonferenza" in q and re.search(r"\b(?:qual e|quale e|quanto|misura)\b", q))
        or re.search(r"\bquanto (?:e|misura) (?:grosso )?il (?:tuo )?tronco\b", q)
        or q == "circonferenza"
    ):
        return "circumference"
    if re.search(
        r"\bquanto sei alt[oa]\b|\b(?:qual e|quale e) la tua altezza\b"
        r"|\b(?:la )?tua altezza\b|\bquanto misuri\b"
        r"|\bquanti (?:cm|centimetri|metri) sei alt[oa]\b",
        q,
    ) and not re.search(r"\bcresciut[oa]\b", q):
        return "height"
    if re.search(
        r"\bquanto (?:sei|e|hai) cresciut[oa]\b|\b(?:la )?tua crescita\b"
        r"|\bcome procede la (?:tua )?crescita\b"
        r"|\bdi quanto (?:sei|e) cresciut[oa]\b"
        r"|\bquanto (?:sei|e) aumentat[oa]\b",
        q,
    ):
        return "growth"
    if not re.search(r"\b(?:ideale|ottimale|necessari[ao])\b|\bper (?:un|il) pioppo\b|\bper la fotosintesi\b", q):
        if re.search(
            r"\bmeteo\b|\bche tempo (?:fa|c e)\b|\b(?:quanti gradi|che temperatura)\b"
            r"|\b(?:qual e|quale e) (?:la )?(?:temperatura|umidita)\b"
            r"|\b(?:temperatura|umidita) (?:oggi|adesso|attuale)\b"
            r"|\b(?:fa caldo|fa freddo|piove oggi|sta piovendo)\b",
            q,
        ):
            return "weather"
    return None


def _get_json(url: str, cache_key: str, ttl: float) -> dict | None:
    now = time.monotonic()
    cached = _cache.get(cache_key)
    if cached and now - cached[0] < ttl:
        return cached[1] if isinstance(cached[1], dict) else None
    try:
        request = Request(url, headers={"User-Agent": "VivoFAQ/2.3", "Accept": "application/json"})
        with urlopen(request, timeout=3.5) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            return None
        _cache[cache_key] = (now, data)
        return data
    except (OSError, ValueError, TypeError) as exc:
        print(f"FAQ dati {cache_key} non disponibili: {exc}", flush=True)
        # Non esporre il cache scaduto come se fosse aggiornato.
        return None


def _number(value: object, *, positive: bool = False) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n) or (positive and n <= 0):
        return None
    return n


def _fmt(n: float, *, digits: int = 1) -> str:
    return f"{n:.{digits}f}".replace(".", ",")


def _date(value: object) -> str:
    if not isinstance(value, str):
        return "data non disponibile"
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return "data non disponibile"


def _measurements(data: dict | None) -> tuple[dict | None, dict | None, int]:
    if not isinstance(data, dict) or data.get("available") is not True:
        return None, None, 0
    first, latest = data.get("first"), data.get("latest")
    count = data.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        return None, None, 0
    if not isinstance(first, dict) or not isinstance(latest, dict):
        return None, None, 0
    return first, latest, count


def _height_sentence(data: dict | None) -> str:
    _, latest, count = _measurements(data)
    if not latest or count == 0:
        return "Non ho una misura di altezza consultabile in questo momento."
    height = _number(latest.get("height_cm"), positive=True)
    if height is None:
        return "L'ultima altezza registrata non è disponibile o non è valida."
    return f"Secondo l'ultimo rilievo pubblicato ({_date(latest.get('date'))}), sono alto {_fmt(height)} cm."


def _circumference_sentence(data: dict | None) -> str:
    first, latest, count = _measurements(data)
    if not latest:
        return "Non ho una misura di circonferenza consultabile in questo momento."
    latest_c = _number(latest.get("circumference_cm"), positive=True)
    if latest_c is None:
        return "L'ultima circonferenza registrata non è disponibile o non è valida."
    msg = f"La mia circonferenza misurata è {_fmt(latest_c)} cm (rilievo del {_date(latest.get('date'))})."
    first_c = _number(first.get("circumference_cm"), positive=True) if first else None
    if count >= 2 and first_c is not None:
        delta = latest_c - first_c
        if delta > 0:
            msg += f" Rispetto al primo rilievo è aumentata di {_fmt(delta)} cm."
        elif delta < 0:
            msg += f" Rispetto al primo rilievo risulta inferiore di {_fmt(abs(delta))} cm."
        else:
            msg += " Non risultano variazioni rispetto al primo rilievo."
    return msg


def _growth_sentence(data: dict | None) -> str:
    first, latest, count = _measurements(data)
    if not latest:
        return "Non risultano ancora misurazioni sufficienti sul sito."
    height = _number(latest.get("height_cm"), positive=True)
    if height is None:
        return "Le mie misurazioni attuali non sono sufficienti per calcolare la crescita."
    latest_date = _date(latest.get("date"))
    if count < 2:
        return (f"L'ultima misura pubblicata ({latest_date}) indica un'altezza di "
                f"{_fmt(height)} cm, ma manca un secondo rilievo per calcolare la crescita.")
    previous = _number(first.get("height_cm"), positive=True) if first else None
    if previous is None:
        return (f"L'ultima altezza registrata ({latest_date}) è {_fmt(height)} cm, "
                "ma non posso confrontarla con la prima misura.")
    delta = height - previous
    percentage = (delta / previous) * 100
    begin = _date(first.get("date"))
    if delta > 0:
        msg = (f"Dal {begin} al {latest_date} sono cresciuto di {_fmt(delta)} cm "
               f"in altezza (+{_fmt(percentage)}%). Ora misuro {_fmt(height)} cm")
    elif delta < 0:
        msg = (f"Dal {begin} al {latest_date} i rilievi indicano un'altezza inferiore "
               f"di {_fmt(abs(delta))} cm ({_fmt(percentage)}%). "
               f"L'ultima misura è {_fmt(height)} cm")
    else:
        msg = (f"Tra il {begin} e il {latest_date} non risulta una variazione di altezza; "
               f"l'ultima misura è {_fmt(height)} cm")
    first_c = _number(first.get("circumference_cm"), positive=True) if first else None
    last_c = _number(latest.get("circumference_cm"), positive=True)
    if first_c is not None and last_c is not None:
        circ = last_c - first_c
        if circ > 0:
            msg += f" e la circonferenza è aumentata di {_fmt(circ)} cm"
        elif circ < 0:
            msg += f" e la circonferenza risulta inferiore di {_fmt(abs(circ))} cm"
    return msg + "."


def _weather_sentence(data: dict | None) -> str:
    current = data.get("current") if isinstance(data, dict) else None
    if not isinstance(current, dict):
        return "Non riesco a recuperare la temperatura aggiornata in questo momento."
    temp = _number(current.get("temperature_2m"))
    humidity = _number(current.get("relative_humidity_2m"))
    if temp is None:
        return "Non riesco a recuperare la temperatura aggiornata in questo momento."
    msg = f"Qui nella zona del Parco Ulisse Dini la temperatura dell'aria è di {_fmt(temp)} °C"
    if humidity is not None and 0 <= humidity <= 100:
        msg += f" e l'umidità è del {_fmt(humidity, digits=0)}%"
    when = current.get("time")
    if isinstance(when, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?", when):
        msg += f" (Open-Meteo, rilevazione delle {when[11:16]} del {_date(when)})"
    else:
        msg += " (Open-Meteo, ultima rilevazione disponibile)"
    return msg + "."


CAPABILITIES = (
    "Posso raccontarti il progetto Vivo e spiegarti come funziona un pioppo bianco. "
    "Posso anche riportare il meteo della zona e le mie misurazioni di altezza "
    "e circonferenza, quando i servizi sono disponibili. Per le domande botaniche "
    "consulto le fonti del progetto; non posso verificare direttamente il mio stato di salute."
)


def build_faq_answer(intent: str, weather: dict | None, measurements: dict | None) -> str:
    if intent == "capabilities":
        return CAPABILITIES
    if intent == "weather":
        return _weather_sentence(weather)
    if intent == "height":
        return _height_sentence(measurements)
    if intent == "circumference":
        return _circumference_sentence(measurements)
    if intent == "growth":
        return _growth_sentence(measurements)
    if intent == "status":
        # Meteo e crescita vengono sempre considerati, anche se uno dei servizi fallisce.
        return (
            _weather_sentence(weather) + " " + _growth_sentence(measurements) + " "
            "Questi dati non bastano da soli a stabilire se sono in buona salute."
        )
    raise ValueError(f"Intent FAQ sconosciuto: {intent}")


def answer_faq(question: str) -> str | None:
    intent = faq_intent(question)
    if intent is None:
        return None
    if intent == "capabilities":
        return CAPABILITIES
    measurements = (
        _get_json(STATUS_URL, "measurements", 90.0)
        if intent in {"height", "growth", "circumference", "status"} else None
    )
    weather = (
        _get_json(WEATHER_URL, "weather", 120.0)
        if intent in {"weather", "status"} else None
    )
    return build_faq_answer(intent, weather, measurements)
