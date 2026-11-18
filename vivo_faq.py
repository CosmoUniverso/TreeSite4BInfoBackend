"""Vivo v2.2 FAQ: risposte verificabili basate su dati meteorologici e misurazioni.

Niente LLM nei percorsi 'come stai' e 'quanto sei cresciuto':
- temperatura Open-Meteo (ambiente, non sensore Vivo);
- altezza/circonferenza dal sito Vercel (database Neon);
- nessuna diagnosi di salute dedotta da questi dati.
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
# Nel server locale gira un solo worker AI; questa cache evita richieste duplicate.
_cache: dict[str, tuple[float, object]] = {}


def _clean(q: str) -> str:
    text = unicodedata.normalize("NFKD", q.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text)).strip()


def faq_intent(question: str) -> str | None:
    """Classifica solo un insieme ristretto di FAQ, senza rubare domande botaniche."""
    q = _clean(question)
    if re.search(
        r"\bcome stai\b|\bcome sta vivo\b|\bcome sta (?:l |un )?albero\b"
        r"|\bcome ti senti\b|\bstai bene\b|\bcome va(?: oggi)?$",
        q,
    ):
        return "status"
    if re.search(
        r"\bquanto (?:sei|e|hai) cresciut[oa]\b|\b(?:la )?tua crescita\b"
        r"|\bquanto (?:sei|e) alt[oa]\b|\bquanto misuri\b"
        r"|\b(?:tua|la tua) (?:altezza|circonferenza)\b"
        r"|\bcome procede la crescita\b",
        q,
    ):
        return "growth"
    return None


def _get_json(url: str, cache_key: str, ttl: float) -> dict | None:
    cached = _cache.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < ttl:
        return cached[1] if isinstance(cached[1], dict) else None
    try:
        req = Request(url, headers={"User-Agent": "VivoFAQ/2.2", "Accept": "application/json"})
        with urlopen(req, timeout=3.5) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            return None
        _cache[cache_key] = (now, data)
        return data
    except (OSError, ValueError, TypeError) as exc:
        print(f"FAQ dati {cache_key} non disponibili: {exc}", flush=True)
        # Un eventuale dato scaduto non deve essere presentato come aggiornato.
        return None


def _finite_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _fmt(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _date(value: object) -> str:
    if not isinstance(value, str):
        return "data non disponibile"
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return "data non disponibile"


def _weather_sentence(data: dict | None) -> str:
    current = data.get("current", {}) if data else {}
    if not isinstance(current, dict):
        current = {}
    temp = _finite_number(current.get("temperature_2m"))
    humidity = _finite_number(current.get("relative_humidity_2m"))
    when = current.get("time")
    if temp is None:
        return "Non riesco a recuperare la temperatura aggiornata in questo momento."
    msg = f"Qui al Parco Ulisse Dini la temperatura dell'aria è di {_fmt(temp)} °C"
    if humidity is not None:
        msg += f" e l'umidità relativa è del {_fmt(humidity)}%"
    if isinstance(when, str) and len(when) >= 16:
        msg += f" (meteo esterno Open-Meteo, rilevazione {when[11:16]} del {_date(when)})"
    else:
        msg += " (meteo esterno Open-Meteo)"
    return msg + "."


def _growth_sentence(data: dict | None) -> str:
    if not data or data.get("available") is not True:
        return "Non riesco a consultare le mie misurazioni di crescita in questo momento."
    latest = data.get("latest")
    first = data.get("first")
    if not isinstance(latest, dict) or not isinstance(first, dict):
        return "Non risultano ancora misurazioni sufficienti sul sito."
    height = _finite_number(latest.get("height_cm"))
    if height is None or height <= 0:
        return "Le mie misurazioni attuali non sono sufficienti per calcolare la crescita."
    latest_day = _date(latest.get("date"))
    count = data.get("count", 0)
    if not isinstance(count, int) or count < 2:
        return (f"L'ultima misura pubblicata ({latest_day}) indica un'altezza di "
                f"{_fmt(height)} cm, ma manca un secondo rilievo per calcolare la crescita.")
    first_height = _finite_number(first.get("height_cm"))
    if first_height is None or first_height <= 0:
        return (f"L'ultima altezza registrata ({latest_day}) è {_fmt(height)} cm; "
                "non posso calcolare la variazione rispetto alla prima misura.")
    delta = height - first_height
    percent = delta / first_height * 100
    beginning = _date(first.get("date"))
    if delta > 0:
        trend = f"sono cresciuto di {_fmt(delta)} cm ({_fmt(percent)}%)"
    elif delta < 0:
        trend = f"le misure indicano una diminuzione di {_fmt(abs(delta))} cm ({_fmt(abs(percent))}%)"
    else:
        trend = "le due misure dell'altezza coincidono"
    msg = (f"Secondo le misurazioni pubblicate, dal {beginning} al {latest_day} "
           f"{trend}; l'ultima altezza registrata è {_fmt(height)} cm")
    first_circ = _finite_number(first.get("circumference_cm"))
    last_circ = _finite_number(latest.get("circumference_cm"))
    if first_circ is not None and last_circ is not None and first_circ > 0:
        circ_delta = last_circ - first_circ
        if circ_delta > 0:
            msg += f" e la circonferenza è aumentata di {_fmt(circ_delta)} cm"
        elif circ_delta < 0:
            msg += f" e la circonferenza misurata è diminuita di {_fmt(abs(circ_delta))} cm"
    return msg + "."


def build_faq_answer(intent: str, weather: dict | None, measurements: dict | None) -> str:
    growth = _growth_sentence(measurements)
    if intent == "growth":
        return growth
    return (
        _weather_sentence(weather) + " " + growth + " "
        + "Questi dati descrivono il meteo e la mia crescita, ma non bastano da soli "
          "a valutare il mio stato di salute."
    )


def answer_faq(question: str) -> str | None:
    intent = faq_intent(question)
    if intent is None:
        return None
    measurements = _get_json(STATUS_URL, "measurements", 90.0)
    weather = _get_json(WEATHER_URL, "weather", 120.0) if intent == "status" else None
    return build_faq_answer(intent, weather, measurements)
