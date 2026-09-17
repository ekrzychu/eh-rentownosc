import unittest

from model import domyslne_parametry, oblicz_model
from timeline import (
    domyslne_parametry_czasowe,
    oblicz_model_czasowy,
    rozloz_naplyw,
    wyznacz_break_even,
)


class TestUzgodnienieModeluCzasowego(unittest.TestCase):
    def setUp(self):
        self.parametry = domyslne_parametry()
        self.lifecycle = oblicz_model(self.parametry)
        self.czasowy = oblicz_model_czasowy(self.parametry)
        self.pelna = self.czasowy["pelna_tabela_miesieczna"]

    def suma(self, klucz):
        return sum(wiersz[klucz] for wiersz in self.pelna)

    def test_przychod_uzgadnia_sie_z_lifecycle_i_przekrojami(self):
        self.assertAlmostEqual(
            self.suma("Przychód razem"), self.lifecycle["ogolem"]["przychod"]
        )
        self.assertAlmostEqual(
            self.suma("Przychód z ugód"), self.lifecycle["ogolem"]["przychod_ugody"]
        )
        self.assertAlmostEqual(
            self.suma("Przychód z wyroków"), self.lifecycle["ogolem"]["przychod_wyroki"]
        )
        for rodzaj, dane in self.lifecycle["rodzaje"].items():
            self.assertAlmostEqual(
                self.czasowy["uzgodnienie"]["przychod_wedlug_rodzaju"][rodzaj],
                dane["przychod"],
            )
        for grupa, klucz in (("niski_wps", "wps_niski"), ("wysoki_wps", "wps_wysoki")):
            self.assertAlmostEqual(
                self.czasowy["uzgodnienie"]["przychod_wedlug_wps"][grupa],
                self.lifecycle[klucz]["przychod"],
            )

    def test_bezposredni_czas_uzgadnia_sie_z_lifecycle(self):
        self.assertAlmostEqual(
            self.suma("Bezpośrednie minuty pracy"),
            self.lifecycle["bezposrednie_minuty_spraw"],
        )

    def test_czynnosci_dzienne_uzgadniaja_sie_z_lifecycle(self):
        self.assertAlmostEqual(
            self.suma("Minuty czynności dziennych"),
            self.lifecycle["czynnosci_dzienne_lifecycle_minuty"],
        )

    def test_koszt_uzgadnia_sie_z_lifecycle(self):
        self.assertAlmostEqual(self.suma("Koszt"), self.lifecycle["ogolem"]["koszt"])

    def test_liczby_wynikow_sumarycznie_daja_calosc_portfela(self):
        liczba_zakonczen = sum(
            self.suma(klucz)
            for klucz in (
                "Ugody",
                "Zakończenia po I instancji",
                "Zakończenia po II instancji",
            )
        )
        self.assertAlmostEqual(liczba_zakonczen, self.parametry["liczba_spraw"])

    def test_jawny_podzial_ii_instancji(self):
        nieugodzone = (
            self.parametry["liczba_spraw"]
            * self.lifecycle["udzialy_ugod"]["bez_ugody"]
            / 100
        )
        oczekiwane_ii = nieugodzone * self.parametry["udzial_ii_instancji_percent"] / 100
        self.assertAlmostEqual(
            self.suma("Zakończenia po II instancji"), oczekiwane_ii
        )


