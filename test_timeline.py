import unittest

from model import MINUTY_DNIA_PRACY, domyslne_parametry, oblicz_model
from timeline import (
    domyslne_parametry_czasowe,
    minimalna_liczba_pracownikow_dla_stabilnosci,
    oblicz_model_czasowy,
    oblicz_pojemnosc_miesieczna,
    porownaj_obsade,
    wyznacz_break_even,
)


def pierwszy_miesiac_z_wartoscia(wiersze, klucz):
    return next(w["Miesiąc"] for w in wiersze if w[klucz] > 1e-8)


class TestCiaglyNaplywIUzgodnienieKohorty(unittest.TestCase):
    def setUp(self):
        self.parametry = domyslne_parametry()

    def test_600_rocznie_daje_50_spraw_w_kazdym_miesiacu(self):
        wynik = oblicz_model_czasowy(self.parametry)
        self.assertEqual(len(wynik["tabela_miesieczna"]), 60)
        self.assertTrue(
            all(w["Nowe sprawy"] == 50.0 for w in wynik["tabela_miesieczna"])
        )

    def test_przez_60_miesiecy_wplywa_3000_spraw(self):
        wynik = oblicz_model_czasowy(self.parametry)
        self.assertEqual(
            sum(w["Nowe sprawy"] for w in wynik["tabela_miesieczna"]), 3000.0
        )
        self.assertEqual(wynik["podsumowanie"]["laczny_naplyw"], 3000.0)

    def test_zmiana_horyzontu_nie_zatrzymuje_naplywu(self):
        wynik = oblicz_model_czasowy(
            self.parametry, {"horyzont_miesiace": 97}
        )
        self.assertEqual(len(wynik["tabela_miesieczna"]), 97)
        self.assertTrue(
            all(w["Nowe sprawy"] == 50.0 for w in wynik["tabela_miesieczna"])
        )

    def test_miesieczna_kohorta_uzgadnia_ekonomie_lifecycle(self):
        lifecycle = oblicz_model(self.parametry)
        wynik = oblicz_model_czasowy(self.parametry)
        zbudowana = wynik["walidacja"]["kohorta_zbudowana"]
        self.assertAlmostEqual(
            zbudowana["revenue"], lifecycle["ogolem"]["przychod"] / 12
        )
        self.assertAlmostEqual(
            zbudowana["direct_minutes"],
            lifecycle["bezposrednie_minuty_spraw"] / 12,
        )
        self.assertAlmostEqual(zbudowana["cases"], 50.0)

    def test_domyslne_parametry_nie_maja_trybu_ani_okresu_naplywu(self):
        self.assertEqual(
            domyslne_parametry_czasowe(),
            {
                "miesiace_do_ugody": 6,
                "miesiace_do_wyroku_i": 9,
                "miesiace_wyrok_i_do_ii": 6,
                "opoznienie_platnosci_miesiace": 0,
                "horyzont_miesiace": 60,
            },
        )
        with self.assertRaises(ValueError):
            oblicz_model_czasowy(
                self.parametry, {"tryb_naplywu": "wszystkie na początku"}
            )


