import unittest

from model import (
    MINUTY_DNIA_PRACY,
    alokuj_liczby_z_procentow,
    domyslne_parametry,
    oblicz_czas_czynnosci_dziennych,
    oblicz_czasy_sciezek_ugod,
    oblicz_model,
    oblicz_podzial_spraw,
    oblicz_prog_czasu,
    oblicz_prog_fin,
    oblicz_prog_kosztu_stalego,
    oblicz_prog_wynagrodzenia_pracownika,
    oblicz_sredni_czas_sciezki_ugody,
    oblicz_udzialy_ugod,
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


class TestUgody(unittest.TestCase):
    def setUp(self):
        self.parametry = domyslne_parametry()

    def test_domyslne_udzialy_ugod(self):
        udzialy = oblicz_udzialy_ugod(15, 30, 50)
        self.assertEqual(udzialy["kategoryczna_odmowa"], 15.0)
        self.assertEqual(udzialy["automatyczne_ramy"], 30.0)
        self.assertEqual(udzialy["pozostale_sprawy"], 55.0)
        self.assertEqual(udzialy["szansa_poza_ramami"], 27.5)
        self.assertEqual(udzialy["brak_szans"], 27.5)
        self.assertEqual(udzialy["zakonczone_ugoda"], 57.5)
        self.assertEqual(udzialy["bez_ugody"], 42.5)
        self.assertAlmostEqual(
            sum(udzialy[nazwa] for nazwa in (
                "kategoryczna_odmowa", "automatyczne_ramy",
                "szansa_poza_ramami", "brak_szans",
            )),
            100.0,
        )

    def test_nieprawidlowe_udzialy_sa_odrzucane(self):
        with self.assertRaises(ValueError):
            oblicz_udzialy_ugod(60, 50, 50)
        with self.assertRaises(ValueError):
            oblicz_udzialy_ugod(15, 30, 101)

    def test_czasy_sciezek_i_srednia_wazona(self):
        czasy = oblicz_czasy_sciezek_ugod(
            self.parametry["wspolne_czynnosci"],
            self.parametry["procesowe_czynnosci"],
            self.parametry["ugodowe_czynnosci"],
            self.parametry["analiza_mozliwosci_ugody"],
        )
        self.assertEqual(czasy, {
            "kategoryczna_odmowa": 280,
            "automatyczne_ramy": 85,
            "szansa_poza_ramami": 115,
            "brak_szans": 310,
        })
        udzialy = oblicz_udzialy_ugod(15, 30, 50)
        self.assertAlmostEqual(oblicz_sredni_czas_sciezki_ugody(udzialy, czasy), 184.375)


class TestCzasDziennyIPojemnosc(unittest.TestCase):
    def test_domyslny_i_piecioosobowy_narzut(self):
        czynnosci = domyslne_parametry()["codzienne_czynnosci"]
        self.assertEqual(oblicz_czas_czynnosci_dziennych(1, 250, czynnosci), 22_500)
        self.assertEqual(oblicz_czas_czynnosci_dziennych(5, 250, czynnosci), 112_500)

    def test_narzut_dzienny_nie_zalezy_od_liczby_spraw(self):
        parametry_600 = domyslne_parametry()
        parametry_1000 = {**domyslne_parametry(), "liczba_spraw": 1000}
        wynik_600 = oblicz_model(parametry_600)
        wynik_1000 = oblicz_model(parametry_1000)
        self.assertEqual(wynik_600["czynnosci_dzienne_minuty"], 22_500)
        self.assertEqual(wynik_1000["czynnosci_dzienne_minuty"], 22_500)

    def test_pracownicy_nie_mnoza_czasu_spraw(self):
        jeden = oblicz_model(domyslne_parametry())
        pieciu = oblicz_model({**domyslne_parametry(), "liczba_pracownikow": 5})
        self.assertEqual(jeden["bezposrednie_minuty_spraw"], pieciu["bezposrednie_minuty_spraw"])
        self.assertEqual(jeden["czynnosci_dzienne_minuty"], 22_500)
        self.assertEqual(pieciu["czynnosci_dzienne_minuty"], 112_500)
        self.assertGreater(
            pieciu["pojemnosc"]["pojemnosc_spraw_minuty"],
            jeden["pojemnosc"]["pojemnosc_spraw_minuty"],
        )

    def test_brak_czasu_na_sprawy_jest_wykrywany(self):
        parametry = domyslne_parametry()
        parametry["codzienne_czynnosci"] = {"Czynności dzienne": MINUTY_DNIA_PRACY}
        wynik = oblicz_model(parametry)
        self.assertTrue(wynik["pojemnosc"]["brak_czasu_na_sprawy"])
        self.assertTrue(wynik["pojemnosc"]["przekroczona"])


class TestModelFinansowy(unittest.TestCase):
    def test_fin_i_wynagrodzenie(self):
        self.assertEqual(oblicz_wynagrodzenie(100_000, 10_000, 50), 4_500)
        self.assertEqual(100_000 * 70 / 100, 70_000)

    def test_domyslny_model_korzysta_z_nowego_czasu(self):
        wynik = oblicz_model()
        self.assertAlmostEqual(wynik["ogolem"]["przychod"], 780_000)
        self.assertAlmostEqual(wynik["srednie_minuty_sciezki_ugody"], 184.375)
        self.assertAlmostEqual(wynik["bezposrednie_minuty_spraw"], 215_745)
        self.assertAlmostEqual(wynik["czynnosci_dzienne_minuty"], 22_500)
        self.assertAlmostEqual(wynik["ogolem"]["koszt"], 560_074.2875)

    def test_koszty_grup_uzgadniaja_sie_z_portfelem(self):
        wynik = oblicz_model()
        self.assertAlmostEqual(
            sum(dane["koszt"] for dane in wynik["rodzaje"].values()),
            wynik["ogolem"]["koszt"],
        )
        self.assertAlmostEqual(
            wynik["wps_niski"]["koszt"] + wynik["wps_wysoki"]["koszt"],
            wynik["ogolem"]["koszt"],
        )

    def test_zero_spraw_nie_powoduje_dzielenia_przez_zero(self):
        wynik = oblicz_model({**domyslne_parametry(), "liczba_spraw": 0})
        self.assertEqual(wynik["narzut_dzienny_na_sprawe"], 0.0)
        self.assertAlmostEqual(wynik["ogolem"]["koszt"], wynik["czynnosci_dzienne_koszt"])


class TestProgiRentownosci(unittest.TestCase):
    def test_prog_czasu_zostawia_czynnosci_dzienne_bez_zmian(self):
        parametry = {
            **domyslne_parametry(),
            "koszt_staly_na_godzine": 150.0,
            "wynagrodzenie_pracownika_na_godzine": 150.0,
        }
        prog = oblicz_prog_czasu(parametry)
        self.assertTrue(prog["mozliwe"])
        self.assertFalse(prog["juz_rentowny"])

        skala = prog["docelowy_udzial_czasu"]
        zmienione = {
            **parametry,
            "wspolne_czynnosci": {k: v * skala for k, v in parametry["wspolne_czynnosci"].items()},
            "procesowe_czynnosci": {k: v * skala for k, v in parametry["procesowe_czynnosci"].items()},
            "ugodowe_czynnosci": {k: v * skala for k, v in parametry["ugodowe_czynnosci"].items()},
            "analiza_mozliwosci_ugody": parametry["analiza_mozliwosci_ugody"] * skala,
            "dodatkowe_minuty": {k: v * skala for k, v in parametry["dodatkowe_minuty"].items()},
        }
        wynik_przed = oblicz_model(parametry)
        wynik_po = oblicz_model(zmienione)
        self.assertEqual(
            wynik_przed["czynnosci_dzienne_minuty"],
            wynik_po["czynnosci_dzienne_minuty"],
        )
        self.assertAlmostEqual(wynik_po["ogolem"]["wynik"], 0, places=6)

    def test_progi_kosztow_uzywaja_wszystkich_godzin(self):
        parametry = domyslne_parametry()
        prog_staly = oblicz_prog_kosztu_stalego(parametry)
        self.assertTrue(prog_staly["mozliwe"])
        self.assertAlmostEqual(
            oblicz_model({**parametry, "koszt_staly_na_godzine": prog_staly["prog"]})["ogolem"]["wynik"],
            0,
            places=6,
        )

        prog_pracownik = oblicz_prog_wynagrodzenia_pracownika(parametry)
        self.assertTrue(prog_pracownik["mozliwe"])
        self.assertAlmostEqual(
            oblicz_model({**parametry, "wynagrodzenie_pracownika_na_godzine": prog_pracownik["prog"]})["ogolem"]["wynik"],
            0,
            places=6,
        )

    def test_prog_fin_uzywa_nowego_kosztu(self):
        parametry = domyslne_parametry()
        prog_fin = oblicz_prog_fin(parametry)
        self.assertTrue(prog_fin["mozliwe"])
        self.assertAlmostEqual(
            oblicz_model({**parametry, "fin_percent": prog_fin["prog"]})["ogolem"]["wynik"],
            0,
            delta=1.0,
        )

    def test_narzut_dzienny_moze_uniemozliwic_prog_czasu(self):
        parametry = {**domyslne_parametry(), "liczba_pracownikow": 100}
        self.assertFalse(oblicz_prog_czasu(parametry)["mozliwe"])

    def test_niemozliwe_progi_sa_oznaczone(self):
        parametry = {
            **domyslne_parametry(),
            "koszt_staly_na_godzine": 500.0,
            "wynagrodzenie_pracownika_na_godzine": 500.0,
        }
        self.assertFalse(oblicz_prog_kosztu_stalego(parametry)["mozliwe"])
        self.assertFalse(oblicz_prog_wynagrodzenia_pracownika(parametry)["mozliwe"])
        self.assertFalse(oblicz_prog_fin(parametry)["mozliwe"])


if __name__ == "__main__":
    unittest.main()
