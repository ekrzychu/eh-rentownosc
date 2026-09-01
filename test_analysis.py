import unittest

from analysis import (
    analiza_pojemnosci,
    analiza_wplywu_wzglednego,
    analiza_wrazliwosci,
    analizuj_progi,
    czy_parametr_sterowalny,
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
        self.parametry = {
            **domyslne_parametry(),
            "srednia_kwota_ugody_percent": 20.0,
            "srednia_kwota_wyroku_percent": 20.0,
        }
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

    def test_bufor_kosztu_czynnosci_i_wysokiego_wps(self):
        for identyfikator in ("koszt_staly", "procesowe:Duplika", "wysoki_wps_procent"):
            with self.subTest(identyfikator=identyfikator):
                self.sprawdz_granice(identyfikator)

    def test_pelne_progi_zawieraja_kwoty_zakonczenia_i_podatek(self):
        identyfikatory = {x["id"] for x in analizuj_progi(self.parametry, 40.0)["pozycje"]}
        self.assertTrue({
            "srednia_kwota_ugody", "srednia_kwota_wyroku", "podatek_dochodowy"
        }.issubset(identyfikatory))

    def test_pelne_progi_zawieraja_parametry_ii_instancji(self):
        progi = {x["id"]: x for x in analizuj_progi(self.parametry, 40.0)["pozycje"]}
        for identyfikator in ("udzial_ii_instancji", "czas_ii_instancji"):
            self.assertIn(identyfikator, progi)
            self.assertNotIn("wykonalne_operacyjnie", progi[identyfikator])

    def test_progi_finansowe_nie_zaleza_od_statusu_rocznej_pojemnosci(self):
        przeciazony = self.parametry
        wykonalny = {**self.parametry, "liczba_pracownikow": 3}
        self.assertTrue(oblicz_model(przeciazony)["pojemnosc"]["przekroczona"])
        self.assertFalse(oblicz_model(wykonalny)["pojemnosc"]["przekroczona"])

        for parametry in (przeciazony, wykonalny):
            definicja_kwoty_ugody = {
                d["id"]: d for d in definicje_parametrow(parametry)
            }["srednia_kwota_ugody"]
            prog = znajdz_granice(parametry, definicja_kwoty_ugody, 40.0)
            self.assertTrue(prog["osiagalne"])
            na_granicy = oblicz_model(
                ustaw_parametr(parametry, "srednia_kwota_ugody", prog["granica"])
            )
            self.assertTrue(spelnia_cel(na_granicy, 40.0))
            self.assertAlmostEqual(na_granicy["ogolem"]["marza"], 40.0, places=6)

    def test_ranking_progow_nie_filtruje_przekroczonej_pojemnosci(self):
        self.assertTrue(oblicz_model(self.parametry)["pojemnosc"]["przekroczona"])
        progi = analizuj_progi(self.parametry, 0.0)
        ranking = ranking_progow(progi, "bufor", limit=100)
        self.assertTrue(ranking)
        self.assertTrue(all("wykonalne_operacyjnie" not in x for x in ranking))

    def test_najkrotsze_drogi_do_celu_sa_tylko_sterowalne(self):
        parametry = {**self.parametry, "koszt_staly_na_godzine": 250.0}
        ranking = ranking_progow(
            analizuj_progi(parametry, 0.0),
            "wymagana_zmiana",
            limit=100,
            tylko_sterowalne=True,
        )
        self.assertTrue(ranking)
        self.assertTrue(all(czy_parametr_sterowalny(x["id"]) for x in ranking))

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
            "srednia_kwota_ugody",
            "zawarte_ugody",
        )
        for cel in (0.0, 10.0, 20.0):
            analiza = analizuj_progi(self.parametry, cel)
            kluczowe = kluczowe_progi(self.parametry, cel, analiza)
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

    def test_podsumowanie_i_tabela_maja_te_same_progi(self):
        for cel in (0.0, 10.0, 20.0):
            analiza = analizuj_progi(self.parametry, cel)
            tabela = {pozycja["id"]: pozycja for pozycja in analiza["pozycje"]}
            podsumowanie = kluczowe_progi(self.parametry, cel, analiza)
            for identyfikator in ("srednia_kwota_ugody", "koszt_staly", "wynagrodzenie", "zawarte_ugody"):
                with self.subTest(cel=cel, identyfikator=identyfikator):
                    self.assertEqual(podsumowanie[identyfikator]["granica"], tabela[identyfikator]["granica"])

    def test_skalowanie_sredniego_czasu_przelicza_czynnosci_dzienne_lifecycle(self):
        bazowe = oblicz_model(self.parametry)
        obecny_czas = bazowe["bezposrednie_minuty_spraw"] / self.parametry["liczba_spraw"]
        zmienione = ustaw_parametr(self.parametry, "sredni_czas_bezposredni", obecny_czas / 2)
        po_zmianie = oblicz_model(zmienione)
        self.assertAlmostEqual(po_zmianie["bezposrednie_minuty_spraw"], bazowe["bezposrednie_minuty_spraw"] / 2)
        self.assertAlmostEqual(
            po_zmianie["czynnosci_dzienne_lifecycle_minuty"],
            bazowe["czynnosci_dzienne_lifecycle_minuty"] / 2,
        )
        self.assertEqual(zmienione["udzial_ii_instancji_percent"], self.parametry["udzial_ii_instancji_percent"])
        self.assertEqual(zmienione["obsluga_ii_instancji_minuty"], self.parametry["obsluga_ii_instancji_minuty"] / 2)

    def test_obsada_nie_jest_progiem_finansowym(self):
        identyfikatory = {
            pozycja["id"] for pozycja in analizuj_progi(self.parametry, 0.0)["pozycje"]
        }
        self.assertNotIn("liczba_pracownikow", identyfikatory)