class TestKosztIPojemnoscObsady(unittest.TestCase):
    def setUp(self):
        self.parametry = domyslne_parametry()

    def test_dwoch_pracownikow_daje_dwa_razy_wieksza_pojemnosc_i_koszt(self):
        jeden = oblicz_pojemnosc_miesieczna(
            {**self.parametry, "liczba_pracownikow": 1}
        )
        dwoch = oblicz_pojemnosc_miesieczna(
            {**self.parametry, "liczba_pracownikow": 2}
        )
        for klucz in (
            "pojemnosc_brutto_minuty",
            "czynnosci_dzienne_minuty",
            "pojemnosc_na_sprawy_minuty",
            "miesieczny_koszt_zespolu",
        ):
            self.assertAlmostEqual(dwoch[klucz], 2 * jeden[klucz])

    def test_wzor_na_domyslna_pojemnosc_brutto(self):
        pojemnosc = oblicz_pojemnosc_miesieczna(self.parametry)
        self.assertAlmostEqual(
            pojemnosc["pojemnosc_brutto_minuty"], 2 * 251 * 480 / 12
        )
        self.assertAlmostEqual(pojemnosc["pojemnosc_brutto_minuty"], 20_080)

    def test_brak_pracy_bezposredniej_nie_usuwa_kosztu_zespolu(self):
        wynik = oblicz_model_czasowy({**self.parametry, "liczba_spraw": 0})
        wiersz = wynik["tabela_miesieczna"][0]
        self.assertEqual(wiersz["Wykonana praca (h)"], 0.0)
        self.assertAlmostEqual(
            wiersz["Niewykorzystana pojemność (h)"],
            wiersz["Pojemność brutto (h)"] - wiersz["Czynności dzienne (h)"],
        )
        self.assertGreater(wiersz["Koszt zespołu"], 0.0)
        self.assertEqual(
            wiersz["Wynik miesięczny przed podatkiem"], -wiersz["Koszt zespołu"]
        )

    def test_czynnosci_dzienne_zuzywaja_moc_bez_drugiego_kosztu(self):
        normalne = oblicz_model_czasowy(self.parametry)
        bez_dziennych_parametry = {**self.parametry, "codzienne_czynnosci": {}}
        bez_dziennych = oblicz_model_czasowy(bez_dziennych_parametry)
        self.assertGreater(normalne["tabela_miesieczna"][0]["Czynności dzienne (h)"], 0)
        self.assertLess(
            normalne["pojemnosc"]["pojemnosc_na_sprawy_minuty"],
            bez_dziennych["pojemnosc"]["pojemnosc_na_sprawy_minuty"],
        )
        self.assertEqual(
            normalne["pojemnosc"]["miesieczny_koszt_zespolu"],
            bez_dziennych["pojemnosc"]["miesieczny_koszt_zespolu"],
        )

    def test_koszt_zespolu_nie_odejmuje_ponownie_niewykorzystania(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 10},
            {"horyzont_miesiace": 12},
        )
        for wiersz in wynik["tabela_miesieczna"]:
            self.assertAlmostEqual(
                wiersz["Wynik miesięczny przed podatkiem"],
                wiersz["Przychód razem"] - wiersz["Koszt zespołu"],
            )

    def test_czynnosci_dzienne_moga_wyczerpac_cala_pojemnosc(self):
        parametry = {
            **self.parametry,
            "codzienne_czynnosci": {"Czynności dzienne": MINUTY_DNIA_PRACY},
        }
        with self.assertRaisesRegex(ValueError, "zużywają cały dzień pracy"):
            oblicz_model_czasowy(parametry, {"horyzont_miesiace": 12})

    def test_lifecycle_i_timeline_maja_wspolna_fizyke_pojemnosci(self):
        lifecycle = oblicz_model(self.parametry)
        pojemnosc = oblicz_pojemnosc_miesieczna(
            {**self.parametry, "liczba_pracownikow": 1}, lifecycle
        )
        dzienne = sum(self.parametry["codzienne_czynnosci"].values())
        self.assertAlmostEqual(
            pojemnosc["pojemnosc_na_sprawy_minuty"] * 12,
            self.parametry["liczba_dni_pracy_w_roku"]
            * (MINUTY_DNIA_PRACY - dzienne),
        )
        self.assertAlmostEqual(
            lifecycle["laczne_minuty"],
            lifecycle["bezposrednie_minuty_spraw"]
            * MINUTY_DNIA_PRACY
            / (MINUTY_DNIA_PRACY - dzienne),
        )


