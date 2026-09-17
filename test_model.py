import unittest

from model import (
    MINUTY_DNIA_PRACY,
    alokuj_liczby_z_procentow,
    domyslne_parametry,
    oblicz_czas_czynnosci_dziennych,
    oblicz_czynnosci_dzienne_lifecycle,
    oblicz_czasy_sciezek_ugod,
    oblicz_czasy_sciezek_z_ii_instancja,
    oblicz_model,
    oblicz_podatek_dochodowy,
    oblicz_podzial_spraw,
    oblicz_prog_czasu,
    oblicz_prog_kosztu_stalego,
    oblicz_prog_wynagrodzenia_pracownika,
    oblicz_sredni_czas_sciezki_ugody,
    oblicz_udzialy_ugod,
    oblicz_wynagrodzenie,
    oblicz_wskazniki_ii_instancji,
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
        udzialy = oblicz_udzialy_ugod(15, 30, 50, 50)
        self.assertEqual(udzialy["kategoryczna_odmowa"], 15.0)
        self.assertEqual(udzialy["automatyczne_ramy"], 30.0)
        self.assertEqual(udzialy["pozostale_sprawy"], 55.0)
        self.assertEqual(udzialy["szansa_poza_ramami"], 27.5)
        self.assertEqual(udzialy["zawarte_poza_ramami"], 13.75)
        self.assertEqual(udzialy["brak_ugody_poza_ramami"], 13.75)
        self.assertEqual(udzialy["brak_szans"], 27.5)
        self.assertEqual(udzialy["zakonczone_ugoda"], 43.75)
        self.assertEqual(udzialy["bez_ugody"], 56.25)
        self.assertAlmostEqual(
            sum(udzialy[nazwa] for nazwa in (
                "kategoryczna_odmowa", "automatyczne_ramy",
                "brak_szans", "zawarte_poza_ramami",
                "brak_ugody_poza_ramami",
            )),
            100.0,
        )

    def test_przyklad_podzialu_i_wskaznik_ugod(self):
        udzialy = oblicz_udzialy_ugod(15, 30, 50, 60)
        self.assertEqual(udzialy["zawarte_poza_ramami"], 16.5)
        self.assertEqual(udzialy["brak_ugody_poza_ramami"], 11.0)
        self.assertEqual(udzialy["zakonczone_ugoda"], 46.5)
        self.assertEqual(udzialy["bez_ugody"], 53.5)

    def test_nieprawidlowe_udzialy_sa_odrzucane(self):
        with self.assertRaises(ValueError):
            oblicz_udzialy_ugod(60, 50, 50)
        with self.assertRaises(ValueError):
            oblicz_udzialy_ugod(15, 30, 101)
        with self.assertRaises(ValueError):
            oblicz_udzialy_ugod(15, 30, 50, 101)

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
            "brak_szans": 310,
            "zawarte_poza_ramami": 115,
            "brak_ugody_poza_ramami": 345,
        })
        udzialy = oblicz_udzialy_ugod(15, 30, 50, 50)
        self.assertAlmostEqual(oblicz_sredni_czas_sciezki_ugody(udzialy, czasy), 216.0)

    def test_brak_ugody_pomija_podpis_i_obejmuje_proces(self):
        ugodowe = self.parametry["ugodowe_czynnosci"].copy()
        ugodowe["Podpisanie ugody"] = 999
        bez_podpisu = oblicz_czasy_sciezek_ugod(
            self.parametry["wspolne_czynnosci"],
            self.parametry["procesowe_czynnosci"],
            ugodowe,
            self.parametry["analiza_mozliwosci_ugody"],
        )["brak_ugody_poza_ramami"]
        self.assertEqual(bez_podpisu, 345)

        procesowe = self.parametry["procesowe_czynnosci"].copy()
        procesowe["Duplika"] += 10
        z_dodatkowym_procesem = oblicz_czasy_sciezek_ugod(
            self.parametry["wspolne_czynnosci"],
            procesowe,
            self.parametry["ugodowe_czynnosci"],
            self.parametry["analiza_mozliwosci_ugody"],
        )["brak_ugody_poza_ramami"]
        self.assertEqual(z_dodatkowym_procesem, 355)