class TestRozkladWCzasie(unittest.TestCase):
    def setUp(self):
        self.parametry = domyslne_parametry()

    def test_zmiana_czasu_ii_nie_dodaje_przychodu(self):
        krotko = oblicz_model_czasowy(
            self.parametry, {"miesiace_wyrok_i_do_ii": 0}
        )
        dlugo = oblicz_model_czasowy(
            self.parametry, {"miesiace_wyrok_i_do_ii": 18}
        )
        self.assertAlmostEqual(
            krotko["podsumowanie"]["przychod_pelny"],
            dlugo["podsumowanie"]["przychod_pelny"],
        )
        self.assertAlmostEqual(
            krotko["podsumowanie"]["przychod_pelny"],
            oblicz_model(self.parametry)["ogolem"]["przychod"],
        )
        self.assertAlmostEqual(
            krotko["podsumowanie"]["koszt_pelny"],
            dlugo["podsumowanie"]["koszt_pelny"],
        )
        self.assertNotEqual(
            [w["Przychód z wyroków"] for w in krotko["pelna_tabela_miesieczna"]],
            [w["Przychód z wyroków"] for w in dlugo["pelna_tabela_miesieczna"]],
        )

    def test_opoznienie_przesuwa_tylko_przychod(self):
        bez = oblicz_model_czasowy(
            self.parametry, {"opoznienie_platnosci_miesiace": 0}
        )
        opozniony = oblicz_model_czasowy(
            self.parametry, {"opoznienie_platnosci_miesiace": 4}
        )
        przychod_bez = {
            w["Miesiąc"]: w["Przychód razem"]
            for w in bez["pelna_tabela_miesieczna"]
        }
        przychod_opozniony = {
            w["Miesiąc"]: w["Przychód razem"]
            for w in opozniony["pelna_tabela_miesieczna"]
        }
        for miesiac, wartosc in przychod_bez.items():
            self.assertAlmostEqual(przychod_opozniony.get(miesiac + 4, 0.0), wartosc)
        self.assertAlmostEqual(
            bez["podsumowanie"]["przychod_pelny"],
            opozniony["podsumowanie"]["przychod_pelny"],
        )
        self.assertAlmostEqual(
            bez["podsumowanie"]["koszt_pelny"],
            opozniony["podsumowanie"]["koszt_pelny"],
        )

    def test_wszystkie_sprawy_wplywaja_w_pierwszym_miesiacu(self):
        wynik = oblicz_model_czasowy(
            self.parametry, {"tryb_naplywu": "Wszystkie na początku"}
        )
        naplyw = [w["Nowe sprawy"] for w in wynik["tabela_miesieczna"]]
        self.assertEqual(naplyw[0], 600.0)
        self.assertTrue(all(wartosc == 0.0 for wartosc in naplyw[1:]))

    def test_rowny_naplyw_600_spraw_przez_12_miesiecy(self):
        naplyw = rozloz_naplyw(600, "równomiernie", 12)
        self.assertEqual(naplyw, [50.0] * 12)
        self.assertEqual(sum(naplyw), 600.0)

    def test_krotki_horyzont_nie_ucina_pelnego_uzgodnienia(self):
        wynik = oblicz_model_czasowy(self.parametry, {"horyzont_miesiace": 6})
        pelny_przychod = sum(
            w["Przychód razem"] for w in wynik["pelna_tabela_miesieczna"]
        )
        widoczny_przychod = sum(
            w["Przychód razem"] for w in wynik["tabela_miesieczna"]
        )
        pelny_koszt = sum(w["Koszt"] for w in wynik["pelna_tabela_miesieczna"])
        widoczny_koszt = sum(w["Koszt"] for w in wynik["tabela_miesieczna"])
        self.assertAlmostEqual(pelny_przychod, oblicz_model(self.parametry)["ogolem"]["przychod"])
        self.assertLess(wynik["kpi"]["udzial_przychodu_lifecycle_w_horyzoncie"], 100.0)
        self.assertAlmostEqual(
            wynik["podsumowanie"]["pozostaly_przychod"],
            pelny_przychod - widoczny_przychod,
        )
        self.assertAlmostEqual(
            wynik["podsumowanie"]["pozostaly_koszt"], pelny_koszt - widoczny_koszt
        )
        self.assertFalse(wynik["podsumowanie"]["pelny_cykl_w_horyzoncie"])

    def test_zero_spraw_daje_zerowe_przeplywy(self):
        wynik = oblicz_model_czasowy({**self.parametry, "liczba_spraw": 0})
        for wiersz in wynik["tabela_miesieczna"]:
            for klucz in (
                "Nowe sprawy",
                "Ugody",
                "Zakończenia po I instancji",
                "Zakończenia po II instancji",
                "Przychód razem",
                "Bezpośrednie godziny pracy",
                "Godziny czynności dziennych",
                "Koszt",
                "Wynik miesięczny",
                "Wynik skumulowany",
            ):
                self.assertEqual(wiersz[klucz], 0.0)
        self.assertEqual(wynik["kpi"]["break_even_skumulowany"], "Od początku")

    def test_zerowe_czasy_nie_gubia_pracy(self):
        wynik = oblicz_model_czasowy(
            self.parametry,
            {
                "tryb_naplywu": "wszystkie na początku",
                "miesiace_do_ugody": 0,
                "miesiace_do_wyroku_i": 0,
                "miesiace_wyrok_i_do_ii": 0,
            },
        )
        self.assertAlmostEqual(
            sum(w["Bezpośrednie minuty pracy"] for w in wynik["pelna_tabela_miesieczna"]),
            oblicz_model(self.parametry)["bezposrednie_minuty_spraw"],
        )
        self.assertAlmostEqual(
            sum(w["Koszt"] for w in wynik["pelna_tabela_miesieczna"]),
            oblicz_model(self.parametry)["ogolem"]["koszt"],
        )

    def test_obsada_i_podatek_nie_zmieniaja_ekonomii_czasowej(self):
        bazowy = oblicz_model_czasowy(self.parametry)
        zmieniony = oblicz_model_czasowy(
            {
                **self.parametry,
                "liczba_pracownikow": 25,
                "liczba_dni_pracy_w_roku": 100,
                "podatek_dochodowy_percent": 37.0,
            }
        )
        for klucz in ("przychod_pelny", "koszt_pelny"):
            self.assertAlmostEqual(
                bazowy["podsumowanie"][klucz], zmieniony["podsumowanie"][klucz]
            )
        self.assertEqual(bazowy["tabela_miesieczna"], zmieniony["tabela_miesieczna"])

    def test_nieudana_proba_ugody_jest_najpozniej_przy_wyroku_i_bez_podpisu(self):
        parametry = {
            **self.parametry,
            "kategoryczna_odmowa_percent": 0.0,
            "automatyczne_ramy_percent": 0.0,
            "szansa_na_ugode_percent": 100.0,
            "zawarte_ugody_percent": 0.0,
            "udzial_ii_instancji_percent": 0.0,
            "wspolne_czynnosci": {"Wspólna": 0.0},
            "procesowe_czynnosci": {"Proces": 0.0},
            "analiza_mozliwosci_ugody": 0.0,
            "ugodowe_czynnosci": {
                "Oferta ugody": 15.0,
                "Projekt ugody": 20.0,
                "Podpisanie ugody": 999.0,
            },
            "dodatkowe_minuty": {"P1": 0.0, "P2": 0.0, "P3": 0.0},
        }
        wynik = oblicz_model_czasowy(
            parametry,
            {
                "tryb_naplywu": "wszystkie na początku",
                "miesiace_do_ugody": 20,
                "miesiace_do_wyroku_i": 5,
            },
        )
        minuty = {
            w["Miesiąc"]: w["Bezpośrednie minuty pracy"]
            for w in wynik["pelna_tabela_miesieczna"]
        }
        self.assertAlmostEqual(minuty[5], 600 * (15 + 20))
        self.assertEqual(minuty.get(20, 0.0), 0.0)
        self.assertAlmostEqual(
            sum(minuty.values()), oblicz_model(parametry)["bezposrednie_minuty_spraw"]
        )

    def test_proces_jest_rozlozony_po_wplywie_do_wyroku_i(self):
        parametry = {
            **self.parametry,
            "kategoryczna_odmowa_percent": 100.0,
            "automatyczne_ramy_percent": 0.0,
            "udzial_ii_instancji_percent": 0.0,
            "wspolne_czynnosci": {"Wspólna": 0.0},
            "procesowe_czynnosci": {"Proces": 90.0},
            "ugodowe_czynnosci": {},
            "analiza_mozliwosci_ugody": 0.0,
            "dodatkowe_minuty": {"P1": 0.0, "P2": 0.0, "P3": 0.0},
        }
        wynik = oblicz_model_czasowy(
            parametry,
            {
                "tryb_naplywu": "wszystkie na początku",
                "miesiace_do_wyroku_i": 3,
            },
        )
        minuty = [w["Bezpośrednie minuty pracy"] for w in wynik["pelna_tabela_miesieczna"]]
        self.assertEqual(minuty[0], 0.0)
        for miesiac in (1, 2, 3):
            self.assertAlmostEqual(minuty[miesiac], 600 * 30.0)


