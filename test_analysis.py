import unittest

from analysis import (
    analiza_pojemnosci,
    analiza_wplywu_wzglednego,
    analiza_wrazliwosci,
    analizuj_progi,
    definicje_parametrow,
    ekonomika_ugod,
    kluczowe_progi,
    maksymalna_liczba_spraw,
    minimalna_liczba_pracownikow,
    przelicz_udzial_rodzaju,
    ranking_progow,
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
                self.assertNotIn("wplywa_na_pojemnosc", prog)
                self.assertNotIn("wykonalne_operacyjnie", prog)

    def test_progi_finansowe_nie_zaleza_od_statusu_rocznej_pojemnosci(self):
        przeciazony = self.parametry
        wykonalny = {**self.parametry, "liczba_pracownikow": 3}
        self.assertTrue(oblicz_model(przeciazony)["pojemnosc"]["przekroczona"])
        self.assertFalse(oblicz_model(wykonalny)["pojemnosc"]["przekroczona"])

        for parametry in (przeciazony, wykonalny):
            definicja_fin = {
                d["id"]: d for d in definicje_parametrow(parametry)
            }["fin"]
            prog = znajdz_granice(parametry, definicja_fin, 40.0)
            self.assertTrue(prog["osiagalne"])
            na_granicy = oblicz_model(
                ustaw_parametr(parametry, "fin", prog["granica"])
            )
            self.assertTrue(spelnia_cel(na_granicy, 40.0))
            self.assertAlmostEqual(na_granicy["ogolem"]["marza"], 40.0, places=6)

    def test_ranking_progow_nie_filtruje_przekroczonej_pojemnosci(self):
        self.assertTrue(oblicz_model(self.parametry)["pojemnosc"]["przekroczona"])
        progi = analizuj_progi(self.parametry, 0.0)
        ranking = ranking_progow(progi, "bufor", limit=100)
        self.assertIn("fin", {pozycja["id"] for pozycja in ranking})
        self.assertTrue(all("wykonalne_operacyjnie" not in x for x in ranking))

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
        wplyw = {x["Id"] for x in analiza_wplywu_wzglednego(parametry)}
        self.assertTrue({"udzial_ii_instancji", "czas_ii_instancji"}.issubset(wplyw))

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

    def test_wplyw_wzgledny_zgadza_sie_z_modelem_i_marza(self):
        parametry = domyslne_parametry()
        analiza = {
            x["Id"]: x for x in analiza_wplywu_wzglednego(parametry)
        }
        pozycja = analiza["procesowe:Duplika"]
        nowa = pozycja["Obecnie"] + pozycja["Zmiana porównawcza"]
        bazowy = oblicz_model(parametry)
        scenariusz = oblicz_model(
            ustaw_parametr(parametry, "procesowe:Duplika", nowa)
        )
        self.assertAlmostEqual(
            pozycja["Wpływ na wynik"],
            scenariusz["ogolem"]["wynik"] - bazowy["ogolem"]["wynik"],
        )
        self.assertAlmostEqual(
            pozycja["Wpływ na marżę"],
            scenariusz["ogolem"]["marza"] - bazowy["ogolem"]["marza"],
        )
        self.assertAlmostEqual(abs(pozycja["Zmiana porównawcza"]), 9.0)

    def test_wplyw_wzgledny_udzialow_p_zachowuje_sume_100(self):
        parametry = domyslne_parametry()
        analiza = analiza_wplywu_wzglednego(parametry)
        for pozycja in (x for x in analiza if x["Id"].startswith("udzial:")):
            zmienione = ustaw_parametr(
                parametry,
                pozycja["Id"],
                pozycja["Obecnie"] + pozycja["Zmiana porównawcza"],
            )
            self.assertAlmostEqual(sum(zmienione["udzialy_rodzajow"].values()), 100.0)

    def test_wartosc_zero_uzywa_standardowego_kroku_zastepczego(self):
        parametry = {**domyslne_parametry(), "koszt_staly_na_godzine": 0.0}
        analiza = {x["Id"]: x for x in analiza_wplywu_wzglednego(parametry)}
        self.assertTrue(analiza["koszt_staly"]["Test zastępczy"])
        self.assertEqual(analiza["koszt_staly"]["Zmiana porównawcza"], 10.0)

    def test_wplyw_ii_instancji_nie_zmienia_przychodu(self):
        parametry = domyslne_parametry()
        bazowy_przychod = oblicz_model(parametry)["ogolem"]["przychod"]
        analiza = {x["Id"]: x for x in analiza_wplywu_wzglednego(parametry)}
        for identyfikator in ("udzial_ii_instancji", "czas_ii_instancji"):
            pozycja = analiza[identyfikator]
            for klucz in ("Korzystna zmiana", "Niekorzystna zmiana"):
                scenariusz = oblicz_model(ustaw_parametr(
                    parametry,
                    identyfikator,
                    pozycja["Obecnie"] + pozycja[klucz],
                ))
                self.assertEqual(scenariusz["ogolem"]["przychod"], bazowy_przychod)


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

    def test_rekomendacje_nie_filtruja_przez_roczna_pojemnosc(self):
        parametry = domyslne_parametry()
        self.assertTrue(oblicz_model(parametry)["pojemnosc"]["przekroczona"])
        wrazliwosc = analiza_wrazliwosci(parametry)
        progi = analizuj_progi(parametry, 0.0)
        ugody = ekonomika_ugod(parametry)
        pojemnosc = analiza_pojemnosci(parametry)
        rekomendacje = rekomendacje_deterministyczne(wrazliwosc, progi, ugody, pojemnosc)
        wszystkie = rekomendacje["najwiekszy_wplyw"] + rekomendacje["czynniki_zewnetrzne"]
        self.assertTrue(wszystkie)
        self.assertTrue(all(x["Wpływ na wynik roczny"] > 0 for x in wszystkie))
        self.assertTrue(all("Wykonalne operacyjnie" not in x for x in wszystkie))

    def test_finansowo_korzystna_ii_instancja_pozostaje_wrazliwoscia(self):
        parametry = {
            **domyslne_parametry(),
            "liczba_pracownikow": 3,
            "obsluga_ii_instancji_minuty": 1000,
        }
        wrazliwosc = {x["Id"]: x for x in analiza_wrazliwosci(parametry)}
        self.assertGreater(wrazliwosc["udzial_ii_instancji"]["Wpływ na wynik roczny"], 0)
        rekomendacje = rekomendacje_deterministyczne(
            [wrazliwosc["udzial_ii_instancji"]],
            analizuj_progi(parametry, 0.0),
            ekonomika_ugod(parametry),
        )
        self.assertEqual(
            [x["Id"] for x in rekomendacje["najwiekszy_wplyw"]],
            ["udzial_ii_instancji"],
        )


class TestSymulator(unittest.TestCase):
    def test_wynik_symulatora_jest_wynikiem_modelu(self):
        parametry = domyslne_parametry()
        symulacja = symuluj_pojedyncza_zmiane(parametry, "fin", 60.0)
        bezposrednio = oblicz_model(ustaw_parametr(parametry, "fin", 60.0))
        self.assertEqual(symulacja["wyniki"]["ogolem"], bezposrednio["ogolem"])

    def test_symulator_nie_zwraca_oceny_rocznej_pojemnosci(self):
        parametry = domyslne_parametry()
        symulacja = symuluj_pojedyncza_zmiane(parametry, "fin", 50.0)
        self.assertNotIn("status_operacyjny", symulacja)
        self.assertNotIn("Wykorzystanie pojemności", symulacja["scenariusz"])
        self.assertEqual(
            set(symulacja["scenariusz"]),
            {"Przychód", "Koszt", "Wynik", "Marża", "Godziny pracy"},
        )

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