class TestDrugaInstancja(unittest.TestCase):
    def setUp(self):
        self.parametry = domyslne_parametry()
        self.wyniki = oblicz_model(self.parametry)

    def test_domyslne_udzialy_liczba_i_czas_portfela(self):
        self.assertAlmostEqual(self.wyniki["udzialy_ugod"]["bez_ugody"], 56.25)
        self.assertAlmostEqual(self.wyniki["udzial_ii_instancji_w_portfelu"], 11.25)
        self.assertAlmostEqual(self.wyniki["oczekiwana_liczba_spraw_ii_instancji"], 67.5)
        self.assertAlmostEqual(self.wyniki["ii_instancja_minuty_na_sprawe_portfela"], 23.625)
        self.assertAlmostEqual(self.wyniki["ii_instancja_minuty_lacznie"], 14_175)
        self.assertAlmostEqual(self.wyniki["ii_instancja_godziny_lacznie"], 236.25)

    def test_ii_instancja_dotyczy_tylko_sciezek_bez_ugody(self):
        podstawowe = self.wyniki["czasy_sciezek_ugod"]
        laczne = self.wyniki["czasy_sciezek_z_ii_instancja"]
        dodatkowe = self.wyniki["czasy_ii_instancji_sciezek"]
        for sciezka in ("kategoryczna_odmowa", "brak_szans", "brak_ugody_poza_ramami"):
            self.assertEqual(dodatkowe[sciezka], 42.0)
            self.assertEqual(laczne[sciezka], podstawowe[sciezka] + 42.0)
        for sciezka in ("automatyczne_ramy", "zawarte_poza_ramami"):
            self.assertEqual(dodatkowe[sciezka], 0.0)
            self.assertEqual(laczne[sciezka], podstawowe[sciezka])
        self.assertEqual(laczne, {
            "kategoryczna_odmowa": 322.0,
            "automatyczne_ramy": 85.0,
            "brak_szans": 352.0,
            "zawarte_poza_ramami": 115.0,
            "brak_ugody_poza_ramami": 387.0,
        })

    def test_ii_instancja_jest_dodatkowa_do_p_i_niezalezna_od_wps(self):
        for grupa in self.wyniki["grupy"]:
            oczekiwane = (
                self.wyniki["srednie_minuty_sciezki_ugody"]
                + self.parametry["dodatkowe_minuty"][grupa["rodzaj"]]
            )
            self.assertAlmostEqual(grupa["laczne_minuty"], oczekiwane)
        for rodzaj in ("P1", "P2", "P3"):
            czasy = {
                grupa["laczne_minuty"]
                for grupa in self.wyniki["grupy"]
                if grupa["rodzaj"] == rodzaj
            }
            self.assertEqual(len(czasy), 1)

    def test_przychod_nie_zalezy_od_ii_instancji(self):
        warianty = []
        for udzial in (0.0, 20.0, 100.0):
            parametry = {**self.parametry, "udzial_ii_instancji_percent": udzial}
            warianty.append(oblicz_model(parametry))
        self.assertEqual(len({wynik["ogolem"]["przychod"] for wynik in warianty}), 1)
        self.assertLess(warianty[0]["ogolem"]["koszt"], warianty[1]["ogolem"]["koszt"])
        self.assertLess(warianty[1]["ogolem"]["koszt"], warianty[2]["ogolem"]["koszt"])
        self.assertLess(warianty[0]["bezposrednie_minuty_spraw"], warianty[2]["bezposrednie_minuty_spraw"])
        self.assertLess(
            warianty[0]["pojemnosc"]["bezposrednie_minuty_spraw"],
            warianty[2]["pojemnosc"]["bezposrednie_minuty_spraw"],
        )

    def test_czas_ii_instancji_zmienia_koszt_i_pojemnosc_bez_zmiany_przychodu(self):
        bez_czasu = oblicz_model({**self.parametry, "obsluga_ii_instancji_minuty": 0})
        dlugi_czas = oblicz_model({**self.parametry, "obsluga_ii_instancji_minuty": 360})
        self.assertEqual(bez_czasu["ogolem"]["przychod"], dlugi_czas["ogolem"]["przychod"])
        self.assertGreater(dlugi_czas["ogolem"]["koszt"], bez_czasu["ogolem"]["koszt"])
        self.assertLess(dlugi_czas["ogolem"]["wynik"], bez_czasu["ogolem"]["wynik"])
        self.assertLess(dlugi_czas["ogolem"]["marza"], bez_czasu["ogolem"]["marza"])
        self.assertGreater(dlugi_czas["bezposrednie_minuty_spraw"], bez_czasu["bezposrednie_minuty_spraw"])

    def test_koszt_ii_instancji_uzgadnia_sie_z_grupami_i_portfelem(self):
        bez_ii = oblicz_model({**self.parametry, "udzial_ii_instancji_percent": 0.0})
        roznica_minut = self.wyniki["bezposrednie_minuty_spraw"] - bez_ii["bezposrednie_minuty_spraw"]
        roznica_kosztu = self.wyniki["ogolem"]["koszt"] - bez_ii["ogolem"]["koszt"]
        self.assertAlmostEqual(roznica_minut, self.wyniki["ii_instancja_minuty_lacznie"])
        self.assertGreater(roznica_kosztu, roznica_minut / 60 * self.wyniki["koszt_godziny"])
        self.assertAlmostEqual(
            sum(grupa["laczny_koszt"] for grupa in self.wyniki["grupy"]),
            self.wyniki["ogolem"]["koszt"],
        )

    def test_przypadki_brzezne(self):
        zero_udzialu = oblicz_model({**self.parametry, "udzial_ii_instancji_percent": 0.0})
        zero_czasu = oblicz_model({**self.parametry, "obsluga_ii_instancji_minuty": 0})
        zero_spraw = oblicz_model({**self.parametry, "liczba_spraw": 0})
        wszystkie_ugodzone = oblicz_model({
            **self.parametry,
            "kategoryczna_odmowa_percent": 0.0,
            "automatyczne_ramy_percent": 100.0,
        })
        for wynik in (zero_udzialu, zero_czasu, zero_spraw, wszystkie_ugodzone):
            self.assertEqual(wynik["ii_instancja_minuty_lacznie"], 0.0)
        self.assertEqual(wszystkie_ugodzone["oczekiwana_liczba_spraw_ii_instancji"], 0.0)

    def test_walidacja_parametrow_ii_instancji(self):
        podstawowe = self.wyniki["czasy_sciezek_ugod"]
        with self.assertRaises(ValueError):
            oblicz_czasy_sciezek_z_ii_instancja(podstawowe, 101, 180)
        with self.assertRaises(ValueError):
            oblicz_wskazniki_ii_instancji(600, self.wyniki["udzialy_ugod"], 20, -1)