class TestKolejkaIOpoznieniePrzychodu(unittest.TestCase):
    def setUp(self):
        self.parametry = domyslne_parametry()

    def test_niedostateczna_obsada_tworzy_rosnacy_backlog_i_nie_gubi_pracy(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 1}
        )
        self.assertEqual(wynik["pojemnosc"]["status_pojemnosci"], "Niewystarczająca")
        self.assertGreater(
            wynik["tabela_miesieczna"][-1]["Backlog na koniec (h)"],
            wynik["tabela_miesieczna"][29]["Backlog na koniec (h)"],
        )
        walidacja = wynik["walidacja"]
        self.assertAlmostEqual(
            walidacja["praca_wykonana_minuty"] + walidacja["backlog_minuty"],
            walidacja["praca_nalezna_do_horyzontu_minuty"],
        )

    def test_brak_pojemnosci_opoznia_zakonczenia_i_przychod(self):
        niedobor = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 1}
        )
        zapas = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 10}
        )
        self.assertGreater(
            niedobor["podsumowanie"]["maksymalne_opoznienie_pojemnosci_miesiace"],
            0,
        )
        self.assertEqual(
            zapas["podsumowanie"]["maksymalne_opoznienie_pojemnosci_miesiace"],
            0,
        )
        self.assertGreater(
            niedobor["podsumowanie"]["srednie_opoznienie_pojemnosci_miesiace"],
            zapas["podsumowanie"]["srednie_opoznienie_pojemnosci_miesiace"],
        )

    def test_nadmiar_obsady_nie_skroca_nominalnego_czasu(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 50}
        )
        tabela = wynik["tabela_miesieczna"]
        self.assertEqual(pierwszy_miesiac_z_wartoscia(tabela, "Przychód z ugód"), 7)
        self.assertEqual(pierwszy_miesiac_z_wartoscia(tabela, "Przychód z wyroków"), 10)

    def test_opoznienie_platnosci_przesuwa_przychod_i_break_even(self):
        parametry = {
            **self.parametry,
            "liczba_pracownikow": 3,
            "koszt_staly_na_godzine": 1.0,
            "wynagrodzenie_pracownika_na_godzine": 1.0,
        }
        bez = oblicz_model_czasowy(parametry)
        opozniony = oblicz_model_czasowy(
            parametry, {"opoznienie_platnosci_miesiace": 4}
        )
        self.assertEqual(
            pierwszy_miesiac_z_wartoscia(opozniony["tabela_miesieczna"], "Przychód razem"),
            pierwszy_miesiac_z_wartoscia(bez["tabela_miesieczna"], "Przychód razem") + 4,
        )
        self.assertNotEqual(
            bez["kpi"]["break_even_miesiac"], opozniony["kpi"]["break_even_miesiac"]
        )
        self.assertEqual(
            bez["pojemnosc"]["pojemnosc_na_sprawy_minuty"],
            opozniony["pojemnosc"]["pojemnosc_na_sprawy_minuty"],
        )
        self.assertEqual(
            [w["Nowa praca (h)"] for w in bez["tabela_miesieczna"]],
            [w["Nowa praca (h)"] for w in opozniony["tabela_miesieczna"]],
        )
        self.assertAlmostEqual(
            bez["walidacja"]["dojrzaly_przychod_roczny"],
            opozniony["walidacja"]["dojrzaly_przychod_roczny"],
        )

    def test_wiecej_pracownikow_ma_koszt_i_moze_zmniejszyc_backlog(self):
        jeden = oblicz_model_czasowy({**self.parametry, "liczba_pracownikow": 1})
        pieciu = oblicz_model_czasowy({**self.parametry, "liczba_pracownikow": 5})
        self.assertGreater(
            pieciu["pojemnosc"]["miesieczny_koszt_zespolu"],
            jeden["pojemnosc"]["miesieczny_koszt_zespolu"],
        )
        self.assertGreater(
            pieciu["pojemnosc"]["pojemnosc_na_sprawy_minuty"],
            jeden["pojemnosc"]["pojemnosc_na_sprawy_minuty"],
        )
        self.assertLess(
            pieciu["podsumowanie"]["backlog_koniec_godziny"],
            jeden["podsumowanie"]["backlog_koniec_godziny"],
        )