class TestMutacjeIWrazliwosc(unittest.TestCase):
    def test_kwota_ugody_jest_sterowalna_a_wyrok_i_podatek_zewnetrzne(self):
        parametry = domyslne_parametry()
        pelne = {x["id"] for x in definicje_parametrow(parametry)}
        wrazliwosc = {x["Id"] for x in analiza_wrazliwosci(parametry)}
        self.assertTrue({
            "srednia_kwota_ugody", "srednia_kwota_wyroku", "podatek_dochodowy"
        }.issubset(pelne))
        self.assertIn("srednia_kwota_ugody", wrazliwosc)
        self.assertNotIn("srednia_kwota_wyroku", wrazliwosc)
        self.assertNotIn("podatek_dochodowy", wrazliwosc)

    def test_podatek_wplywa_na_prog_dodatniej_marzy_po_podatku(self):
        bazowe = {
            **domyslne_parametry(),
            "srednia_kwota_ugody_percent": 20.0,
            "srednia_kwota_wyroku_percent": 20.0,
        }
        bez_podatku = kluczowe_progi(
            {**bazowe, "podatek_dochodowy_percent": 0.0}, 10.0
        )["koszt_staly"]["granica"]
        z_podatkiem = kluczowe_progi(
            {**bazowe, "podatek_dochodowy_percent": 19.0}, 10.0
        )["koszt_staly"]["granica"]
        self.assertIsNotNone(bez_podatku)
        self.assertIsNotNone(z_podatkiem)
        self.assertLess(z_podatkiem, bez_podatku)

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

    def test_udzial_ii_instancji_jest_zalozeniem_a_czas_sterowalny(self):
        parametry = domyslne_parametry()
        definicje = {x["id"] for x in definicje_parametrow(parametry)}
        self.assertTrue({"udzial_ii_instancji", "czas_ii_instancji"}.issubset(definicje))
        wrazliwosc = {x["Id"] for x in analiza_wrazliwosci(parametry)}
        self.assertNotIn("udzial_ii_instancji", wrazliwosc)
        self.assertIn("czas_ii_instancji", wrazliwosc)
        progi = {x["id"] for x in analizuj_progi(parametry, 40.0)["pozycje"]}
        self.assertTrue({"udzial_ii_instancji", "czas_ii_instancji"}.issubset(progi))
        wplyw = {x["Id"] for x in analiza_wplywu_wzglednego(parametry)}
        self.assertNotIn("udzial_ii_instancji", wplyw)
        self.assertIn("czas_ii_instancji", wplyw)

    def test_wrazliwosc_wyklucza_zalozenia_zewnetrzne_i_skale(self):
        wykluczone = {
            "wysoki_wps_procent", "automatyczne_ramy", "udzial_ii_instancji",
            "niski_wps", "wysoki_wps", "udzial:P1", "udzial:P2", "udzial:P3",
            "kategoryczna_odmowa", "liczba_spraw", "liczba_pracownikow",
        }
        identyfikatory = {x["Id"] for x in analiza_wrazliwosci(domyslne_parametry())}
        self.assertTrue(wykluczone.isdisjoint(identyfikatory))
        self.assertTrue(all(czy_parametr_sterowalny(x) for x in identyfikatory))

    def test_wrazliwosc_zawiera_wymagane_dzwignie(self):
        wymagane = {
            "srednia_kwota_ugody", "koszt_staly", "wynagrodzenie", "szansa_na_ugode",
            "zawarte_ugody", "czas_ii_instancji", "procesowe:Duplika",
            "analiza_ugody", "dodatkowe:P1", "dodatkowe:P2", "dodatkowe:P3",
            "wspolne:Analiza sprawy i kompletowanie załącznika",
            "codzienne:Obsługa skrzynki ugody EH",
        }
        identyfikatory = {x["Id"] for x in analiza_wrazliwosci(domyslne_parametry())}
        self.assertTrue(wymagane.issubset(identyfikatory))

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
        zmieniony = oblicz_model(ustaw_parametr(
            parametry, "czas_ii_instancji", parametry["obsluga_ii_instancji_minuty"] - 1
        ))["ogolem"]["wynik"]
        self.assertAlmostEqual(
            analiza["Obsługa sprawy w II instancji"]["Wpływ skrócenia o 1 min"],
            zmieniony - bazowy,
        )

    def test_zmiana_10_i_20_procent_daje_poprawne_wartosci_dupliki(self):
        parametry = domyslne_parametry()
        dziesiec = {x["Id"]: x for x in analiza_wrazliwosci(parametry, 10.0)}[
            "procesowe:Duplika"
        ]
        dwadziescia = {x["Id"]: x for x in analiza_wrazliwosci(parametry, 20.0)}[
            "procesowe:Duplika"
        ]
        self.assertEqual(
            sorted(round(x, 8) for x in (
                dziesiec["Wartość po korzystnej zmianie"],
                dziesiec["Wartość po niekorzystnej zmianie"],
            )),
            [81.0, 99.0],
        )
        self.assertEqual(
            sorted(round(x, 8) for x in (
                dwadziescia["Wartość po korzystnej zmianie"],
                dwadziescia["Wartość po niekorzystnej zmianie"],
            )),
            [72.0, 108.0],
        )

    def test_wplyw_zgadza_sie_z_modelem_i_marza_w_obu_kierunkach(self):
        parametry = domyslne_parametry()
        pozycja = {x["Id"]: x for x in analiza_wrazliwosci(parametry, 10.0)}[
            "procesowe:Duplika"
        ]
        bazowy = oblicz_model(parametry)
        for wartosc_klucz, wynik_klucz, marza_klucz in (
            ("Wartość po korzystnej zmianie", "Wpływ korzystny", "Wpływ korzystny na marżę"),
            ("Wartość po niekorzystnej zmianie", "Wpływ niekorzystny", "Wpływ niekorzystny na marżę"),
        ):
            scenariusz = oblicz_model(ustaw_parametr(
                parametry, "procesowe:Duplika", pozycja[wartosc_klucz]
            ))
            self.assertAlmostEqual(
                pozycja[wynik_klucz],
                scenariusz["ogolem"]["wynik"] - bazowy["ogolem"]["wynik"],
            )
            self.assertAlmostEqual(
                pozycja[marza_klucz],
                scenariusz["ogolem"]["marza"] - bazowy["ogolem"]["marza"],
            )

    def test_procent_ugod_jest_zmieniany_wzglednie(self):
        pozycja = {
            x["Id"]: x for x in analiza_wrazliwosci(domyslne_parametry(), 10.0)
        }["zawarte_ugody"]
        self.assertEqual(
            sorted(round(x, 8) for x in (
                pozycja["Wartość po korzystnej zmianie"],
                pozycja["Wartość po niekorzystnej zmianie"],
            )),
            [45.0, 55.0],
        )

    def test_wartosc_zero_jest_pominieta(self):
        parametry = {**domyslne_parametry(), "koszt_staly_na_godzine": 0.0}
        identyfikatory = {x["Id"] for x in analiza_wrazliwosci(parametry)}
        self.assertNotIn("koszt_staly", identyfikatory)

    def test_czas_ii_instancji_nie_zmienia_przychodu(self):
        parametry = domyslne_parametry()
        bazowy_przychod = oblicz_model(parametry)["ogolem"]["przychod"]
        pozycja = {x["Id"]: x for x in analiza_wrazliwosci(parametry)}[
            "czas_ii_instancji"
        ]
        for klucz in ("Wartość po korzystnej zmianie", "Wartość po niekorzystnej zmianie"):
            scenariusz = oblicz_model(ustaw_parametr(
                parametry, "czas_ii_instancji", pozycja[klucz]
            ))
            self.assertEqual(scenariusz["ogolem"]["przychod"], bazowy_przychod)