class TestCzasDziennyIPojemnosc(unittest.TestCase):
    def test_wzor_lifecycle_dla_1600_godzin(self):
        metryki = oblicz_czynnosci_dzienne_lifecycle(1_600 * 60, {"Dzienna": 90})
        self.assertAlmostEqual(metryki["ekwiwalent_osobodni_kohorty"], 1600 / 6.5)
        self.assertAlmostEqual(
            metryki["czynnosci_dzienne_lifecycle_minuty"], 1600 / 6.5 * 90
        )
        self.assertAlmostEqual(
            metryki["czynnosci_dzienne_lifecycle_godziny"], 369.2307692307692
        )
        self.assertAlmostEqual(
            1_600 + metryki["czynnosci_dzienne_lifecycle_godziny"],
            1_969.2307692307693,
        )
        self.assertEqual(metryki["produktywne_minuty_na_osobodzien"], 390)

    def test_lifecycle_nie_ma_rocznego_limitu_i_zachowuje_ulamki(self):
        ponad_rok = oblicz_czynnosci_dzienne_lifecycle(3_200 * 60, {"Dzienna": 90})
        ulamkowe = oblicz_czynnosci_dzienne_lifecycle(1_604 * 60, {"Dzienna": 90})
        self.assertAlmostEqual(ponad_rok["ekwiwalent_osobodni_kohorty"], 3200 / 6.5)
        self.assertAlmostEqual(
            ponad_rok["czynnosci_dzienne_lifecycle_godziny"], 3200 / 6.5 * 1.5
        )
        self.assertAlmostEqual(ulamkowe["ekwiwalent_osobodni_kohorty"], 1604 / 6.5)

    def test_ekonomia_kohorty_nie_zalezy_od_obsady_ani_dni_pracy(self):
        porownywane = [
            oblicz_model({
                **domyslne_parametry(),
                "liczba_pracownikow": pracownicy,
                "liczba_dni_pracy_w_roku": dni,
            })
            for pracownicy, dni in ((1, 150), (2, 251), (4, 350))
        ]
        for klucz in (
            "przychod", "koszt", "wynik", "marza",
        ):
            self.assertTrue(all(
                wynik["ogolem"][klucz] == porownywane[0]["ogolem"][klucz]
                for wynik in porownywane
            ))
        for klucz in (
            "bezposrednie_minuty_spraw",
            "ekwiwalent_osobodni_kohorty",
            "czynnosci_dzienne_lifecycle_minuty",
        ):
            self.assertTrue(all(wynik[klucz] == porownywane[0][klucz] for wynik in porownywane))
        self.assertNotEqual(
            porownywane[0]["pojemnosc"]["pojemnosc_brutto_minuty"],
            porownywane[-1]["pojemnosc"]["pojemnosc_brutto_minuty"],
        )

    def test_zmiana_czynnosci_dziennej_ma_dokladny_koszt_lifecycle(self):
        parametry = domyslne_parametry()
        bazowy = oblicz_model(parametry)
        zmienione = {
            **parametry,
            "codzienne_czynnosci": {
                **parametry["codzienne_czynnosci"],
                "Obsługa skrzynki ugody EH": 40,
            },
        }
        po_zmianie = oblicz_model(zmienione)
        bezposrednie = bazowy["bezposrednie_minuty_spraw"]
        oczekiwane_minuty = bezposrednie * 100 / 380 - bezposrednie * 90 / 390
        self.assertAlmostEqual(
            po_zmianie["czynnosci_dzienne_lifecycle_minuty"]
            - bazowy["czynnosci_dzienne_lifecycle_minuty"],
            oczekiwane_minuty,
        )
        self.assertAlmostEqual(
            po_zmianie["ogolem"]["koszt"] - bazowy["ogolem"]["koszt"],
            oczekiwane_minuty / 60 * bazowy["koszt_godziny"],
        )

    def test_skrocenie_czasu_bezposredniego_oszczedza_tez_narzut_lifecycle(self):
        parametry = domyslne_parametry()
        bazowy = oblicz_model(parametry)
        zmienione = {
            **parametry,
            "procesowe_czynnosci": {
                **parametry["procesowe_czynnosci"], "Duplika": 80,
            },
        }
        po_zmianie = oblicz_model(zmienione)
        self.assertLess(po_zmianie["bezposrednie_minuty_spraw"], bazowy["bezposrednie_minuty_spraw"])
        self.assertLess(po_zmianie["ekwiwalent_osobodni_kohorty"], bazowy["ekwiwalent_osobodni_kohorty"])
        self.assertLess(
            po_zmianie["czynnosci_dzienne_lifecycle_minuty"],
            bazowy["czynnosci_dzienne_lifecycle_minuty"],
        )
        self.assertGreater(
            bazowy["ogolem"]["koszt"] - po_zmianie["ogolem"]["koszt"],
            (bazowy["bezposrednie_minuty_spraw"] - po_zmianie["bezposrednie_minuty_spraw"])
            / 60 * bazowy["koszt_godziny"],
        )

    def test_domyslna_pojemnosc_wynika_z_aktualnych_parametrow(self):
        parametry = domyslne_parametry()
        wynik = oblicz_model(parametry)
        dzienne_na_pracownika = sum(parametry["codzienne_czynnosci"].values())
        oczekiwana_pojemnosc = (
            parametry["liczba_pracownikow"]
            * parametry["liczba_dni_pracy_w_roku"]
            * (MINUTY_DNIA_PRACY - dzienne_na_pracownika)
        )
        self.assertEqual(wynik["pojemnosc"]["pojemnosc_spraw_minuty"], oczekiwana_pojemnosc)
        self.assertEqual(
            wynik["pojemnosc"]["przekroczona"],
            wynik["bezposrednie_minuty_spraw"] > oczekiwana_pojemnosc,
        )

    def test_pojemnosc_roczna_reaguje_na_obsade_dni_i_czynnosci_dzienne(self):
        parametry = domyslne_parametry()
        bazowy = oblicz_model(parametry)["pojemnosc"]
        wiecej_pracownikow = oblicz_model({
            **parametry, "liczba_pracownikow": 3,
        })["pojemnosc"]
        mniej_dni = oblicz_model({
            **parametry, "liczba_dni_pracy_w_roku": 200,
        })["pojemnosc"]
        dluzsze_czynnosci = oblicz_model({
            **parametry,
            "codzienne_czynnosci": {
                **parametry["codzienne_czynnosci"], "Obsługa skrzynki ugody EH": 40,
            },
        })["pojemnosc"]
        self.assertGreater(
            wiecej_pracownikow["pojemnosc_spraw_minuty"], bazowy["pojemnosc_spraw_minuty"]
        )
        self.assertLess(
            mniej_dni["pojemnosc_spraw_minuty"], bazowy["pojemnosc_spraw_minuty"]
        )
        self.assertLess(
            dluzsze_czynnosci["pojemnosc_spraw_minuty"], bazowy["pojemnosc_spraw_minuty"]
        )

    def test_domyslny_i_piecioosobowy_narzut(self):
        czynnosci = domyslne_parametry()["codzienne_czynnosci"]
        self.assertEqual(oblicz_czas_czynnosci_dziennych(1, 250, czynnosci), 22_500)
        self.assertEqual(oblicz_czas_czynnosci_dziennych(5, 250, czynnosci), 112_500)

    def test_narzut_lifecycle_skaluje_sie_z_liczba_spraw(self):
        parametry_600 = domyslne_parametry()
        parametry_1000 = {**domyslne_parametry(), "liczba_spraw": 1000}
        wynik_600 = oblicz_model(parametry_600)
        wynik_1000 = oblicz_model(parametry_1000)
        self.assertLess(
            wynik_600["czynnosci_dzienne_lifecycle_minuty"],
            wynik_1000["czynnosci_dzienne_lifecycle_minuty"],
        )

    def test_pracownicy_nie_mnoza_czasu_spraw(self):
        domyslny = oblicz_model(domyslne_parametry())
        pieciu = oblicz_model({**domyslne_parametry(), "liczba_pracownikow": 5})
        self.assertEqual(domyslny["bezposrednie_minuty_spraw"], pieciu["bezposrednie_minuty_spraw"])
        self.assertEqual(
            domyslny["czynnosci_dzienne_lifecycle_minuty"],
            pieciu["czynnosci_dzienne_lifecycle_minuty"],
        )
        self.assertGreater(
            pieciu["pojemnosc"]["pojemnosc_spraw_minuty"],
            domyslny["pojemnosc"]["pojemnosc_spraw_minuty"],
        )

    def test_brak_czasu_na_sprawy_jest_wykrywany(self):
        parametry = domyslne_parametry()
        parametry["codzienne_czynnosci"] = {"Czynności dzienne": MINUTY_DNIA_PRACY}
        with self.assertRaisesRegex(ValueError, "zużywają cały dzień pracy"):
            oblicz_model(parametry)

    def test_lifecycle_i_pojemnosc_uzywaja_tego_samego_dnia_480_minut(self):
        parametry = domyslne_parametry()
        wynik = oblicz_model(parametry)
        dzienne = sum(parametry["codzienne_czynnosci"].values())
        oczekiwane_minuty_zasobu = (
            wynik["bezposrednie_minuty_spraw"]
            * MINUTY_DNIA_PRACY
            / (MINUTY_DNIA_PRACY - dzienne)
        )
        self.assertAlmostEqual(wynik["laczne_minuty"], oczekiwane_minuty_zasobu)
        pelne_osobodni = (
            wynik["bezposrednie_minuty_spraw"]
            / (MINUTY_DNIA_PRACY - dzienne)
        )
        self.assertAlmostEqual(
            pelne_osobodni * MINUTY_DNIA_PRACY,
            wynik["laczne_minuty"],
        )


