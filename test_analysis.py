import unittest

from analysis import (
    analiza_pojemnosci,
    definicje_parametrow,
    ekonomika_ugod,
    maksymalna_liczba_spraw,
    minimalna_liczba_pracownikow,
    przelicz_udzial_rodzaju,
    spelnia_cel,
    symuluj_pojedyncza_zmiane,
    ustaw_parametr,
    wartosc_skrocenia_czynnosci,
    znajdz_granice,
)
from model import domyslne_parametry, oblicz_model


class TestSilnikProgow(unittest.TestCase):
    def setUp(self):
        self.parametry = domyslne_parametry()
        self.definicje = {d["id"]: d for d in definicje_parametrow(self.parametry)}

    def sprawdz_granice(self, identyfikator, cel=0.0):
        self.assertTrue(spelnia_cel(oblicz_model(self.parametry), cel))
        prog = znajdz_granice(self.parametry, self.definicje[identyfikator], cel)
        self.assertTrue(prog["osiagalne"])
        na_granicy = oblicz_model(ustaw_parametr(self.parametry, identyfikator, prog["granica"]))
        self.assertTrue(spelnia_cel(na_granicy, cel))
        krok = 0.01 if prog["zmiana"] > 0 else -0.01
        poza = oblicz_model(ustaw_parametr(self.parametry, identyfikator, prog["granica"] + krok))
        self.assertFalse(spelnia_cel(poza, cel))
        return prog

    def test_bufor_kosztu_fin_czynnosci_i_wysokiego_wps(self):
        for identyfikator in ("koszt_staly", "fin", "procesowe:Duplika", "wysoki_wps_procent"):
            with self.subTest(identyfikator=identyfikator):
                self.sprawdz_granice(identyfikator)

    def test_bufor_zawartych_ugod_dla_marzy_15_procent(self):
        self.sprawdz_granice("zawarte_ugody", 15.0)

    def test_scenariusz_nierentowny_i_zmiana_niewystarczajaca(self):
        parametry = {**self.parametry, "koszt_staly_na_godzine": 250.0}
        definicje = {d["id"]: d for d in definicje_parametrow(parametry)}
        prog = znajdz_granice(parametry, definicje["koszt_staly"], 0.0)
        self.assertEqual(prog["typ"], "wymagana_zmiana")
        self.assertTrue(prog["osiagalne"])
        self.assertTrue(spelnia_cel(oblicz_model(ustaw_parametr(parametry, "koszt_staly", prog["granica"])), 0.0))

        bardzo_drogo = {**self.parametry, "koszt_staly_na_godzine": 1000.0}
        definicje = {d["id"]: d for d in definicje_parametrow(bardzo_drogo)}
        prog_czynnosci = znajdz_granice(bardzo_drogo, definicje["procesowe:Duplika"], 0.0)
        self.assertFalse(prog_czynnosci["osiagalne"])


