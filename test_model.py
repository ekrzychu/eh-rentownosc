import unittest

from model import (
    alokuj_liczby_z_procentow, domyslne_parametry, oblicz_model,
    oblicz_podzial_spraw, oblicz_prog_czasu, oblicz_prog_fin,
    oblicz_prog_kosztu_stalego, oblicz_prog_wynagrodzenia_pracownika,
    oblicz_wynagrodzenie,
)


class TestAlokacjaSpraw(unittest.TestCase):
    def test_domyslny_podzial(self):
        alokacja = alokuj_liczby_z_procentow(600, {"P1": 25, "P2": 58, "P3": 17})
        self.assertEqual(alokacja, {"P1": 150, "P2": 348, "P3": 102})

    def test_domyslny_podzial_wps(self):
        podzial = oblicz_podzial_spraw(600, {"P1": 25, "P2": 58, "P3": 17}, 80)
        self.assertEqual(podzial["P1"], {"wysoki_wps": 120, "niski_wps": 30})
        self.assertEqual(podzial["P2"], {"wysoki_wps": 278, "niski_wps": 70})
        self.assertEqual(podzial["P3"], {"wysoki_wps": 82, "niski_wps": 20})

    def test_niewygodna_liczba_spraw_sumuje_sie_poprawnie(self):
        alokacja = alokuj_liczby_z_procentow(601, {"P1": 25, "P2": 58, "P3": 17})
        self.assertEqual(sum(alokacja.values()), 601)

    def test_fin_i_wynagrodzenie(self):
        self.assertEqual(oblicz_wynagrodzenie(100_000, 10_000, 50), 4_500)
        self.assertEqual(100_000 * 70 / 100, 70_000)

    def test_regresja_fin_50_procent(self):
        wynik = oblicz_model()
        self.assertAlmostEqual(wynik["ogolem"]["przychod"], 780_000)
        self.assertAlmostEqual(wynik["ogolem"]["koszt"], 846_582.10)
        self.assertAlmostEqual(wynik["ogolem"]["wynik"], -66_582.10)

    def test_progi_rentownosci(self):
        parametry = domyslne_parametry()
        prog_czasu = oblicz_prog_czasu(parametry)
        self.assertTrue(prog_czasu["mozliwe"])
        czas_docelowy = parametry["podstawowe_czynnosci"].copy()
        czas_docelowy["Duplika"] -= prog_czasu["redukcja_minut_na_sprawe"]
        self.assertAlmostEqual(oblicz_model({**parametry, "podstawowe_czynnosci": czas_docelowy})["ogolem"]["wynik"], 0, places=6)

        prog_staly = oblicz_prog_kosztu_stalego(parametry)
        self.assertTrue(prog_staly["mozliwe"])
        self.assertAlmostEqual(oblicz_model({**parametry, "koszt_staly_na_godzine": prog_staly["prog"]})["ogolem"]["wynik"], 0, places=6)

        prog_pracownik = oblicz_prog_wynagrodzenia_pracownika(parametry)
        self.assertTrue(prog_pracownik["mozliwe"])
        self.assertAlmostEqual(oblicz_model({**parametry, "wynagrodzenie_pracownika_na_godzine": prog_pracownik["prog"]})["ogolem"]["wynik"], 0, places=6)

        prog_fin = oblicz_prog_fin(parametry)
        self.assertTrue(prog_fin["mozliwe"])
        self.assertAlmostEqual(oblicz_model({**parametry, "fin_percent": prog_fin["prog"]})["ogolem"]["wynik"], 0, delta=1.0)

    def test_niemozliwe_progi_sa_oznaczone(self):
        parametry = {**domyslne_parametry(), "koszt_staly_na_godzine": 500.0, "wynagrodzenie_pracownika_na_godzine": 500.0}
        self.assertFalse(oblicz_prog_kosztu_stalego(parametry)["mozliwe"])
        self.assertFalse(oblicz_prog_wynagrodzenia_pracownika(parametry)["mozliwe"])
        self.assertFalse(oblicz_prog_fin(parametry)["mozliwe"])


if __name__ == "__main__":
    unittest.main()