class TestModelFinansowy(unittest.TestCase):
    def test_wynagrodzenie_ugoda_i_wyrok_dla_niskiego_i_wysokiego_wps(self):
        self.assertEqual(oblicz_wynagrodzenie(2_500, 10_000, 70), 400)
        self.assertEqual(oblicz_wynagrodzenie(2_500, 10_000, 95), 275)
        self.assertEqual(oblicz_wynagrodzenie(25_000, 10_000, 70), 1_100)
        self.assertEqual(oblicz_wynagrodzenie(25_000, 10_000, 95), 600)

    def test_limity_czesci_zmiennej_sa_stosowane_osobno(self):
        self.assertEqual(oblicz_wynagrodzenie(20_000, 30_000, 0), 2_250)
        self.assertEqual(oblicz_wynagrodzenie(100_000, 10_000, 0), 5_500)

    def test_domyslny_model_korzysta_z_nowego_czasu(self):
        wynik = oblicz_model()
        oczekiwany = sum(
            grupa["liczba"]
            * (
                wynik["udzialy_ugod"]["zakonczone_ugoda"] / 100
                * grupa["wynagrodzenie_ugoda"]
                + wynik["udzialy_ugod"]["bez_ugody"] / 100
                * grupa["wynagrodzenie_wyrok"]
            )
            for grupa in wynik["grupy"]
        )
        self.assertAlmostEqual(wynik["ogolem"]["przychod"], oczekiwany)
        self.assertAlmostEqual(wynik["srednie_minuty_podstawowej_sciezki_ugody"], 216.0)
        self.assertAlmostEqual(wynik["srednie_minuty_sciezki_ugody"], 239.625)
        self.assertAlmostEqual(wynik["bezposrednie_minuty_spraw"], 233_955)
        self.assertAlmostEqual(wynik["czynnosci_dzienne_lifecycle_minuty"], 53_989.61538461538)
        self.assertAlmostEqual(wynik["ogolem"]["koszt"], 460_135.49538461544)

    def test_przychod_wedlug_zakonczenia_i_grup_uzgadnia_sie(self):
        wynik = oblicz_model()
        self.assertAlmostEqual(
            wynik["ogolem"]["przychod_ugody"] + wynik["ogolem"]["przychod_wyroki"],
            wynik["ogolem"]["przychod"],
        )
        self.assertAlmostEqual(
            sum(dane["przychod"] for dane in wynik["rodzaje"].values()),
            wynik["ogolem"]["przychod"],
        )
        self.assertAlmostEqual(
            wynik["wps_niski"]["przychod"] + wynik["wps_wysoki"]["przychod"],
            wynik["ogolem"]["przychod"],
        )

    def test_skrajne_udzialy_ugod_izoluja_wlasciwy_parametr(self):
        bazowe = domyslne_parametry()
        same_ugody = {**bazowe, "kategoryczna_odmowa_percent": 0.0, "automatyczne_ramy_percent": 100.0}
        przychod_ugod = oblicz_model(same_ugody)["ogolem"]["przychod"]
        self.assertEqual(
            oblicz_model({**same_ugody, "srednia_kwota_wyroku_percent": 0.0})["ogolem"]["przychod"],
            przychod_ugod,
        )
        bez_ugod = {**bazowe, "automatyczne_ramy_percent": 0.0, "zawarte_ugody_percent": 0.0}
        przychod_wyrokow = oblicz_model(bez_ugod)["ogolem"]["przychod"]
        self.assertEqual(
            oblicz_model({**bez_ugod, "srednia_kwota_ugody_percent": 0.0})["ogolem"]["przychod"],
            przychod_wyrokow,
        )

    def test_parametry_kwot_zmieniaja_tylko_wlasny_skladnik_przychodu(self):
        parametry = domyslne_parametry()
        bazowy = oblicz_model(parametry)["ogolem"]
        inna_ugoda = oblicz_model({
            **parametry, "srednia_kwota_ugody_percent": 60.0,
        })["ogolem"]
        inny_wyrok = oblicz_model({
            **parametry, "srednia_kwota_wyroku_percent": 85.0,
        })["ogolem"]
        self.assertNotEqual(inna_ugoda["przychod_ugody"], bazowy["przychod_ugody"])
        self.assertEqual(inna_ugoda["przychod_wyroki"], bazowy["przychod_wyroki"])
        self.assertEqual(inny_wyrok["przychod_ugody"], bazowy["przychod_ugody"])
        self.assertNotEqual(inny_wyrok["przychod_wyroki"], bazowy["przychod_wyroki"])

    def test_wzrost_skutecznosci_ugod_zmienia_przychod_i_koszt(self):
        parametry = domyslne_parametry()
        nizsza = oblicz_model({**parametry, "zawarte_ugody_percent": 40.0})
        wyzsza = oblicz_model({**parametry, "zawarte_ugody_percent": 60.0})
        zmiana_udzialu = (
            wyzsza["udzialy_ugod"]["zakonczone_ugoda"]
            - nizsza["udzialy_ugod"]["zakonczone_ugoda"]
        ) / 100
        oczekiwana_zmiana_przychodu = sum(
            grupa["liczba"]
            * zmiana_udzialu
            * (grupa["wynagrodzenie_ugoda"] - grupa["wynagrodzenie_wyrok"])
            for grupa in nizsza["grupy"]
        )
        self.assertAlmostEqual(
            wyzsza["ogolem"]["przychod"] - nizsza["ogolem"]["przychod"],
            oczekiwana_zmiana_przychodu,
        )
        self.assertLess(wyzsza["bezposrednie_minuty_spraw"], nizsza["bezposrednie_minuty_spraw"])
        self.assertLess(wyzsza["ogolem"]["koszt"], nizsza["ogolem"]["koszt"])

    def test_rowne_kwoty_koncowe_uniezalezniaja_przychod_od_ugod(self):
        parametry = {
            **domyslne_parametry(),
            "srednia_kwota_ugody_percent": 80.0,
            "srednia_kwota_wyroku_percent": 80.0,
        }
        przychody = {
            oblicz_model({**parametry, "zawarte_ugody_percent": skutecznosc})["ogolem"]["przychod"]
            for skutecznosc in (0.0, 50.0, 100.0)
        }
        self.assertEqual(len(przychody), 1)

    def test_podatek_od_zysku_i_brak_podatku_od_straty(self):
        zero = oblicz_podatek_dochodowy(500_000, 400_000, 0)
        podatek = oblicz_podatek_dochodowy(500_000, 400_000, 19)
        strata = oblicz_podatek_dochodowy(400_000, 500_000, 19)
        self.assertEqual((zero["wynik_przed_podatkiem"], zero["podatek_dochodowy"], zero["wynik_po_podatku"]), (100_000, 0, 100_000))
        self.assertEqual((podatek["wynik_przed_podatkiem"], podatek["podatek_dochodowy"], podatek["wynik_po_podatku"]), (100_000, 19_000, 81_000))
        self.assertEqual((strata["wynik_przed_podatkiem"], strata["podatek_dochodowy"], strata["wynik_po_podatku"]), (-100_000, 0, -100_000))

    def test_stawka_podatku_nie_zmienia_ekonomii_operacyjnej(self):
        bez = oblicz_model({**domyslne_parametry(), "podatek_dochodowy_percent": 0.0, "srednia_kwota_ugody_percent": 20.0, "srednia_kwota_wyroku_percent": 20.0})
        z = oblicz_model({**domyslne_parametry(), "podatek_dochodowy_percent": 19.0, "srednia_kwota_ugody_percent": 20.0, "srednia_kwota_wyroku_percent": 20.0})
        for klucz in ("przychod", "koszt", "wynik_przed_podatkiem"):
            self.assertEqual(bez["ogolem"][klucz], z["ogolem"][klucz])
        for klucz in ("bezposrednie_minuty_spraw", "czynnosci_dzienne_lifecycle_minuty"):
            self.assertEqual(bez[klucz], z[klucz])
        self.assertAlmostEqual(z["ogolem"]["podatek_dochodowy"], z["ogolem"]["wynik_przed_podatkiem"] * 0.19)

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
        self.assertEqual(wynik["czynnosci_dzienne_lifecycle_minuty"], 0.0)
        self.assertEqual(wynik["ogolem"]["koszt"], 0.0)