class TestMutacjeIWrazliwosc(unittest.TestCase):
    def test_katalog_zawiera_wszystkie_edytowalne_czasy(self):
        parametry = domyslne_parametry()
        identyfikatory = {x["id"] for x in definicje_parametrow(parametry)}
        grupy = {
            "wspolne": "wspolne_czynnosci",
            "procesowe": "procesowe_czynnosci",
            "ugodowe": "ugodowe_czynnosci",
            "codzienne": "codzienne_czynnosci",
            "dodatkowe": "dodatkowe_minuty",
        }
        oczekiwane = {
            f"{prefiks}:{nazwa}"
            for prefiks, klucz in grupy.items()
            for nazwa in parametry[klucz]
        }
        oczekiwane.add("analiza_ugody")
        self.assertTrue(oczekiwane.issubset(identyfikatory))

    def test_udzial_p1_zachowuje_sume_i_relacje(self):
        wynik = przelicz_udzial_rodzaju({"P1": 25.0, "P2": 58.0, "P3": 17.0}, "P1", 35.0)
        self.assertAlmostEqual(sum(wynik.values()), 100.0)
        self.assertAlmostEqual(wynik["P2"] / wynik["P3"], 58 / 17)

    def test_mutacja_ugody_zachowuje_hierarchie(self):
        parametry = domyslne_parametry()
        zmienione = ustaw_parametr(parametry, "zawarte_ugody", 72.0)
        wynik = oblicz_model(zmienione)
        sciezki = ("kategoryczna_odmowa", "automatyczne_ramy", "brak_szans", "zawarte_poza_ramami", "brak_ugody_poza_ramami")
        self.assertAlmostEqual(sum(wynik["udzialy_ugod"][x] for x in sciezki), 100.0)

    def test_wartosc_minuty_zgadza_sie_z_modelem(self):
        parametry = domyslne_parametry()
        analiza = {x["Czynność"]: x for x in wartosc_skrocenia_czynnosci(parametry)}
        bazowy = oblicz_model(parametry)["ogolem"]["wynik"]
        zmieniony = oblicz_model(ustaw_parametr(parametry, "procesowe:Duplika", parametry["procesowe_czynnosci"]["Duplika"] - 1))["ogolem"]["wynik"]
        self.assertAlmostEqual(analiza["Duplika"]["Wpływ skrócenia o 1 min"], zmieniony - bazowy)


class TestUgodyIPojemnosc(unittest.TestCase):
    def test_minimalna_skutecznosc_ugod(self):
        parametry = domyslne_parametry()
        analiza = ekonomika_ugod(parametry)
        prog = analiza["minimalna_skutecznosc"]
        czasy = oblicz_model(parametry)["czasy_sciezek_ugod"]
        oczekiwany = prog / 100 * czasy["zawarte_poza_ramami"] + (1 - prog / 100) * czasy["brak_ugody_poza_ramami"]
        self.assertAlmostEqual(oczekiwany, czasy["brak_szans"], places=6)
        self.assertLess(
            (prog + 0.01) / 100 * czasy["zawarte_poza_ramami"] + (1 - (prog + 0.01) / 100) * czasy["brak_ugody_poza_ramami"],
            czasy["brak_szans"],
        )
        self.assertGreater(
            (prog - 0.01) / 100 * czasy["zawarte_poza_ramami"] + (1 - (prog - 0.01) / 100) * czasy["brak_ugody_poza_ramami"],
            czasy["brak_szans"],
        )

    def test_minimum_pracownikow_i_maksimum_spraw_sa_granicami(self):
        parametry = domyslne_parametry()
        minimum = minimalna_liczba_pracownikow(parametry)
        self.assertFalse(oblicz_model(ustaw_parametr(parametry, "liczba_pracownikow", minimum))["pojemnosc"]["przekroczona"])
        self.assertTrue(oblicz_model(ustaw_parametr(parametry, "liczba_pracownikow", minimum - 1))["pojemnosc"]["przekroczona"])

        maksimum = maksymalna_liczba_spraw(parametry)
        self.assertFalse(oblicz_model(ustaw_parametr(parametry, "liczba_spraw", maksimum))["pojemnosc"]["przekroczona"])
        self.assertTrue(oblicz_model(ustaw_parametr(parametry, "liczba_spraw", maksimum + 1))["pojemnosc"]["przekroczona"])

    def test_analiza_pojemnosci_ma_szesc_segmentow(self):
        self.assertEqual(len(analiza_pojemnosci(domyslne_parametry())["segmenty"]), 6)


class TestSymulator(unittest.TestCase):
    def test_wynik_symulatora_jest_wynikiem_modelu(self):
        parametry = domyslne_parametry()
        symulacja = symuluj_pojedyncza_zmiane(parametry, "fin", 60.0)
        bezposrednio = oblicz_model(ustaw_parametr(parametry, "fin", 60.0))
        self.assertEqual(symulacja["wyniki"]["ogolem"], bezposrednio["ogolem"])


if __name__ == "__main__":
    unittest.main()
