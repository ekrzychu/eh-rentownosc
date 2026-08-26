import unittest

from analysis import (
    analiza_pojemnosci,
    analiza_wrazliwosci,
    analizuj_progi,
    definicje_parametrow,
    ekonomika_ugod,
    kluczowe_progi,
    maksymalna_liczba_spraw,
    minimalna_liczba_pracownikow,
    przelicz_udzial_rodzaju,
    rekomendacje_deterministyczne,
    spelnia_cel,
    status_operacyjny,
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

    def test_bufor_zawartych_ugod_dla_marzy_40_procent(self):
        self.sprawdz_granice("zawarte_ugody", 40.0)

    def test_bufory_parametrow_ii_instancji(self):
        for identyfikator in ("udzial_ii_instancji", "czas_ii_instancji"):
            with self.subTest(identyfikator=identyfikator):
                prog = self.sprawdz_granice(identyfikator, 40.0)
                self.assertTrue(prog["wplywa_na_pojemnosc"])

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

    def test_kluczowe_progi_respektuja_marze_0_10_i_20_procent(self):
        identyfikatory = (
            "sredni_czas_bezposredni",
            "koszt_staly",
            "wynagrodzenie",
            "fin",
            "zawarte_ugody",
        )
        podsumowania = {}
        for cel in (0.0, 10.0, 20.0):
            analiza = analizuj_progi(self.parametry, cel)
            kluczowe = kluczowe_progi(self.parametry, cel, analiza)
            podsumowania[cel] = kluczowe
            for identyfikator in identyfikatory:
                with self.subTest(cel=cel, identyfikator=identyfikator):
                    prog = kluczowe[identyfikator]
                    if not prog["osiagalne"]:
                        continue
                    na_granicy = oblicz_model(
                        ustaw_parametr(self.parametry, identyfikator, prog["granica"])
                    )
                    if cel == 0:
                        self.assertAlmostEqual(na_granicy["ogolem"]["wynik"], 0.0, places=5)
                    else:
                        self.assertAlmostEqual(na_granicy["ogolem"]["marza"], cel, places=6)
                    krok = 0.01 if prog["zmiana"] > 0 else -0.01
                    poza = oblicz_model(
                        ustaw_parametr(self.parametry, identyfikator, prog["granica"] + krok)
                    )
                    self.assertFalse(spelnia_cel(poza, cel))
        for identyfikator in ("sredni_czas_bezposredni", "koszt_staly", "wynagrodzenie", "fin"):
            self.assertGreater(podsumowania[0.0][identyfikator]["granica"], podsumowania[10.0][identyfikator]["granica"])
            self.assertGreater(podsumowania[10.0][identyfikator]["granica"], podsumowania[20.0][identyfikator]["granica"])
        self.assertIsNone(podsumowania[10.0]["zawarte_ugody"]["granica"])
        prog_ugod_40 = kluczowe_progi(self.parametry, 40.0)["zawarte_ugody"]
        self.assertIsNotNone(prog_ugod_40["granica"])

    def test_podsumowanie_i_tabela_maja_te_same_progi(self):
        for cel in (0.0, 10.0, 20.0):
            analiza = analizuj_progi(self.parametry, cel)
            tabela = {pozycja["id"]: pozycja for pozycja in analiza["pozycje"]}
            podsumowanie = kluczowe_progi(self.parametry, cel, analiza)
            for identyfikator in ("fin", "koszt_staly", "wynagrodzenie", "zawarte_ugody"):
                with self.subTest(cel=cel, identyfikator=identyfikator):
                    self.assertEqual(podsumowanie[identyfikator]["granica"], tabela[identyfikator]["granica"])

    def test_skalowanie_sredniego_czasu_nie_zmienia_czynnosci_dziennych(self):
        bazowe = oblicz_model(self.parametry)
        obecny_czas = bazowe["bezposrednie_minuty_spraw"] / self.parametry["liczba_spraw"]
        zmienione = ustaw_parametr(self.parametry, "sredni_czas_bezposredni", obecny_czas / 2)
        po_zmianie = oblicz_model(zmienione)
        self.assertAlmostEqual(po_zmianie["bezposrednie_minuty_spraw"], bazowe["bezposrednie_minuty_spraw"] / 2)
        self.assertEqual(po_zmianie["czynnosci_dzienne_minuty"], bazowe["czynnosci_dzienne_minuty"])
        self.assertEqual(zmienione["udzial_ii_instancji_percent"], self.parametry["udzial_ii_instancji_percent"])
        self.assertEqual(zmienione["obsluga_ii_instancji_minuty"], self.parametry["obsluga_ii_instancji_minuty"] / 2)

    def test_granica_calkowita_zwraca_dokladna_bezpieczna_wartosc(self):
        analiza = analizuj_progi(self.parametry, 0.0)
        prog = next(pozycja for pozycja in analiza["pozycje"] if pozycja["id"] == "liczba_spraw")
        self.assertIsInstance(prog["granica"], int)
        self.assertTrue(spelnia_cel(oblicz_model(ustaw_parametr(self.parametry, "liczba_spraw", prog["granica"])), 0.0))
        self.assertFalse(spelnia_cel(oblicz_model(ustaw_parametr(self.parametry, "liczba_spraw", prog["granica"] - 1)), 0.0))


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
        oczekiwane.add("czas_ii_instancji")
        self.assertTrue(oczekiwane.issubset(identyfikatory))

    def test_analityka_zawiera_obie_dzwignie_ii_instancji(self):
        parametry = domyslne_parametry()
        definicje = {x["id"] for x in definicje_parametrow(parametry)}
        self.assertTrue({"udzial_ii_instancji", "czas_ii_instancji"}.issubset(definicje))
        wrazliwosc = {x["Id"] for x in analiza_wrazliwosci(parametry)}
        self.assertTrue({"udzial_ii_instancji", "czas_ii_instancji"}.issubset(wrazliwosc))
        progi = {x["id"] for x in analizuj_progi(parametry, 40.0)["pozycje"]}
        self.assertTrue({"udzial_ii_instancji", "czas_ii_instancji"}.issubset(progi))

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

    def test_wartosc_minuty_ii_instancji_jest_wazona_modelem(self):
        parametry = domyslne_parametry()
        analiza = {x["Czynność"]: x for x in wartosc_skrocenia_czynnosci(parametry)}
        bazowy = oblicz_model(parametry)["ogolem"]["wynik"]
        zmieniony = oblicz_model(ustaw_parametr(parametry, "czas_ii_instancji", 179))["ogolem"]["wynik"]
        self.assertAlmostEqual(
            analiza["Obsługa sprawy w II instancji"]["Wpływ skrócenia o 1 min"],
            zmieniony - bazowy,
        )


class TestUgodyIPojemnosc(unittest.TestCase):
    def test_minimalna_skutecznosc_ugod(self):
        parametry = domyslne_parametry()
        analiza = ekonomika_ugod(parametry)
        prog = analiza["minimalna_skutecznosc"]
        czasy = oblicz_model(parametry)["czasy_sciezek_z_ii_instancja"]
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

    def test_ii_instancja_zwieksza_ekonomiczna_wartosc_ugod(self):
        parametry = domyslne_parametry()
        bez_ii = ekonomika_ugod({**parametry, "udzial_ii_instancji_percent": 0.0})
        z_ii = ekonomika_ugod(parametry)
        self.assertLess(z_ii["minimalna_skutecznosc"], bez_ii["minimalna_skutecznosc"])
        self.assertGreater(z_ii["strategia_wplyw_pln"], bez_ii["strategia_wplyw_pln"])

    def test_minimum_pracownikow_i_maksimum_spraw_sa_granicami(self):
        parametry = domyslne_parametry()
        minimum = minimalna_liczba_pracownikow(parametry)
        self.assertIsNotNone(minimum)
        assert minimum is not None
        self.assertFalse(oblicz_model(ustaw_parametr(parametry, "liczba_pracownikow", minimum))["pojemnosc"]["przekroczona"])
        self.assertTrue(oblicz_model(ustaw_parametr(parametry, "liczba_pracownikow", minimum - 1))["pojemnosc"]["przekroczona"])

        maksimum = maksymalna_liczba_spraw(parametry)
        self.assertIsNotNone(maksimum)
        assert maksimum is not None
        self.assertFalse(oblicz_model(ustaw_parametr(parametry, "liczba_spraw", maksimum))["pojemnosc"]["przekroczona"])
        self.assertTrue(oblicz_model(ustaw_parametr(parametry, "liczba_spraw", maksimum + 1))["pojemnosc"]["przekroczona"])

    def test_brak_pojemnosci_nie_jest_raportowany_jako_zero_spraw(self):
        parametry = domyslne_parametry()
        parametry["codzienne_czynnosci"] = {"Czynności dzienne": 600}
        self.assertIsNone(maksymalna_liczba_spraw(parametry))
        self.assertEqual(analiza_pojemnosci(parametry)["powod_braku_maksimum"], "brak_pojemnosci")

    def test_analiza_pojemnosci_ma_szesc_segmentow(self):
        self.assertEqual(len(analiza_pojemnosci(domyslne_parametry())["segmenty"]), 6)

    def test_ii_instancja_zmniejsza_maksymalna_pojemnosc(self):
        parametry = domyslne_parametry()
        bez_ii = analiza_pojemnosci({**parametry, "udzial_ii_instancji_percent": 0.0})
        z_ii = analiza_pojemnosci(parametry)
        self.assertLess(z_ii["maksymalne_sprawy"], bez_ii["maksymalne_sprawy"])

    def test_status_rozroznia_rentownosc_i_wykonalnosc(self):
        przeciazony = domyslne_parametry()
        wynik_przeciazony = oblicz_model(przeciazony)
        self.assertTrue(spelnia_cel(wynik_przeciazony, 0.0))
        self.assertFalse(status_operacyjny(wynik_przeciazony)["wykonalne"])

        wykonalny = {**domyslne_parametry(), "liczba_pracownikow": 3}
        wynik_wykonalny = oblicz_model(wykonalny)
        self.assertTrue(spelnia_cel(wynik_wykonalny, 0.0))
        self.assertTrue(status_operacyjny(wynik_wykonalny)["wykonalne"])

    def test_rekomendacje_odrzucaja_niewykonalne_scenariusze(self):
        parametry = domyslne_parametry()
        wrazliwosc = analiza_wrazliwosci(parametry)
        progi = analizuj_progi(parametry, 0.0)
        ugody = ekonomika_ugod(parametry)
        pojemnosc = analiza_pojemnosci(parametry)
        rekomendacje = rekomendacje_deterministyczne(wrazliwosc, progi, ugody, pojemnosc)
        wszystkie = rekomendacje["najwiekszy_wplyw"] + rekomendacje["czynniki_zewnetrzne"]
        self.assertTrue(all(pozycja["Wykonalne operacyjnie"] for pozycja in wszystkie))

        wykonalne_parametry = {**domyslne_parametry(), "liczba_pracownikow": 3}
        wykonalne_rekomendacje = rekomendacje_deterministyczne(
            analiza_wrazliwosci(wykonalne_parametry),
            analizuj_progi(wykonalne_parametry, 0.0),
            ekonomika_ugod(wykonalne_parametry),
            analiza_pojemnosci(wykonalne_parametry),
        )
        self.assertTrue(wykonalne_rekomendacje["najwiekszy_wplyw"])
        self.assertTrue(all(
            pozycja["Wykonalne operacyjnie"]
            for pozycja in wykonalne_rekomendacje["najwiekszy_wplyw"]
        ))

    def test_udzial_ii_instancji_moze_trafic_do_rekomendacji(self):
        parametry = {
            **domyslne_parametry(),
            "liczba_pracownikow": 3,
            "obsluga_ii_instancji_minuty": 1000,
        }
        rekomendacje = rekomendacje_deterministyczne(
            analiza_wrazliwosci(parametry),
            analizuj_progi(parametry, 0.0),
            ekonomika_ugod(parametry),
            analiza_pojemnosci(parametry),
        )
        self.assertIn(
            "udzial_ii_instancji",
            {pozycja["Id"] for pozycja in rekomendacje["najwiekszy_wplyw"]},
        )


class TestSymulator(unittest.TestCase):
    def test_wynik_symulatora_jest_wynikiem_modelu(self):
        parametry = domyslne_parametry()
        symulacja = symuluj_pojedyncza_zmiane(parametry, "fin", 60.0)
        bezposrednio = oblicz_model(ustaw_parametr(parametry, "fin", 60.0))
        self.assertEqual(symulacja["wyniki"]["ogolem"], bezposrednio["ogolem"])

    def test_symulator_zwraca_status_operacyjny(self):
        parametry = domyslne_parametry()
        self.assertFalse(symuluj_pojedyncza_zmiane(parametry, "fin", 50.0)["status_operacyjny"]["wykonalne"])
        self.assertTrue(symuluj_pojedyncza_zmiane(parametry, "liczba_pracownikow", 3)["status_operacyjny"]["wykonalne"])

    def test_symulator_ii_instancji_jest_zgodny_z_modelem_i_nie_zmienia_przychodu(self):
        parametry = domyslne_parametry()
        for identyfikator, wartosc in (("udzial_ii_instancji", 75.0), ("czas_ii_instancji", 300.0)):
            with self.subTest(identyfikator=identyfikator):
                symulacja = symuluj_pojedyncza_zmiane(parametry, identyfikator, wartosc)
                bezposrednio = oblicz_model(ustaw_parametr(parametry, identyfikator, wartosc))
                self.assertEqual(symulacja["wyniki"]["ogolem"], bezposrednio["ogolem"])
                self.assertEqual(symulacja["scenariusz"]["Przychód"], symulacja["obecnie"]["Przychód"])


if __name__ == "__main__":
    unittest.main()
