import unittest
from collections import defaultdict, deque
from unittest.mock import patch

import timeline
from staff import nowy_pracownik

from model import (
    MINUTY_DNIA_PRACY,
    domyslne_parametry,
    oblicz_model,
    oblicz_przeplyw,
)
from timeline import (
    GODZINY_ETATU_MIESIECZNIE,
    _nominalny_miesiac_dojrzalosci,
    domyslne_parametry_czasowe,
    klasyfikuj_status_kontraktu,
    oblicz_model_czasowy,
    oblicz_pojemnosc_miesieczna,
    porownaj_obsade,
    wyznacz_break_even,
    wyznacz_trwaly_break_even,
)

def osoba(rola, stawka=60.0, wykorzystanie=100.0):
    return {"rola": rola, "stawka": stawka, "wykorzystanie_percent": wykorzystanie}

def pierwszy_miesiac_z_wartoscia(wiersze, klucz):
    return next(w["Miesiąc"] for w in wiersze if w[klucz] > 1e-8)

def parametry_jednej_sciezki():
    """2,5 sprawy/mies., po 6000 minut w jednym etapie, 10020 minut/FTE."""
    return {
        **domyslne_parametry(),
        "liczba_spraw": 30,
        "pracownicy": [nowy_pracownik(i) for i in range(1)],
        "udzialy_rodzajow": {"P1": 100.0, "P2": 0.0, "P3": 0.0},
        "wysoki_wps_procent": 100.0,
        "kategoryczna_odmowa_percent": 0.0,
        "automatyczne_ramy_percent": 100.0,
        "skutecznosc_automatycznych_ram_percent": 100.0,
        "udzial_ii_instancji_percent": 0.0,
        "wspolne_czynnosci": {},
        "procesowe_czynnosci": {},
        "ugodowe_czynnosci": {"Oferta ugody": 6000},
        "dodatkowe_minuty": {"P1": 0, "P2": 0, "P3": 0},
        "codzienne_czynnosci": {},
    }