class TestUgodyIPojemnosc(unittest.TestCase):
    def test_porownanie_automatycznych_ram_reaguje_na_analize_ugod(self):
        etykieta = "Automatyczne ramy w porównaniu z brakiem szans na ugodę"
        etykieta_wspolnej_analizy = (
            "Zawarta ugoda poza ramami w porównaniu z brakiem ugody poza ramami"
        )
        wyniki = {}

        for minuty_analizy in (0, 30, 60):
            parametry = {**domyslne_parametry(), "analiza_mozliwosci_ugody": minuty_analizy}
            model = oblicz_model(parametry)
            porownania = {
                wiersz["Porównanie"]: wiersz
                for wiersz in ekonomika_ugod(parametry)["porownania"]
            }
            automatyczne_ramy = porownania[etykieta]
            oczekiwana_roznica_minut = (
                model["czasy_sciezek_z_ii_instancja"]["brak_szans"]
                - model["czasy_sciezek_z_ii_instancja"]["automatyczne_ramy"]
            )
            oczekiwana_roznica_pln = (
                oczekiwana_roznica_minut
                / 60
                * model["koszt_godziny"]
                * (1 + sum(parametry["codzienne_czynnosci"].values()) / 480)
            )
            oczekiwany_wplyw_portfela = (
                oczekiwana_roznica_pln
                * parametry["liczba_spraw"]
                * model["udzialy_ugod"]["automatyczne_ramy"]
                / 100
            )
            self.assertAlmostEqual(
                automatyczne_ramy["Różnica minut na sprawę"], oczekiwana_roznica_minut
            )
            self.assertAlmostEqual(
                automatyczne_ramy["Różnica PLN na sprawę"], oczekiwana_roznica_pln
            )
            self.assertAlmostEqual(
                automatyczne_ramy["Wpływ roczny przy obecnym udziale"],
                oczekiwany_wplyw_portfela,
            )
            wyniki[minuty_analizy] = {
                "automatyczne_ramy": automatyczne_ramy,
                "wspolna_analiza": porownania[etykieta_wspolnej_analizy],
            }

        self.assertAlmostEqual(
            wyniki[30]["automatyczne_ramy"]["Różnica minut na sprawę"]
            - wyniki[0]["automatyczne_ramy"]["Różnica minut na sprawę"],
            30.0,
        )
        self.assertAlmostEqual(
            wyniki[60]["automatyczne_ramy"]["Różnica minut na sprawę"]
            - wyniki[0]["automatyczne_ramy"]["Różnica minut na sprawę"],
            60.0,
        )
        for kolumna in ("Różnica minut na sprawę", "Różnica PLN na sprawę"):
            self.assertAlmostEqual(
                wyniki[0]["wspolna_analiza"][kolumna],
                wyniki[60]["wspolna_analiza"][kolumna],
            )

    def test_minimalna_skutecznosc_ugod(self):
        parametry = domyslne_parametry()
        analiza = ekonomika_ugod(parametry)
        prog = analiza["minimalna_skutecznosc"]
        self.assertIsNotNone(prog)
        bez_prob = oblicz_model(ustaw_parametr(parametry, "szansa_na_ugode", 0.0))
        na_granicy = oblicz_model(ustaw_parametr(parametry, "zawarte_ugody", prog))
        self.assertAlmostEqual(
            na_granicy["ogolem"]["wynik"], bez_prob["ogolem"]["wynik"], places=6
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
        self.assertFalse(status_operacyjny(wynik_przeciazony)["wykonalne"])

        wykonalny = {**domyslne_parametry(), "liczba_pracownikow": 3}
        wynik_wykonalny = oblicz_model(wykonalny)
        self.assertEqual(
            spelnia_cel(wynik_wykonalny, 0.0),
            spelnia_cel(wynik_przeciazony, 0.0),
        )
        self.assertTrue(status_operacyjny(wynik_wykonalny)["wykonalne"])

    def test_rekomendacje_nie_filtruja_przez_roczna_pojemnosc(self):
        parametry = domyslne_parametry()
        self.assertTrue(oblicz_model(parametry)["pojemnosc"]["przekroczona"])
        wrazliwosc = analiza_wrazliwosci(parametry)
        progi = analizuj_progi(parametry, 0.0)
        ugody = ekonomika_ugod(parametry)
        pojemnosc = analiza_pojemnosci(parametry)
        rekomendacje = rekomendacje_deterministyczne(wrazliwosc, progi, ugody, pojemnosc)
        wszystkie = rekomendacje["najwiekszy_wplyw"]
        self.assertTrue(wszystkie)
        self.assertTrue(all(x["Wpływ na wynik roczny"] > 0 for x in wszystkie))
        self.assertTrue(all("Wykonalne operacyjnie" not in x for x in wszystkie))

    def test_rekomendacje_sa_sterowalne_posortowane_i_reaguja_na_procent(self):
        parametry = domyslne_parametry()
        progi = analizuj_progi(parametry, 0.0)
        ugody = ekonomika_ugod(parametry)
        wyniki = {}
        for procent in (10.0, 20.0):
            wrazliwosc = analiza_wrazliwosci(parametry, procent)
            rekomendacje = rekomendacje_deterministyczne(wrazliwosc, progi, ugody)
            top = rekomendacje["najwiekszy_wplyw"]
            self.assertTrue(all(czy_parametr_sterowalny(x["Id"]) for x in top))
            self.assertEqual(
                [x["Wpływ na wynik roczny"] for x in top],
                sorted((x["Wpływ na wynik roczny"] for x in top), reverse=True),
            )
            wyniki[procent] = {x["Id"]: x["Wpływ na wynik roczny"] for x in top}
        wspolne = set(wyniki[10.0]) & set(wyniki[20.0])
        self.assertTrue(any(
            abs(wyniki[10.0][x] - wyniki[20.0][x]) > 1e-6 for x in wspolne
        ))

    def test_rekomendacje_odrzucaja_zewnetrzny_wiersz_wejsciowy(self):
        parametry = domyslne_parametry()
        zewnetrzny = {
            "Id": "udzial_ii_instancji", "Parametr": "Udział spraw w II instancji",
            "Kategoria": "Operacyjne", "Wpływ na wynik roczny": 1_000_000.0,
        }
        rekomendacje = rekomendacje_deterministyczne(
            [zewnetrzny] + analiza_wrazliwosci(parametry),
            analizuj_progi(parametry, 0.0),
            ekonomika_ugod(parametry),
        )
        self.assertNotIn(
            "udzial_ii_instancji",
            {x["Id"] for x in rekomendacje["najwiekszy_wplyw"]},
        )

    def test_rekomendacje_nie_zawieraja_kwoty_wyroku_ani_podatku(self):
        parametry = domyslne_parametry()
        rekomendacje = rekomendacje_deterministyczne(
            analiza_wrazliwosci(parametry),
            analizuj_progi(parametry, 0.0),
            ekonomika_ugod(parametry),
        )
        identyfikatory = {x["Id"] for x in rekomendacje["najwiekszy_wplyw"]}
        self.assertIn("srednia_kwota_ugody", {
            x["Id"] for x in analiza_wrazliwosci(parametry)
        })
        self.assertNotIn("srednia_kwota_wyroku", identyfikatory)
        self.assertNotIn("podatek_dochodowy", identyfikatory)
        for klucz in ("najmniejsze_bufory", "najkrotsze_drogi"):
            self.assertTrue(all(
                czy_parametr_sterowalny(x["id"]) for x in rekomendacje[klucz]
            ))


class TestSymulator(unittest.TestCase):
    def test_wynik_symulatora_jest_wynikiem_modelu(self):
        parametry = domyslne_parametry()
        symulacja = symuluj_pojedyncza_zmiane(parametry, "srednia_kwota_ugody", 60.0)
        bezposrednio = oblicz_model(ustaw_parametr(parametry, "srednia_kwota_ugody", 60.0))
        self.assertEqual(symulacja["wyniki"]["ogolem"], bezposrednio["ogolem"])

    def test_symulator_nie_zwraca_oceny_rocznej_pojemnosci(self):
        parametry = domyslne_parametry()
        symulacja = symuluj_pojedyncza_zmiane(parametry, "srednia_kwota_ugody", 50.0)
        self.assertNotIn("status_operacyjny", symulacja)
        self.assertNotIn("Wykorzystanie pojemności", symulacja["scenariusz"])
        self.assertEqual(
            set(symulacja["scenariusz"]),
            {"Przychód", "Koszt", "Wynik przed podatkiem", "Podatek dochodowy", "Wynik po podatku", "Marża po podatku", "Godziny pracy"},
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