class TestStabilnoscIDojrzalosc(unittest.TestCase):
    def setUp(self):
        self.parametry = domyslne_parametry()

    def test_status_stabilny_i_niewystarczajacy(self):
        jeden = oblicz_model_czasowy({**self.parametry, "liczba_pracownikow": 1})
        trzech = oblicz_model_czasowy({**self.parametry, "liczba_pracownikow": 3})
        self.assertEqual(jeden["pojemnosc"]["status_pojemnosci"], "Niewystarczająca")
        self.assertEqual(trzech["pojemnosc"]["status_pojemnosci"], "Stabilna")

    def test_minimalna_stabilna_obsada(self):
        self.assertEqual(
            minimalna_liczba_pracownikow_dla_stabilnosci(self.parametry), 3
        )

    def test_dojrzaly_przychod_i_popyt_uzgadniaja_sie_rocznie(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 10},
            {"horyzont_miesiace": 120},
        )
        self.assertTrue(wynik["podsumowanie"]["dojrzalosc_osiagnieta"])
        self.assertAlmostEqual(
            wynik["walidacja"]["dojrzaly_przychod_roczny"],
            wynik["walidacja"]["roczny_przychod_lifecycle"],
        )
        self.assertAlmostEqual(
            wynik["walidacja"]["dojrzaly_popyt_roczny_minuty"],
            wynik["walidacja"]["roczne_minuty_bezposrednie_lifecycle"],
        )

    def test_krotki_horyzont_nie_udaje_dojrzalosci(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 10},
            {"horyzont_miesiace": 12},
        )
        self.assertFalse(wynik["podsumowanie"]["dojrzalosc_osiagnieta"])
        self.assertIsNone(wynik["kpi"]["wynik_miesieczny_w_stanie_stabilnym"])

    def test_break_even_jest_trwaly_tylko_przy_stabilnej_dodatniej_ekonomii(self):
        tanio = {
            **self.parametry,
            "koszt_staly_na_godzine": 1.0,
            "wynagrodzenie_pracownika_na_godzine": 1.0,
        }
        niedobor = oblicz_model_czasowy({**tanio, "liczba_pracownikow": 1})
        stabilny = oblicz_model_czasowy({**tanio, "liczba_pracownikow": 3})
        self.assertEqual(niedobor["kpi"]["break_even_status"], "osiagniety")
        self.assertEqual(
            niedobor["kpi"]["status_break_even"],
            "Brak trwałego break-even przy obecnej obsadzie",
        )
        self.assertEqual(stabilny["kpi"]["status_break_even"], "Break-even trwały")

    def test_niedobor_ma_kontekstowy_status_i_biezace_pelne_wykorzystanie(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 1}
        )
        self.assertEqual(
            wynik["podsumowanie"]["status_stanu_stabilnego"],
            "Nieosiągalny przy obecnej obsadzie",
        )
        self.assertNotIn(
            "Poza horyzontem", wynik["podsumowanie"]["status_stanu_stabilnego"]
        )
        self.assertAlmostEqual(
            wynik["pojemnosc"]["biezace_wykorzystanie_percent"], 100.0
        )
        self.assertAlmostEqual(
            wynik["pojemnosc"]["ostatnie_12_miesiecy_wykorzystanie_percent"],
            100.0,
        )
        self.assertLess(
            wynik["pojemnosc"]["srednie_wykorzystanie_percent"], 100.0
        )

    def test_dodatnia_ekonomia_lifecycle_i_dobrana_obsada_sa_spojne(self):
        tanio = {
            **self.parametry,
            "koszt_staly_na_godzine": 10.0,
            "wynagrodzenie_pracownika_na_godzine": 10.0,
            "liczba_pracownikow": 3,
        }
        lifecycle = oblicz_model(tanio)
        temporal = oblicz_model_czasowy(tanio, {"horyzont_miesiace": 120})
        self.assertGreater(lifecycle["ogolem"]["wynik_przed_podatkiem"], 0.0)
        self.assertEqual(temporal["pojemnosc"]["status_pojemnosci"], "Stabilna")
        self.assertGreater(
            temporal["kpi"]["wynik_miesieczny_w_stanie_stabilnym"], 0.0
        )

    def test_nadmiar_obsady_moze_dac_strate_mimo_dodatniej_marzy_lifecycle(self):
        tanio = {
            **self.parametry,
            "koszt_staly_na_godzine": 10.0,
            "wynagrodzenie_pracownika_na_godzine": 10.0,
            "liczba_pracownikow": 20,
        }
        lifecycle = oblicz_model(tanio)
        temporal = oblicz_model_czasowy(tanio, {"horyzont_miesiace": 120})
        self.assertGreater(lifecycle["ogolem"]["wynik_przed_podatkiem"], 0.0)
        self.assertLess(
            temporal["kpi"]["wynik_miesieczny_w_stanie_stabilnym"], 0.0
        )
        self.assertGreater(
            temporal["diagnoza"]["koszt_niewykorzystanej_pojemnosci_horyzont"],
            0.0,
        )

    def test_niedobor_opoznia_przychod_a_minimalna_obsada_ma_dodatnia_ekonomie(self):
        tanio = {
            **self.parametry,
            "koszt_staly_na_godzine": 10.0,
            "wynagrodzenie_pracownika_na_godzine": 10.0,
            "liczba_pracownikow": 1,
        }
        temporal = oblicz_model_czasowy(tanio, {"horyzont_miesiace": 120})
        self.assertTrue(temporal["diagnoza"]["strukturalny_niedobor_pojemnosci"])
        self.assertGreater(temporal["podsumowanie"]["backlog_koniec_godziny"], 0.0)
        self.assertGreater(
            temporal["diagnoza"]["wynik_miesieczny_przy_minimalnej_obsadzie"],
            0.0,
        )

    def test_miesieczne_rozliczenie_backlogu_i_aktywnych_spraw(self):
        wynik = oblicz_model_czasowy(self.parametry)
        for row in wynik["tabela_miesieczna"]:
            self.assertAlmostEqual(
                row["Praca oczekująca (h)"],
                row["Backlog na początku (h)"] + row["Nowa praca (h)"],
            )
            self.assertAlmostEqual(
                row["Backlog na koniec (h)"],
                row["Praca oczekująca (h)"] - row["Wykonana praca (h)"],
            )
        walidacja = wynik["walidacja"]
        self.assertAlmostEqual(
            walidacja["laczny_naplyw_spraw"]
            - walidacja["laczne_zakonczenia_spraw"],
            walidacja["aktywne_sprawy"],
        )

    def test_miesiace_danych_zaczynaja_sie_od_jednego(self):
        wynik = oblicz_model_czasowy(self.parametry)
        miesiace = [row["Miesiąc"] for row in wynik["tabela_miesieczna"]]
        self.assertEqual(miesiace[0], 1)
        self.assertTrue(all(month >= 1 for month in miesiace))

    def test_porownanie_obsady_nie_wybiera_najlepszego_wiersza(self):
        rows = porownaj_obsade(
            self.parametry, {"horyzont_miesiace": 36}, 5
        )
        self.assertEqual([row["Liczba pracowników"] for row in rows], [1, 2, 3, 4, 5])
        self.assertTrue(all("Najlepszy" not in row for row in rows))