class TestNatychmiastowaPraca(unittest.TestCase):

    def test_oczekiwanie_nie_dodaje_pracy_ani_kosztu(self):
        p = {**domyslne_parametry(), "pracownicy": [nowy_pracownik(i) for i in range(10)], "udzial_ii_instancji_percent": 0.0}
        krotko = oblicz_model_czasowy(p, {"horyzont_miesiace": 72})
        dlugo = oblicz_model_czasowy(p, {"miesiace_do_ugody": 60, "miesiace_do_wyroku_i": 60, "horyzont_miesiace": 72})
        miesieczna_praca = oblicz_przeplyw(p)["bezposrednie_minuty_spraw"] / 12
        for a, b in zip(krotko["tabela_miesieczna"], dlugo["tabela_miesieczna"]):
            for key in ("Nowa praca (h)", "Wykonana praca (h)", "Backlog na koniec (h)", "Łączny koszt miesięczny"):
                self.assertAlmostEqual(a[key], b[key])
            self.assertAlmostEqual(b["Nowa praca (h)"] * 60, miesieczna_praca - (50 * .2875 * 250 if b["Miesiąc"] == 1 else 0))
        self.assertGreater(dlugo["tabela_miesieczna"][0]["Aktywne sprawy"], 0)
        self.assertEqual(dlugo["tabela_miesieczna"][0]["Przychód razem"], 0)

    def test_dojrzalosc_i_roczne_uzgodnienie_przy_dlugich_terminach(self):
        p = {**domyslne_parametry(), "pracownicy": [nowy_pracownik(i) for i in range(10)]}
        czas = {"miesiace_do_ugody": 60, "miesiace_do_wyroku_i": 20, "miesiace_wyrok_i_do_ii": 45}
        short = oblicz_model_czasowy(p, {**czas, "horyzont_miesiace": 78})
        self.assertFalse(short["podsumowanie"]["dojrzalosc_osiagnieta"])
        wynik = oblicz_model_czasowy(p, {**czas, "horyzont_miesiace": 79})
        self.assertEqual(wynik["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 68)
        self.assertTrue(wynik["podsumowanie"]["dojrzalosc_osiagnieta"])
        last = wynik["tabela_miesieczna"][-12:]
        self.assertAlmostEqual(sum(row[key] for row in last for key in ("Ugody zakończone", "Zakończenia po I instancji", "Zakończenia po II instancji")), 600)
        lifecycle = oblicz_przeplyw(p)
        self.assertAlmostEqual(sum(row["Nowa praca (h)"] * 60 for row in last), lifecycle["bezposrednie_minuty_spraw"])
        self.assertAlmostEqual(sum(row["Przychód razem"] for row in last), lifecycle["ogolem"]["przychod"])

class TestNiezaleznoscOdKolejnosci(unittest.TestCase):
    def assert_nested_equal(self, a, b):
        if isinstance(a, dict):
            self.assertEqual(set(a), set(b))
            for key in a:
                self.assert_nested_equal(a[key], b[key])
        elif isinstance(a, list):
            self.assertEqual(len(a), len(b))
            for x, y in zip(a, b):
                self.assert_nested_equal(x, y)
        elif isinstance(a, (int, float)) and not isinstance(a, bool):
            self.assertAlmostEqual(a, b, places=6)
        else:
            self.assertEqual(a, b)

    def test_odwrocenie_p_wps_i_sciezek_nie_zmienia_wynikow(self):
        for staff in (1, 2):
            p = {**domyslne_parametry(), "pracownicy": [nowy_pracownik(i) for i in range(staff)],
                 "koszt_staly_na_godzine": 1.0}
            baseline = oblicz_model_czasowy(p)
            for variant in ("P", "WPS", "ugody", "bez_ugody", "wszystko"):
                def reordered(params):
                    result = oblicz_przeplyw(params)
                    if variant in ("P", "wszystko"):
                        result["grupy"].sort(key=lambda g: g["rodzaj"], reverse=True)
                    if variant in ("WPS", "wszystko"):
                        result["grupy"] = [g for rodzaj in dict.fromkeys(g["rodzaj"] for g in result["grupy"])
                                           for g in reversed(result["grupy"]) if g["rodzaj"] == rodzaj]
                    return result
                settlement_paths = timeline.SCIEZKI_UGODOWE
                judgment_paths = timeline.SCIEZKI_BEZ_UGODY
                if variant in ("ugody", "wszystko"):
                    settlement_paths = tuple(reversed(settlement_paths))
                if variant in ("bez_ugody", "wszystko"):
                    judgment_paths = tuple(reversed(judgment_paths))
                with (
                    self.subTest(staff=staff, variant=variant),
                    patch.object(timeline, "oblicz_przeplyw", reordered),
                    patch.object(timeline, "SCIEZKI_UGODOWE", settlement_paths),
                    patch.object(timeline, "SCIEZKI_BEZ_UGODY", judgment_paths),
                ):
                    result = oblicz_model_czasowy(p)
                    self.assert_nested_equal(baseline, result)

    def test_wiecej_fte_nie_zwieksza_backlogu_ani_opoznien(self):
        results = [oblicz_model_czasowy({**domyslne_parametry(), "pracownicy": [nowy_pracownik(i) for i in range(n)]}) for n in (1, 2, 3, 10)]
        for lower, higher in zip(results, results[1:]):
            for a, b in zip(lower["tabela_miesieczna"], higher["tabela_miesieczna"]):
                self.assertLessEqual(b["Backlog na koniec (h)"] + b["Praca przyszła i zablokowana (h)"],
                                     a["Backlog na koniec (h)"] + a["Praca przyszła i zablokowana (h)"] + 1e-7)
            # Średnia opóźnień dotyczy zakończonych spraw; dodanie roli może
            # odblokować wcześniej niezakończalne sprawy i zmienić próbę.
            self.assertGreaterEqual(higher["walidacja"]["laczne_zakonczenia_spraw"],
                                    lower["walidacja"]["laczne_zakonczenia_spraw"] - 1e-7)
        self.assertAlmostEqual(results[-1]["podsumowanie"]["backlog_koniec_godziny"], 0)

    def test_obfita_obsada_zachowuje_nominalny_przeplyw(self):
        p = {**domyslne_parametry(), "pracownicy": [nowy_pracownik(i) for i in range(10)]}
        lifecycle = oblicz_przeplyw(p)
        result = oblicz_model_czasowy(p)
        shares = lifecycle["udzialy_ugod"]
        for row in result["tabela_miesieczna"]:
            m = row["Miesiąc"]
            self.assertAlmostEqual(row["Ugody zakończone"], 50 * shares["zakonczone_ugoda"] / 100 if m >= 7 else 0)
            self.assertAlmostEqual(row["Zakończenia po I instancji"], 50 * (.425 * int(m >= 10) + .2875 * int(m >= 11)) / 2)
            self.assertAlmostEqual(row["Zakończenia po II instancji"], 50 * (.425 * int(m >= 17) + .2875 * int(m >= 18)) / 2)
            self.assertAlmostEqual(row["Przychód z ugód"], lifecycle["ogolem"]["przychod_ugody"] / 12 if m >= 7 else 0)
            self.assertAlmostEqual(row["Przychód z wyroków"], lifecycle["ogolem"]["przychod_wyroki"] / 24 / .7125 * (.425 * (int(m >= 10) + int(m >= 17)) + .2875 * (int(m >= 11) + int(m >= 18))))
            self.assertAlmostEqual(row["Backlog na koniec (h)"], 0)
        self.assertEqual(result["podsumowanie"]["maksymalne_opoznienie_pojemnosci_miesiace"], 0)
        last_year = result["tabela_miesieczna"][-12:]
        self.assertAlmostEqual(sum(row["Ugody zakończone"] + row["Zakończenia po I instancji"] + row["Zakończenia po II instancji"] for row in last_year), p["liczba_spraw"])
        self.assertAlmostEqual(sum(row["Przychód razem"] for row in last_year), lifecycle["ogolem"]["przychod"])

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
        lifecycle = oblicz_przeplyw(self.parametry)
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

class TestKolejkaIOpoznieniePrzychodu(unittest.TestCase):
    def setUp(self):
        self.parametry = domyslne_parametry()

    def test_niedostateczna_obsada_tworzy_rosnacy_backlog_i_nie_gubi_pracy(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "pracownicy": [nowy_pracownik(i) for i in range(1)]}
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
            {**self.parametry, "pracownicy": [nowy_pracownik(i) for i in range(1)]}
        )
        zapas = oblicz_model_czasowy(
            {**self.parametry, "pracownicy": [nowy_pracownik(i) for i in range(10)]}
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
            {**self.parametry, "pracownicy": [nowy_pracownik(i) for i in range(50)]}
        )
        tabela = wynik["tabela_miesieczna"]
        self.assertEqual(pierwszy_miesiac_z_wartoscia(tabela, "Przychód z ugód"), 7)
        self.assertEqual(pierwszy_miesiac_z_wartoscia(tabela, "Przychód z wyroków"), 10)

    def test_opoznienie_platnosci_przesuwa_przychod_i_break_even(self):
        parametry = {
            **self.parametry,
            "pracownicy": [nowy_pracownik(i) for i in range(4)],
            "koszt_staly_na_godzine": 1.0,

        }
        roster = [osoba("EH", 1)] * 3 + [osoba("UGODY", 1)]
        bez = oblicz_model_czasowy(parametry, pracownicy=roster)
        opozniony = oblicz_model_czasowy(
            parametry, {"opoznienie_platnosci_miesiace": 4}, pracownicy=roster
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
        jeden = oblicz_model_czasowy({**self.parametry, "pracownicy": [nowy_pracownik(i) for i in range(1)]})
        pieciu = oblicz_model_czasowy({**self.parametry, "pracownicy": [nowy_pracownik(i) for i in range(5)]})
        self.assertGreater(
            pieciu["pojemnosc"]["miesieczny_koszt_wynagrodzen"],
            jeden["pojemnosc"]["miesieczny_koszt_wynagrodzen"],
        )
        self.assertGreater(
            pieciu["pojemnosc"]["pojemnosc_na_sprawy_minuty"],
            jeden["pojemnosc"]["pojemnosc_na_sprawy_minuty"],
        )
        self.assertLess(
            pieciu["podsumowanie"]["backlog_koniec_godziny"],
            jeden["podsumowanie"]["backlog_koniec_godziny"],
        )

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

    def test_trwaly_break_even_odrzuca_powrot_pod_zero(self):
        wynik = wyznacz_trwaly_break_even(
            [-10.0, 2.0, -1.0, 3.0], [1, 2, 3, 4], "Stabilna", 10.0
        )
        self.assertEqual(wynik["miesiac"], 4)

    def test_na_granicy_jest_wykonalne_dla_break_even(self):
        wynik = wyznacz_trwaly_break_even(
            [-1.0, 1.0], [1, 2], "Na granicy", 1.0
        )
        self.assertEqual(wynik["status"], "osiagniety")

class TestDojrzaloscAktywnychSciezek(unittest.TestCase):
    def setUp(self):
        self.parametry = {
            **domyslne_parametry(),
            "pracownicy": [nowy_pracownik(i) for i in range(4)],
            "koszt_staly_na_godzine": 20.0,

            "udzial_ii_instancji_percent": 0.0,
        }

    def assert_roczne_uzgodnienie(self, wynik, parametry):
        lifecycle = oblicz_przeplyw(parametry)
        rows = wynik["tabela_miesieczna"][-12:]
        self.assertTrue(wynik["podsumowanie"]["dojrzalosc_osiagnieta"])
        self.assertAlmostEqual(sum(
            row["Ugody zakończone"] + row["Zakończenia po I instancji"]
            + row["Zakończenia po II instancji"] for row in rows
        ), parametry["liczba_spraw"])
        self.assertAlmostEqual(sum(row["Przychód razem"] for row in rows), lifecycle["ogolem"]["przychod"])
        self.assertAlmostEqual(sum(row["Nowa praca (h)"] * 60 for row in rows), lifecycle["bezposrednie_minuty_spraw"])
        self.assertTrue(all(abs(row["Backlog na koniec (h)"]) < 1e-8 for row in rows))

    def test_zero_ii_potwierdza_dojrzalosc_i_trwaly_break_even(self):
        wynik = oblicz_model_czasowy(self.parametry, {"horyzont_miesiace": 24},
                                     pracownicy=[osoba("EH", 20)] * 3 + [osoba("UGODY", 20)])
        self.assert_roczne_uzgodnienie(wynik, self.parametry)
        self.assertEqual(wynik["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 11)
        self.assertAlmostEqual(wynik["kpi"]["wynik_miesieczny_w_stanie_stabilnym"], 16997.3545)
        self.assertEqual(wynik["kpi"]["break_even_status"], "osiagniety")
        self.assertEqual(wynik["kpi"]["break_even_miesiac"], 18)
        self.assertEqual(wynik["kpi"]["status_break_even"], "Break-even trwały")

    def test_same_ii_respektuja_termin_ii_i_pelny_rok(self):
        parametry = {**self.parametry, "udzial_ii_instancji_percent": 100.0, "pracownicy": [nowy_pracownik(i) for i in range(10)]}
        short = oblicz_model_czasowy(parametry, {"horyzont_miesiace": 28})
        self.assertEqual(short["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 18)
        self.assertFalse(short["podsumowanie"]["dojrzalosc_osiagnieta"])
        mature = oblicz_model_czasowy(parametry, {"horyzont_miesiace": 29})
        self.assert_roczne_uzgodnienie(mature, parametry)
        self.assertTrue(all(row["Zakończenia po I instancji"] == 0 for row in mature["tabela_miesieczna"]))
        self.assertEqual(pierwszy_miesiac_z_wartoscia(mature["tabela_miesieczna"], "Zakończenia po II instancji"), 17)

    def test_zero_ugod_pomija_ich_termin(self):
        parametry = {**self.parametry, "automatyczne_ramy_percent": 0.0,
                     "zawarte_ugody_percent": 0.0, "pracownicy": [nowy_pracownik(i) for i in range(10)]}
        for settlement_lag in (0, 100):
            with self.subTest(settlement_lag=settlement_lag):
                czas = {"miesiace_do_ugody": settlement_lag, "horyzont_miesiace": 22}
                wynik = oblicz_model_czasowy(parametry, czas)
                self.assertEqual(wynik["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 11)
                self.assert_roczne_uzgodnienie(wynik, parametry)
                short = oblicz_model_czasowy(parametry, {**czas, "horyzont_miesiace": 21})
                self.assertFalse(short["podsumowanie"]["dojrzalosc_osiagnieta"])

    def test_same_ugody_pomijaja_obydwa_terminy_wyrokow(self):
        parametry = {**self.parametry, "kategoryczna_odmowa_percent": 0.0,
                     "automatyczne_ramy_percent": 100.0,
                     "skutecznosc_automatycznych_ram_percent": 100.0,
                     "udzial_ii_instancji_percent": 100.0, "pracownicy": [nowy_pracownik(i) for i in range(10)]}
        czas = {"miesiace_do_wyroku_i": 100, "miesiace_wyrok_i_do_ii": 100,
                "horyzont_miesiace": 18}
        wynik = oblicz_model_czasowy(parametry, czas)
        self.assertEqual(wynik["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 7)
        self.assert_roczne_uzgodnienie(wynik, parametry)
        short = oblicz_model_czasowy(parametry, {**czas, "horyzont_miesiace": 17})
        self.assertFalse(short["podsumowanie"]["dojrzalosc_osiagnieta"])

    def test_platnosc_opoznia_dojrzalosc_przychodu_ale_nie_prace(self):
        czas = {"opoznienie_platnosci_miesiace": 4, "horyzont_miesiace": 26}
        delayed = oblicz_model_czasowy(self.parametry, czas)
        self.assertEqual(delayed["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 15)
        self.assert_roczne_uzgodnienie(delayed, self.parametry)
        short = oblicz_model_czasowy(self.parametry, {**czas, "horyzont_miesiace": 25})
        self.assertFalse(short["podsumowanie"]["dojrzalosc_osiagnieta"])
        direct = oblicz_model_czasowy(self.parametry, {**czas, "opoznienie_platnosci_miesiace": 0})
        for a, b in zip(direct["tabela_miesieczna"], delayed["tabela_miesieczna"]):
            for key in ("Nowa praca (h)", "Wykonana praca (h)", "Backlog na koniec (h)",
                        "Ugody zakończone", "Zakończenia po I instancji", "Zakończenia po II instancji"):
                self.assertEqual(a[key], b[key])
        self.assertEqual(pierwszy_miesiac_z_wartoscia(delayed["tabela_miesieczna"], "Przychód z wyroków"), 14)

    def test_zero_naplywu_nie_fabrykuje_dojrzalosci(self):
        wynik = oblicz_model_czasowy({**self.parametry, "liczba_spraw": 0})
        self.assertEqual(wynik["kpi"]["status_kontraktu"], "Brak napływu spraw")
        self.assertEqual(wynik["podsumowanie"]["status_stanu_stabilnego"], "Brak napływu spraw")
        self.assertIsNone(wynik["podsumowanie"]["nominalny_miesiac_dojrzalosci"])
        self.assertFalse(wynik["podsumowanie"]["dojrzalosc_osiagnieta"])
        self.assertIsNone(wynik["kpi"]["wynik_miesieczny_w_stanie_stabilnym"])

    def test_aktywnosc_sciezki_uzywa_tolerancji(self):
        parametry = {**self.parametry, "udzial_ii_instancji_percent": 1e-9}
        self.assertEqual(_nominalny_miesiac_dojrzalosci(
            oblicz_przeplyw(parametry), domyslne_parametry_czasowe()
        ), 11)

    def test_poprawny_termin_nie_zastepuje_wystarczajacej_pojemnosci(self):
        wynik = oblicz_model_czasowy({**self.parametry, "pracownicy": [nowy_pracownik(i) for i in range(1)]}, {"horyzont_miesiace": 24})
        self.assertEqual(wynik["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 11)
        self.assertFalse(wynik["podsumowanie"]["dojrzalosc_osiagnieta"])
        self.assertIsNone(wynik["kpi"]["wynik_miesieczny_w_stanie_stabilnym"])

class TestPrzypadkiBrzegowe(unittest.TestCase):
    def setUp(self):
        self.parametry = domyslne_parametry()

    def test_zero_rocznego_naplywu(self):
        wynik = oblicz_model_czasowy({**self.parametry, "liczba_spraw": 0})
        self.assertTrue(all(w["Nowe sprawy"] == 0 for w in wynik["tabela_miesieczna"]))
        self.assertEqual(wynik["podsumowanie"]["aktywne_sprawy"], 0.0)
        self.assertEqual(wynik["podsumowanie"]["backlog_koniec_godziny"], 0.0)
        self.assertTrue(
            all(
                w["Wynik miesięczny przed podatkiem"]
                == -w["Łączny koszt miesięczny"]
                for w in wynik["tabela_miesieczna"]
            )
        )

    def test_zero_pracownikow(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "pracownicy": [nowy_pracownik(i) for i in range(0)]},
            {"horyzont_miesiace": 24},
        )
        self.assertEqual(wynik["pojemnosc"]["pojemnosc_brutto_minuty"], 0.0)
        self.assertEqual(wynik["pojemnosc"]["miesieczny_koszt_wynagrodzen"], 0.0)
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
            {**self.parametry, "pracownicy": [nowy_pracownik(i) for i in range(50)]},
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
                "pracownicy": [nowy_pracownik(i) for i in range(10)],
                "kategoryczna_odmowa_percent": 0.0,
                "automatyczne_ramy_percent": 100.0,
                "skutecznosc_automatycznych_ram_percent": 100.0,
                "udzial_ii_instancji_percent": 100.0,
            }
        )
        bez_ugod_i_ii = oblicz_model_czasowy(
            {
                **self.parametry,
                "pracownicy": [nowy_pracownik(i) for i in range(10)],
                "automatyczne_ramy_percent": 0.0,
                "zawarte_ugody_percent": 0.0,
                "udzial_ii_instancji_percent": 0.0,
            }
        )
        bez_ugod_same_ii = oblicz_model_czasowy(
            {
                **self.parametry,
                "pracownicy": [nowy_pracownik(i) for i in range(10)],
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

class TestRoleIKosztyKontraktu(unittest.TestCase):
    def setUp(self):
        self.p = domyslne_parametry()
        self.roster = [osoba("EH", 20)] * 3 + [osoba("UGODY", 30)]
        self.p.update(sekretariat_minuty_na_sprawe=30., koszt_sekretariatu_na_godzine=30.)
        self.costs = {}

    def licz(self, p=None, czas=None, roster=None, costs=None):
        return oblicz_model_czasowy(p or self.p, czas, pracownicy=self.roster if roster is None else roster,
                                    koszty_kontraktu=self.costs if costs is None else costs)

    def test_A_wspolny_narzut_zmienia_koszt_kontraktu(self):
        a, b = self.licz(), self.licz({**self.p, "koszt_staly_na_godzine": 60.0})
        self.assertEqual(a["pojemnosc"], b["pojemnosc"])
        for x, y in zip(a["tabela_miesieczna"], b["tabela_miesieczna"]):
            self.assertAlmostEqual(y["Łączny koszt miesięczny"] - x["Łączny koszt miesięczny"],
                                   (x["Wykonana praca (h)"] + x["Czynności dzienne (h)"]) * 24)

    def test_B_stare_niezerowe_koszty_sa_odrzucane(self):
        for key in ("ogolne_na_aktywna_sprawe", "sekretariat_na_aktywna_sprawe"):
            with self.assertRaisesRegex(ValueError, "Wycofany koszt"):
                self.licz(costs={key: 1.0})
            with self.assertRaisesRegex(ValueError, "Wycofany koszt"):
                oblicz_model({**self.p, "koszty_kontraktu": {key: 1.0}})
        self.assertEqual(self.licz(), self.licz(costs={"ogolne_na_aktywna_sprawe": 0.0}))

    def test_D_sekretariat_nie_zuzywa_pojemnosci(self):
        zmiana = {**self.p, "sekretariat_minuty_na_sprawe": 10000.0, "koszt_sekretariatu_na_godzine": 50.0}
        self.assertEqual(self.licz()["pojemnosc"], self.licz(zmiana)["pojemnosc"])

    def test_E_stawka_sekretariatu_jest_niezalezna(self):
        zmiana = {**self.p, "koszt_sekretariatu_na_godzine": 500.0, "sekretariat_minuty_na_sprawe": 10.0,
                  }
        self.assertNotEqual(self.licz()["tabela_miesieczna"], self.licz(zmiana)["tabela_miesieczna"])
        self.assertEqual(self.licz()["pojemnosc"], self.licz(zmiana)["pojemnosc"])

    def test_F_narzut_godzinowy_i_50_jednorazowych_obslug(self):
        pierwszy = self.licz()["tabela_miesieczna"][0]
        self.assertEqual(pierwszy["Sprawy, nad którymi pracowano w miesiącu"], 50)
        self.assertAlmostEqual(pierwszy["Narzut od wykonanej pracy nad sprawami"], pierwszy["Wykonana praca (h)"] * 36)
        self.assertEqual(pierwszy["Jednorazowe koszty sekretariatu"], 750)

    def test_GHI_naliczanie_tylko_w_miesiacu_pracy(self):
        p = {**self.p, "liczba_spraw": 12, "kategoryczna_odmowa_percent": 0.0,
             "automatyczne_ramy_percent": 100.0, "skutecznosc_automatycznych_ram_percent": 100.0}
        rows = self.licz(p, {"miesiace_do_ugody": 2, "horyzont_miesiace": 6})["tabela_miesieczna"]
        # Jedna nowa sprawa na miesiąc: każda pracuje tylko w miesiącu wpływu.
        self.assertEqual([r["Sprawy, nad którymi pracowano w miesiącu"] for r in rows], [1, 1, 1, 1, 1, 1])
        self.assertEqual([r["Sprawy otwarte"] for r in rows], [1, 2, 2, 2, 2, 2])
        # Miesiące oczekiwania i formalnego zakończenia nie dodają opłat.
        for row in rows:
            self.assertAlmostEqual(row["Narzut od wykonanej pracy nad sprawami"], (30 + 150.3 + 55) / 60 * 36)

    def test_GH_nawet_natychmiastowe_zakonczenie_kosztuje_jeden_miesiac(self):
        from test_workflow import proste
        p = proste(600, proces=60)
        rows = self.licz(p, {"miesiace_do_wyroku_i": 0})["tabela_miesieczna"]
        for r in rows:
            self.assertAlmostEqual(r["Sprawy otwarte"], 0)
            self.assertAlmostEqual(r["Sprawy, nad którymi pracowano w miesiącu"], 50)
            self.assertAlmostEqual(r["Narzut od wykonanej pracy nad sprawami"], 50 * 36)

    def test_IJ_opoznienie_platnosci_nie_przedluza_kosztu(self):
        a, b = self.licz(), self.licz(czas={"opoznienie_platnosci_miesiace": 8})
        for x, y in zip(a["tabela_miesieczna"], b["tabela_miesieczna"]):
            for key in ("Sprawy, nad którymi pracowano w miesiącu", "Aktywne sprawy", "Łączny koszt miesięczny"):
                self.assertEqual(x[key], y[key])
        self.assertEqual(pierwszy_miesiac_z_wartoscia(b["tabela_miesieczna"], "Przychód razem"),
                         pierwszy_miesiac_z_wartoscia(a["tabela_miesieczna"], "Przychód razem") + 8)

    def test_KL_60_procent_daje_6012_i_proporcjonalna_pojemnosc(self):
        p = oblicz_pojemnosc_miesieczna(self.p, pracownicy=[osoba("EH", 60, 60)])
        eh = p["role"]["EH"]
        self.assertAlmostEqual(eh["wynagrodzenia"], 6012)
        self.assertAlmostEqual(eh["brutto_minuty"] / 60, 100.2)
        self.assertAlmostEqual(eh["dzienne_minuty"] / 60, 31.3125)
        self.assertAlmostEqual(eh["netto_minuty"] / 60, 100.2 - 31.3125)
        full = oblicz_pojemnosc_miesieczna(self.p, pracownicy=[osoba("EH", 60)])
        self.assertAlmostEqual(eh["netto_minuty"], 100.2 * 60 - 31.3125 * 60)

    def test_M_zero_przydzialu(self):
        result = self.licz(roster=[osoba("EH", 999, 0), osoba("UGODY", 999, 0)])
        self.assertEqual(result["pojemnosc"]["pojemnosc_na_sprawy_minuty"], 0)
        self.assertEqual(result["pojemnosc"]["miesieczny_koszt_wynagrodzen"], 0)
        self.assertTrue(all(r["Wykonana praca (h)"] == 0 for r in result["tabela_miesieczna"]))

    def test_N_magazyn_zachowuje_ustawienia_po_usunieciu_i_dodaniu(self):
        from staff import przywroc_obsade
        state = {}
        przywroc_obsade(state, 2)
        state["ustawienia_obsady"][1] = osoba("EH", 71, 37)
        przywroc_obsade(state, 1)
        self.assertEqual(przywroc_obsade(state, 3)[1], osoba("EH", 71, 37))

    def test_OQ_bez_ugod_nie_ma_zastepstwa(self):
        result = self.licz(roster=[osoba("EH", 1)] * 10)
        self.assertEqual(result["pojemnosc"]["role"]["UGODY"]["netto_minuty"], 0)
        self.assertEqual(result["pojemnosc"]["status_pojemnosci"], "Niewystarczająca")
        self.assertTrue(all(r["Wykonana praca UGODY (h)"] == 0 and r["Ugody zakończone"] == 0
                            for r in result["tabela_miesieczna"]))
        self.assertGreater(result["tabela_miesieczna"][-1]["Backlog UGODY (h)"], 0)
        self.assertIsNone(result["podsumowanie"]["miesiace_backlogu_wedlug_roli"]["UGODY"])
        self.assertIsNone(result["podsumowanie"]["miesiace_backlogu"])

    def test_P_bez_EH_nie_ma_zastepstwa(self):
        result = self.licz(roster=[osoba("UGODY", 1)] * 10)
        self.assertTrue(all(r["Wykonana praca EH (h)"] == 0 and r["Przychód razem"] == 0
                            for r in result["tabela_miesieczna"]))
        self.assertGreater(result["tabela_miesieczna"][-1]["Backlog EH (h)"], 0)

    def test_R_niedobor_EH_mimo_bezczynnych_ugod(self):
        result = self.licz(roster=[osoba("EH", 20, 10)] + [osoba("UGODY", 20)] * 10)
        row = result["tabela_miesieczna"][-1]
        self.assertGreater(row["Backlog EH (h)"], 0)
        self.assertAlmostEqual(row["Backlog UGODY (h)"], 0)
        self.assertGreater(row["Pojemność UGODY (h)"], row["Wykonana praca UGODY (h)"])
        self.assertIsNone(result["kpi"]["wynik_miesieczny_w_stanie_stabilnym"])
        self.assertEqual(result["kpi"]["break_even_status"], "brak_pojemnosci")

    def test_S_wszystkie_role_blokuja_przychod(self):
        for roster in ([osoba("EH", 0)] * 10, [osoba("UGODY", 0)] * 10):
            p = {**self.p, "kategoryczna_odmowa_percent": 0.0, "automatyczne_ramy_percent": 100.0,
                 "skutecznosc_automatycznych_ram_percent": 100.0}
            with self.subTest(roster=roster):
                self.assertEqual(sum(r["Przychód razem"] for r in self.licz(p, roster=roster)["tabela_miesieczna"]), 0)

    def test_T_II_czeka_na_termin_I_nawet_gdy_wczesniej_ma_moc(self):
        p = {**self.p, "udzial_ii_instancji_percent": 100.0}
        r = oblicz_model_czasowy(p, pracownicy=self.roster, zapisz_zdarzenia=True)
        work = [e for e in r["zdarzenia"] if e["etap"] == "ii_instancja" and e["rodzaj"] == "praca"]
        self.assertTrue(work)
        self.assertEqual(min(e["miesiac"] for e in work), 11)
        self.assertTrue(all(row["Ukończona praca: ii_instancja"] == 0 for row in r["tabela_miesieczna"][:10]))

    def test_U_kazda_kolejka_zachowuje_minuty_dla_roznych_obsad(self):
        for roster in ([], [osoba("EH")], [osoba("UGODY")], self.roster,
                       [osoba("EH", 80, 60), osoba("UGODY", 90, 15)]):
            with self.subTest(roster=roster):
                result = self.licz(roster=roster)
                for role, w in result["walidacja"]["role"].items():
                    self.assertAlmostEqual(w["nalezna_minuty"], w["wykonana_minuty"] + w["backlog_minuty"], places=5)
                opening = 0
                inflow = completed = 0
                for row in result["tabela_miesieczna"]:
                    inflow += row["Nowe sprawy"]
                    completed += sum(row[k] for k in ("Ugody zakończone", "Zakończenia po I instancji", "Zakończenia po II instancji"))
                    self.assertLessEqual(row["Sprawy, nad którymi pracowano w miesiącu"], opening + row["Nowe sprawy"] + 1e-6)
                    self.assertAlmostEqual(row["Aktywne sprawy"], inflow - completed, places=6)
                    opening = row["Aktywne sprawy"]
                    for role in ("EH", "UGODY"):
                        self.assertAlmostEqual(row[f"Backlog {role} (h)"], row[f"Backlog początek {role} (h)"] +
                                               row[f"Nowa praca {role} (h)"] - row[f"Wykonana praca {role} (h)"], places=7)

    def test_V_dojrzalosc_uzgadnia_role_liczby_przychod_i_koszty(self):
        result = self.licz()
        self.assertTrue(result["podsumowanie"]["dojrzalosc_osiagnieta"])
        rows = result["tabela_miesieczna"][-12:]
        lifecycle = oblicz_model(self.p)
        self.assertAlmostEqual(sum(r["Przychód razem"] for r in rows), lifecycle["ogolem"]["przychod"])
        self.assertAlmostEqual(sum(r["Wykonana praca (h)"] * 60 for r in rows), lifecycle["bezposrednie_minuty_spraw"])
        self.assertAlmostEqual(sum(sum(r[k] for k in ("Ugody zakończone", "Zakończenia po I instancji", "Zakończenia po II instancji")) for r in rows), 600)
        # Niezależne wyprowadzenie popytu ról z sześciu ścieżek.
        eh = 50 * (30 + 150.3 + .275 * 30 + .7125 * 250 + .7125 * .5 * 210)
        ugody = 50 * (.2875 * 55 + (.15 + .1375) * 35 + (.1375 + .1375) * 30)
        self.assertAlmostEqual(result["pojemnosc"]["role"]["EH"]["popyt_minuty"], eh)
        self.assertAlmostEqual(result["pojemnosc"]["role"]["UGODY"]["popyt_minuty"], ugody)
        # Bieżące przyjęcia + przekazany proces po nieudanej próbie + II instancja.
        active_billable = 50 + 50 * .2875 + 50 * .35625
        expected_cost = 167 * (3 * 20 + 30) + (5131.875 / 12) * 36 + 50 * 15
        self.assertAlmostEqual(rows[-1]["Sprawy, nad którymi pracowano w miesiącu"], active_billable)
        self.assertAlmostEqual(rows[-1]["Łączny koszt miesięczny"], expected_cost)
        self.assertAlmostEqual(result["kpi"]["wynik_miesieczny_w_stanie_stabilnym"], lifecycle["ogolem"]["przychod"] / 12 - expected_cost)

    def test_W_wysokie_wspolne_koszty_obciazaja_obydwa_panele(self):
        p = {**self.p, "koszt_staly_na_godzine": 500.0, "koszt_sekretariatu_na_godzine": 500.0,
             "sekretariat_minuty_na_sprawe": 60.0}
        self.assertLess(oblicz_model(p)["ogolem"]["wynik_przed_podatkiem"], 0)
        result = self.licz(p, costs={"ogolne_na_aktywna_sprawe": 0.0, "sekretariat_na_aktywna_sprawe": 0.0})
        self.assertEqual(result["kpi"]["status_kontraktu"], "Stabilny, ale nierentowny")
        self.assertLess(result["kpi"]["wynik_miesieczny_w_stanie_stabilnym"], 0)

    def test_dodatnia_ekonomika_panelu_1_i_strata_kontraktu(self):
        roster = [osoba("EH", 1)] * 30 + [osoba("UGODY", 1)]
        p = {**self.p, "liczba_spraw": 12, "codzienne_czynnosci": {}, "koszt_staly_na_godzine": 0.0, "pracownicy": roster}
        self.assertGreater(oblicz_model(p)["ogolem"]["wynik_przed_podatkiem"], 0)
        result = self.licz(p, roster=roster)
        self.assertEqual(result["kpi"]["status_kontraktu"], "Stabilny, ale nierentowny")
        self.assertEqual(result["kpi"]["break_even_status"], "brak_ekonomiczny")
        self.assertTrue(result["kpi"]["wynik_nadal_narasta"])

    def test_XY_dokladna_suma_bez_podwojnych_kosztow(self):
        for r in self.licz()["tabela_miesieczna"]:
            total = r["Wynagrodzenia EH"] + r["Wynagrodzenia ugód"] + r["Narzut kosztów ogólnych razem"] + r["Jednorazowe koszty sekretariatu"]
            self.assertEqual(r["Łączny koszt miesięczny"], total)
            self.assertEqual(r["Wynik miesięczny przed podatkiem"], r["Przychód razem"] - total)

    def test_niepelny_rozruch_nie_fabrykuje_dojrzalego_kosztu(self):
        result = self.licz(czas={"horyzont_miesiace": 12})
        self.assertIsNone(result["kpi"]["wynik_miesieczny_w_stanie_stabilnym"])
        self.assertEqual(result["kpi"]["status_kontraktu"], "Stabilny operacyjnie, rentowność niepotwierdzona")
        self.assertEqual(result["kpi"]["break_even_status"], "niepotwierdzony")

    def test_dluzsze_oczekiwanie_nie_zwieksza_kosztu_tej_samej_pracy(self):
        p = {**self.p, "udzial_ii_instancji_percent": 0.0}
        a = self.licz(p, {"horyzont_miesiace": 120})
        b = self.licz(p, {"miesiace_do_ugody": 60, "miesiace_do_wyroku_i": 60, "horyzont_miesiace": 120})
        self.assertTrue(b["podsumowanie"]["dojrzalosc_osiagnieta"])
        self.assertEqual(b["diagnoza"]["koszt_kontraktu_horyzont"], a["diagnoza"]["koszt_kontraktu_horyzont"])
        self.assertEqual(a["walidacja"]["praca_wszystkich_kohort_minuty"], b["walidacja"]["praca_wszystkich_kohort_minuty"])
        self.assertLess(sum(r["Przychód razem"] for r in b["tabela_miesieczna"]), sum(r["Przychód razem"] for r in a["tabela_miesieczna"]))

    def test_zero_spraw_zero_oplat_aktywnych_ale_pelna_placa(self):
        result = self.licz({**self.p, "liczba_spraw": 0})
        for r in result["tabela_miesieczna"]:
            self.assertEqual(r["Narzut od wykonanej pracy nad sprawami"], 0)
            self.assertEqual(r["Jednorazowe koszty sekretariatu"], 0)
            self.assertEqual(r["Łączny koszt miesięczny"], 167 * 90 + 31.3125 * 36)
        self.assertFalse(result["podsumowanie"]["dojrzalosc_osiagnieta"])

    def test_placa_nie_zalezy_od_wykonanej_pracy(self):
        a = self.licz()
        b = self.licz({**self.p, "liczba_spraw": 0})
        self.assertEqual(a["pojemnosc"]["miesieczny_koszt_wynagrodzen"], b["pojemnosc"]["miesieczny_koszt_wynagrodzen"])

    def test_mieszane_przydzialy_i_stawki_sumowane_osobno(self):
        result = self.licz(roster=[osoba("EH", 60, 60), osoba("EH", 80, 25), osoba("UGODY", 100, 0)])
        self.assertAlmostEqual(result["pojemnosc"]["miesieczny_koszt_wynagrodzen"], 6012 + 3340)
        self.assertAlmostEqual(result["pojemnosc"]["role"]["EH"]["netto_minuty"] / 60, 167 * .85 - 31.3125)

    def test_porownanie_wylacznie_jawnych_skladow(self):
        variants = {"Obecny": self.roster, "Ograniczony przydział": [osoba("EH", 20, 60), osoba("UGODY", 30, 10)]}
        rows = porownaj_obsade(self.p, scenariusze=variants, koszty_kontraktu=self.costs)
        self.assertEqual([r["Wariant"] for r in rows], list(variants))
        self.assertEqual(rows[0]["Koszt wynagrodzeń"], 167 * 90)
        self.assertFalse(any("Najlepszy" in r for r in rows))
        with self.assertRaises(TypeError):
            porownaj_obsade(self.p)

    def test_walidacja_kosztow_i_pracownikow(self):
        for bad in (-1, float("nan"), float("inf"), True, "50"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.licz(costs={"ogolne_na_aktywna_sprawe": bad})
        for roster in ([osoba("INNA")], [osoba("EH", -1)], [osoba("EH", 1, 101)],
                       [osoba("EH", 1, float("nan"))], [{}], "EH"):
            with self.subTest(roster=roster), self.assertRaises(ValueError):
                self.licz(roster=roster)
        with self.assertRaises(ValueError):
            self.licz(costs={"nieznany": 1})
        with self.assertRaises(ValueError):
            oblicz_model_czasowy({**self.p, "pracownicy": [{}]})

class TestWyczerpanaPojemnoscRoli(unittest.TestCase):
    def test_caly_dzien_EH_blokuje_tylko_EH(self):
        p = {**domyslne_parametry(), "codzienne_czynnosci": {
            "Komunikacja z EH i zlecanie opłat w SOSS": 480}}
        result = oblicz_model_czasowy(p)
        self.assertEqual(result["pojemnosc"]["role"]["EH"]["netto_minuty"], 0)
        self.assertEqual(result["pojemnosc"]["role"]["UGODY"]["netto_minuty"], 10020)
        self.assertTrue(all(r["Wykonana praca EH (h)"] == 0 for r in result["tabela_miesieczna"]))
        self.assertEqual(sum(r["Wykonana praca UGODY (h)"] for r in result["tabela_miesieczna"]), 0)

    def test_dwie_role_nie_maja_wspolnego_mnoznika_dziennego(self):
        p = {**domyslne_parametry(), "codzienne_czynnosci": {"Obsługa skrzynki ugody EH": 480}}
        result = oblicz_model_czasowy(p)
        self.assertEqual(result["pojemnosc"]["role"]["UGODY"]["netto_minuty"], 10020)
        self.assertEqual(result["pojemnosc"]["role"]["EH"]["netto_minuty"], 0)
        self.assertTrue(all(r["Wykonana praca EH (h)"] == r["Wykonana praca UGODY (h)"] == 0 for r in result["tabela_miesieczna"]))

if __name__ == "__main__":
    unittest.main()