class TestProgiRentownosci(unittest.TestCase):
    def test_prog_czasu_przelicza_czynnosci_dzienne_lifecycle(self):
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
            "obsluga_ii_instancji_minuty": parametry["obsluga_ii_instancji_minuty"] * skala,
            "dodatkowe_minuty": {k: v * skala for k, v in parametry["dodatkowe_minuty"].items()},
        }
        wynik_przed = oblicz_model(parametry)
        wynik_po = oblicz_model(zmienione)
        self.assertLess(
            wynik_po["czynnosci_dzienne_lifecycle_minuty"],
            wynik_przed["czynnosci_dzienne_lifecycle_minuty"],
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

    def test_obsada_nie_wplywa_na_prog_czasu(self):
        parametry = {**domyslne_parametry(), "liczba_pracownikow": 100}
        self.assertEqual(
            oblicz_prog_czasu(parametry)["mozliwe"],
            oblicz_prog_czasu(domyslne_parametry())["mozliwe"],
        )

    def test_niemozliwe_progi_sa_oznaczone(self):
        parametry = {
            **domyslne_parametry(),
            "koszt_staly_na_godzine": 500.0,
            "wynagrodzenie_pracownika_na_godzine": 500.0,
        }
        self.assertFalse(oblicz_prog_kosztu_stalego(parametry)["mozliwe"])
        self.assertFalse(oblicz_prog_wynagrodzenia_pracownika(parametry)["mozliwe"])


if __name__ == "__main__":
    unittest.main()