class TestDefinicjaBreakEven(unittest.TestCase):
    def test_nie_liczy_miesiaca_zero(self):
        wynik = wyznacz_break_even([0.0, -10.0, 0.0], [0, 1, 2])
        self.assertEqual(wynik["miesiac"], 2)

    def test_nigdy_ujemny_oznacza_od_poczatku(self):
        self.assertEqual(
            wyznacz_break_even([0.0, 10.0, 5.0])["etykieta"], "Od początku"
        )

    def test_brak_powrotu_w_horyzoncie(self):
        self.assertEqual(
            wyznacz_break_even([-10.0, -2.0, -1.0])["etykieta"],
            "Nie osiągnięto w horyzoncie",
        )


class TestPrzypadkiBrzegowe(unittest.TestCase):
    def setUp(self):
        self.parametry = domyslne_parametry()

    def test_zero_rocznego_naplywu(self):
        wynik = oblicz_model_czasowy({**self.parametry, "liczba_spraw": 0})
        self.assertTrue(all(w["Nowe sprawy"] == 0 for w in wynik["tabela_miesieczna"]))
        self.assertEqual(wynik["podsumowanie"]["aktywne_sprawy"], 0.0)
        self.assertEqual(wynik["podsumowanie"]["backlog_koniec_godziny"], 0.0)

    def test_zero_pracownikow(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 0},
            {"horyzont_miesiace": 24},
        )
        self.assertEqual(wynik["pojemnosc"]["pojemnosc_brutto_minuty"], 0.0)
        self.assertEqual(wynik["pojemnosc"]["miesieczny_koszt_zespolu"], 0.0)
        self.assertGreater(wynik["podsumowanie"]["backlog_koniec_godziny"], 0.0)

    def test_zero_czynnosci_dziennych(self):
        parametry = {**self.parametry, "codzienne_czynnosci": {}}
        wynik = oblicz_model_czasowy(parametry, {"horyzont_miesiace": 12})
        self.assertEqual(wynik["pojemnosc"]["czynnosci_dzienne_minuty"], 0.0)
        self.assertEqual(
            wynik["pojemnosc"]["pojemnosc_na_sprawy_minuty"],
            wynik["pojemnosc"]["pojemnosc_brutto_minuty"],
        )

    def test_zerowe_czasy_nominalne_i_zero_opoznienia(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 50},
            {
                "miesiace_do_ugody": 0,
                "miesiace_do_wyroku_i": 0,
                "miesiace_wyrok_i_do_ii": 0,
                "opoznienie_platnosci_miesiace": 0,
                "horyzont_miesiace": 12,
            },
        )
        self.assertGreater(wynik["tabela_miesieczna"][0]["Przychód razem"], 0.0)

    def test_skrajne_udzialy_ugod_i_ii_instancji(self):
        same_ugody = oblicz_model_czasowy(
            {
                **self.parametry,
                "liczba_pracownikow": 10,
                "kategoryczna_odmowa_percent": 0.0,
                "automatyczne_ramy_percent": 100.0,
                "udzial_ii_instancji_percent": 100.0,
            }
        )
        bez_ugod_i_ii = oblicz_model_czasowy(
            {
                **self.parametry,
                "liczba_pracownikow": 10,
                "automatyczne_ramy_percent": 0.0,
                "zawarte_ugody_percent": 0.0,
                "udzial_ii_instancji_percent": 0.0,
            }
        )
        bez_ugod_same_ii = oblicz_model_czasowy(
            {
                **self.parametry,
                "liczba_pracownikow": 10,
                "automatyczne_ramy_percent": 0.0,
                "zawarte_ugody_percent": 0.0,
                "udzial_ii_instancji_percent": 100.0,
            }
        )
        self.assertEqual(
            sum(w["Zakończenia po II instancji"] for w in same_ugody["tabela_miesieczna"]),
            0.0,
        )
        self.assertEqual(
            sum(w["Ugody zakończone"] for w in bez_ugod_i_ii["tabela_miesieczna"]),
            0.0,
        )
        self.assertEqual(
            sum(w["Zakończenia po II instancji"] for w in bez_ugod_i_ii["tabela_miesieczna"]),
            0.0,
        )
        self.assertGreater(
            sum(
                w["Zakończenia po II instancji"]
                for w in bez_ugod_same_ii["tabela_miesieczna"]
            ),
            0.0,
        )

    def test_stawka_podatku_nie_zmienia_modelu_czasowego(self):
        bez = oblicz_model_czasowy(
            {**self.parametry, "podatek_dochodowy_percent": 0.0}
        )
        z = oblicz_model_czasowy(
            {**self.parametry, "podatek_dochodowy_percent": 37.0}
        )
        self.assertEqual(bez["tabela_miesieczna"], z["tabela_miesieczna"])

    def test_nieprawidlowe_parametry_sa_odrzucane(self):
        with self.assertRaises(ValueError):
            oblicz_model_czasowy(self.parametry, {"miesiace_do_ugody": -1})
        with self.assertRaises(ValueError):
            oblicz_model_czasowy(self.parametry, {"horyzont_miesiace": 0})


if __name__ == "__main__":
    unittest.main()
