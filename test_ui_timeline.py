import unittest

import pandas as pd

from ui_timeline import (
    _break_even_value,
    _capacity_charts,
    _cumulative_chart,
    _kwota_skrocona,
)


class TestWidokCzasowy(unittest.TestCase):
    def setUp(self):
        self.table = pd.DataFrame(
            {
                "Miesiąc": list(range(1, 61)),
                "Wynik skumulowany przed podatkiem": [month - 20 for month in range(1, 61)],
                "Backlog na koniec (h)": [float(month) for month in range(1, 61)],
                "Nowa praca (h)": [10.0] * 60,
                "Praca oczekująca (h)": [20.0] * 60,
                "Wykonana praca (h)": [9.0] * 60,
                "Wykorzystanie pojemności (%)": [100.0] * 60,
            }
        )

    def test_wykresy_maja_jawna_dziedzine_miesiecy_od_jednego(self):
        cumulative = _cumulative_chart(self.table, 60, 20).to_dict()
        domains = [
            layer["encoding"]["x"]["scale"]["domain"]
            for layer in cumulative["layer"]
            if "x" in layer.get("encoding", {})
        ]
        self.assertTrue(domains)
        self.assertTrue(all(domain == [1, 60] for domain in domains))

        backlog, utilization = _capacity_charts(self.table, 60)
        self.assertEqual(
            backlog.to_dict()["encoding"]["x"]["scale"]["domain"], [1, 60]
        )
        utilization_domains = [
            layer["encoding"]["x"]["scale"]["domain"]
            for layer in utilization.to_dict()["layer"]
            if "x" in layer.get("encoding", {})
        ]
        self.assertTrue(all(domain == [1, 60] for domain in utilization_domains))

    def test_niewystarczajaca_pojemnosc_ma_krotki_kpi_i_pelne_wyjasnienie(self):
        value, help_text = _break_even_value(
            {"break_even_status": "nie_osiagnieto", "break_even_miesiac": None},
            {"status_pojemnosci": "Niewystarczająca"},
        )
        self.assertEqual(value, "Brak")
        self.assertIn("Brak trwałego break-even", help_text)

    def test_duze_kwoty_sa_formatowane_kompaktowo(self):
        self.assertEqual(_kwota_skrocona(339_364.8), "339,4 tys. zł")
        self.assertEqual(_kwota_skrocona(1_430_000), "1,43 mln zł")


if __name__ == "__main__":
    unittest.main()