class TestDefinicjaBreakEven(unittest.TestCase):
    def test_nigdy_ujemny_oznacza_od_poczatku(self):
        self.assertEqual(
            wyznacz_break_even([0.0, 10.0, 5.0])["etykieta"], "Od początku"
        )

    def test_powrot_z_deficytu_wskazuje_pierwszy_miesiac(self):
        wynik = wyznacz_break_even([-10.0, -2.0, 0.0, 5.0])
        self.assertEqual(wynik["miesiac"], 2)
        self.assertEqual(wynik["etykieta"], "Miesiąc 2")

    def test_brak_powrotu_w_horyzoncie(self):
        self.assertEqual(
            wyznacz_break_even([-10.0, -2.0, -1.0])["etykieta"],
            "Nie osiągnięto w horyzoncie",
        )


class TestParametryCzasowe(unittest.TestCase):
    def test_wartosci_domyslne(self):
        self.assertEqual(
            domyslne_parametry_czasowe(),
            {
                "tryb_naplywu": "równomiernie",
                "okres_naplywu_miesiace": 12,
                "miesiace_do_ugody": 6,
                "miesiace_do_wyroku_i": 9,
                "miesiace_wyrok_i_do_ii": 6,
                "opoznienie_platnosci_miesiace": 0,
                "horyzont_miesiace": 36,
            },
        )

    def test_ujemne_czasy_i_zerowy_horyzont_sa_odrzucane(self):
        with self.assertRaises(ValueError):
            oblicz_model_czasowy(domyslne_parametry(), {"miesiace_do_ugody": -1})
        with self.assertRaises(ValueError):
            oblicz_model_czasowy(domyslne_parametry(), {"horyzont_miesiace": 0})


if __name__ == "__main__":
    unittest.main()
