"""Offline tests for Vivo FAQ. Numeric values are fixtures, not live readings."""
import unittest
from unittest.mock import patch
import vivo_faq as faq

SAMPLE = {
    "available": True, "count": 2,
    "first": {"date": "2026-04-02", "height_cm": 33.6, "circumference_cm": 1.8},
    "latest": {"date": "2026-11-11", "height_cm": 43.3, "circumference_cm": 2.4},
}
WEATHER = {"current": {"temperature_2m": 7.9, "relative_humidity_2m": 89,
                       "time": "2026-11-18T11:30"}}


class TestFaq(unittest.TestCase):
    def setUp(self):
        faq._cache.clear()

    def test_six_intents(self):
        cases = {
            "status": ["Come stai?", "Come ti senti oggi?", "Come sta Vivo?", "Tutto bene?", "Come va?"],
            "height": ["Quanto sei alto?", "Qual è la tua altezza?", "Quanto misuri?", "Quanti centimetri sei alto?"],
            "growth": ["Quanto sei cresciuto?", "Come procede la tua crescita?", "Di quanto sei cresciuto?"],
            "circumference": ["Qual è la tua circonferenza?", "Quanto misura il tuo tronco?"],
            "weather": ["Che tempo fa?", "Quanti gradi ci sono?", "Che temperatura c'è?", "Meteo oggi?", "Fa freddo?"],
            "capabilities": ["Cosa puoi fare?", "Che cosa sai fare?", "Come puoi aiutarmi?", "Quali sono le tue capacità?"],
        }
        for intent, questions in cases.items():
            for question in questions:
                with self.subTest(question=question):
                    self.assertEqual(faq.faq_intent(question), intent)

    def test_do_not_hijack_botany(self):
        for question in [
            "Come funziona la fotosintesi?", "Quanto cresce un pioppo bianco?",
            "Come crescono le radici?", "Qual è la temperatura ideale per un pioppo?",
            "Perché la circonferenza aumenta con l'età?", "Dove sei stato piantato?",
        ]:
            with self.subTest(question=question):
                self.assertIsNone(faq.faq_intent(question))

    def test_status_contains_weather_and_growth(self):
        text = faq.build_faq_answer("status", WEATHER, SAMPLE)
        for value in ["7,9 °C", "89%", "11:30", "9,7 cm", "+28,9%", "43,3 cm", "0,6 cm"]:
            self.assertIn(value, text)
        self.assertIn("non bastano", text)
        self.assertNotIn("sono in salute", text)
        self.assertNotIn("sto bene", text.lower())

    def test_height_is_direct_and_only_height(self):
        text = faq.build_faq_answer("height", None, SAMPLE)
        self.assertIn("43,3 cm", text)
        self.assertIn("11/11/2026", text)
        self.assertNotIn("9,7 cm", text)
        self.assertNotIn("temperatura", text)

    def test_growth_includes_interval_and_circumference_delta(self):
        text = faq.build_faq_answer("growth", None, SAMPLE)
        self.assertIn("02/04/2026", text)
        self.assertIn("11/11/2026", text)
        self.assertIn("9,7 cm", text)
        self.assertIn("28,9%", text)
        self.assertIn("0,6 cm", text)
        self.assertNotIn("temperatura", text)

    def test_circumference_is_direct(self):
        text = faq.build_faq_answer("circumference", None, SAMPLE)
        self.assertIn("2,4 cm", text)
        self.assertIn("0,6 cm", text)
        self.assertNotIn("43,3", text)

    def test_weather_is_only_weather(self):
        text = faq.build_faq_answer("weather", WEATHER, None)
        self.assertIn("7,9 °C", text)
        self.assertIn("89%", text)
        self.assertNotIn("cresciut", text)
        self.assertNotIn("circonferenza", text)

    def test_capabilities_is_immediate(self):
        with patch.object(faq, "_get_json") as lookup:
            text = faq.answer_faq("Cosa puoi fare?")
        lookup.assert_not_called()
        self.assertIn("meteo", text)
        self.assertIn("misurazioni", text)

    def test_routing_only_fetches_required_sources(self):
        for prompt, expected in [
            ("Quanto sei alto?", ["measurements"]),
            ("Quanto sei cresciuto?", ["measurements"]),
            ("Qual è la circonferenza?", ["measurements"]),
            ("Che tempo fa?", ["weather"]),
            ("Come stai?", ["measurements", "weather"]),
        ]:
            with self.subTest(prompt=prompt), patch.object(faq, "_get_json") as mock:
                mock.side_effect = lambda _url, key, _ttl: SAMPLE if key == "measurements" else WEATHER
                self.assertTrue(faq.answer_faq(prompt))
                self.assertEqual([c.args[1] for c in mock.call_args_list], expected)

    def test_no_measurements(self):
        none = {"available": True, "count": 0, "first": None, "latest": None}
        self.assertIn("Non risultano", faq.build_faq_answer("growth", None, none))
        self.assertIn("non ho una misura", faq.build_faq_answer("height", None, none).lower())
        status = faq.build_faq_answer("status", WEATHER, none)
        self.assertIn("7,9 °C", status)
        self.assertIn("Non risultano", status)

    def test_single_measure(self):
        single = dict(SAMPLE, count=1, first=SAMPLE["latest"])
        self.assertIn("manca un secondo rilievo", faq.build_faq_answer("growth", None, single))
        self.assertIn("43,3 cm", faq.build_faq_answer("height", None, single))
        self.assertIn("2,4 cm", faq.build_faq_answer("circumference", None, single))

    def test_missing_current_height_no_fabrication(self):
        bad = dict(SAMPLE, latest=dict(SAMPLE["latest"], height_cm=None))
        self.assertIn("non sono sufficienti", faq.build_faq_answer("growth", None, bad))
        self.assertIn("non è disponibile", faq.build_faq_answer("height", None, bad))
        self.assertIn("2,4 cm", faq.build_faq_answer("circumference", None, bad))

    def test_invalid_numeric_values(self):
        bad = dict(SAMPLE, latest=dict(SAMPLE["latest"], height_cm="NaN", circumference_cm=True))
        self.assertNotIn("nan", faq.build_faq_answer("growth", None, bad).lower())
        self.assertIn("non è disponibile", faq.build_faq_answer("circumference", None, bad))

    def test_no_weather_response(self):
        status = faq.build_faq_answer("status", None, SAMPLE)
        self.assertIn("Non riesco a recuperare la temperatura", status)
        self.assertIn("9,7 cm", status)

    def test_negative_growth_is_not_referred_as_growth(self):
        bad = dict(SAMPLE, latest=dict(SAMPLE["latest"], height_cm=30.0))
        text = faq.build_faq_answer("growth", None, bad)
        self.assertIn("altezza inferiore", text)
        self.assertNotIn("sono cresciuto", text)

    def test_missing_humidity_and_timestamp(self):
        weather = {"current": {"temperature_2m": 8.0}}
        text = faq.build_faq_answer("weather", weather, None)
        self.assertIn("8,0 °C", text)
        self.assertNotIn("umidità", text)
        self.assertIn("ultima rilevazione disponibile", text)

    def test_intent_unknown_fails_explicitly(self):
        with self.assertRaises(ValueError):
            faq.build_faq_answer("unsupported", None, None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
