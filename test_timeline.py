import unittest
from collections import defaultdict, deque
from unittest.mock import patch

import timeline

from model import (
    MINUTY_DNIA_PRACY,
    domyslne_parametry,
    oblicz_model,
)
from timeline import (
    Completion,
    GODZINY_ETATU_MIESIECZNIE,
    _dodaj_kohorte,
    _dodaj_pakiet,
    _nominalny_miesiac_dojrzalosci,
    _przyrost_zakonczenia,
    _wykonaj_prace,
    domyslne_parametry_czasowe,
    klasyfikuj_status_kontraktu,
    minimalna_liczba_pracownikow_dla_stabilnosci,
    oblicz_model_czasowy,
    oblicz_pojemnosc_miesieczna,
    porownaj_obsade,
    wyznacz_break_even,
    wyznacz_trwaly_break_even,
)


def pierwszy_miesiac_z_wartoscia(wiersze, klucz):
    return next(w["Miesiąc"] for w in wiersze if w[klucz] > 1e-8)


def parametry_jednej_sciezki():
    """2,5 sprawy/mies., po 6000 minut w jednym etapie, 10020 minut/FTE."""
    return {
        **domyslne_parametry(),
        "liczba_spraw": 30,
        "liczba_pracownikow": 1,
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


class TestPrzeplywOczekiwany(unittest.TestCase):
    def test_proporcjonalny_podzial_i_fifo_miedzy_miesiacami(self):
        completions = [Completion(1, "test", "ugoda", 5, 10, 8000) for _ in range(4)]
        packets = defaultdict(list)
        stats = {"direct_minutes": 0.0}
        for i, minutes in enumerate((1200, 2400, 3600, 600)):
            _dodaj_pakiet(packets, completions, i, 5 if i < 3 else 6,
                          1, "test", "zawarcie_ugody", minutes, stats)
        queue = deque([packets[5], packets[6]])
        self.assertEqual(_wykonaj_prace(queue, completions, 3600), 3600)
        self.assertEqual([c.stage_executed_minutes["zawarcie_ugody"] for c in completions],
                         [600, 1200, 1800, 0])
        self.assertEqual(_wykonaj_prace(queue, completions, 3900), 3900)
        self.assertEqual([c.stage_executed_minutes["zawarcie_ugody"] for c in completions],
                         [1200, 2400, 3600, 300])
        self.assertEqual(queue[0][0].due_month, 6)

    def test_zakonczenie_wymaga_wszystkich_etapow_i_terminu_nominalnego(self):
        c = Completion(1, "test:ii", "ii", 9, 10, 8000,
                       {"proces": 100, "ii_instancja": 200, "zerowy": 0},
                       {"proces": 100, "ii_instancja": 80})
        self.assertEqual(_przyrost_zakonczenia(c, 8), 0)
        cases, revenue = [], []
        for month, executed, expected in ((9, 80, .4), (10, 150, .35), (11, 200, .25)):
            c.stage_executed_minutes["ii_instancja"] = executed
            increment = _przyrost_zakonczenia(c, month)
            self.assertAlmostEqual(increment, expected)
            cases.append(c.cases * increment)
            revenue.append(c.revenue * increment)
            self.assertEqual(_przyrost_zakonczenia(c, month), 0)
        for actual, expected in zip(cases, (4, 3.5, 2.5)):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(revenue, (3200, 2800, 2000)):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(sum(cases), c.cases)
        self.assertAlmostEqual(sum(revenue), c.revenue)
        self.assertEqual(c.recognized_fraction, 1)
        self.assertEqual(_przyrost_zakonczenia(c, 12), 0)

    def test_brak_przychodu_gdy_jeden_wymagany_etap_jest_niewykonany(self):
        for outcome, final_stage in (("ugoda", "zawarcie_ugody"), ("i", "proces"), ("ii", "ii_instancja")):
            c = Completion(1, "test", outcome, 1, 10, 8000,
                           {"przyjecie": 100, final_stage: 100},
                           {"przyjecie": 100, final_stage: 0})
            self.assertEqual(_przyrost_zakonczenia(c, 1), 0)
            c.stage_executed_minutes[final_stage] = 25
            self.assertEqual(_przyrost_zakonczenia(c, 1), .25)

    def test_zerowa_praca_czeka_na_nominalny_termin(self):
        c = Completion(1, "test", "ugoda", 7, 2.5, 1000)
        self.assertEqual(_przyrost_zakonczenia(c, 6), 0)
        self.assertEqual(_przyrost_zakonczenia(c, 7), 1)
        self.assertEqual(_przyrost_zakonczenia(c, 8), 0)

    def test_rozlozony_etap_rejestruje_caly_wymagany_czas(self):
        p = domyslne_parametry()
        packets, completions = defaultdict(list), []
        _dodaj_kohorte(1, oblicz_model(p), p, domyslne_parametry_czasowe(), packets, completions)
        for i, c in enumerate(completions):
            for stage, total in c.stage_total_minutes.items():
                self.assertAlmostEqual(total, sum(packet.minutes_remaining
                    for bucket in packets.values() for packet in bucket
                    if packet.completion_id == i and packet.stage == stage))
        self.assertTrue(any(c.outcome == "ii" and "ii_instancja" in c.stage_total_minutes for c in completions))

    def test_czesc_agregatu_zamyka_sie_z_proporcjonalnym_przychodem(self):
        p = parametry_jednej_sciezki()
        result = oblicz_model_czasowy(p, {"miesiace_do_ugody": 0, "horyzont_miesiace": 2})
        first, second = result["tabela_miesieczna"]
        self.assertAlmostEqual(first["Wykonana praca (h)"], 167)
        self.assertAlmostEqual(first["Ugody zakończone"], 1.67)
        unit_revenue = oblicz_model(p)["ogolem"]["przychod"] / 30
        self.assertAlmostEqual(first["Przychód z ugód"], 1.67 * unit_revenue)
        self.assertAlmostEqual(second["Ugody zakończone"], 1.67)
        self.assertAlmostEqual(first["Aktywne sprawy"], .83)
        self.assertAlmostEqual(result["podsumowanie"]["srednie_opoznienie_pojemnosci_miesiace"], .83 / 3.34)
        self.assertEqual(result["podsumowanie"]["maksymalne_opoznienie_pojemnosci_miesiace"], 1)

    def test_opoznienie_platnosci_przesuwa_osobno_kazdy_przyrost(self):
        p = parametry_jednej_sciezki()
        time = {"miesiace_do_ugody": 0, "horyzont_miesiace": 5}
        direct = oblicz_model_czasowy(p, time)["tabela_miesieczna"]
        delayed = oblicz_model_czasowy(p, {**time, "opoznienie_platnosci_miesiace": 2})["tabela_miesieczna"]
        for i, (a, b) in enumerate(zip(direct, delayed)):
            for key in ("Wykonana praca (h)", "Backlog na koniec (h)", "Ugody zakończone", "Aktywne sprawy"):
                self.assertAlmostEqual(a[key], b[key])
            self.assertAlmostEqual(b["Przychód razem"], direct[i-2]["Przychód razem"] if i >= 2 else 0)

    def test_ii_instancja_nie_placi_przy_wyroku_i(self):
        p = {**parametry_jednej_sciezki(), "kategoryczna_odmowa_percent": 100.0,
             "automatyczne_ramy_percent": 0.0, "ugodowe_czynnosci": {},
             "udzial_ii_instancji_percent": 100.0, "obsluga_ii_instancji_minuty": 6000}
        time = {"miesiace_do_wyroku_i": 0, "miesiace_wyrok_i_do_ii": 1,
                "opoznienie_platnosci_miesiace": 1, "horyzont_miesiace": 3}
        rows = oblicz_model_czasowy(p, time)["tabela_miesieczna"]
        self.assertEqual(rows[0]["Zakończenia po I instancji"], 0)
        self.assertEqual(rows[0]["Zakończenia po II instancji"], 0)
        self.assertEqual(rows[0]["Przychód razem"], 0)
        self.assertAlmostEqual(rows[1]["Zakończenia po II instancji"], 1.67)
        self.assertEqual(rows[1]["Przychód razem"], 0)
        unit_revenue = oblicz_model(p)["ogolem"]["przychod"] / 30
        self.assertAlmostEqual(rows[2]["Przychód razem"], 1.67 * unit_revenue)


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
            p = {**domyslne_parametry(), "liczba_pracownikow": staff,
                 "koszt_staly_na_godzine": 1.0, "wynagrodzenie_pracownika_na_godzine": 1.0}
            baseline = oblicz_model_czasowy(p)
            for variant in ("P", "WPS", "ugody", "bez_ugody", "wszystko"):
                def reordered(params):
                    result = oblicz_model(params)
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
                    patch.object(timeline, "oblicz_model", reordered),
                    patch.object(timeline, "SCIEZKI_UGODOWE", settlement_paths),
                    patch.object(timeline, "SCIEZKI_BEZ_UGODY", judgment_paths),
                ):
                    result = oblicz_model_czasowy(p)
                    self.assert_nested_equal(baseline, result)

    def test_wiecej_fte_nie_zwieksza_backlogu_ani_opoznien(self):
        results = [oblicz_model_czasowy({**domyslne_parametry(), "liczba_pracownikow": n}) for n in (1, 2, 3, 10)]
        for lower, higher in zip(results, results[1:]):
            for a, b in zip(lower["tabela_miesieczna"], higher["tabela_miesieczna"]):
                self.assertLessEqual(b["Backlog na koniec (h)"], a["Backlog na koniec (h)"] + 1e-7)
            for key in ("srednie_opoznienie_pojemnosci_miesiace", "maksymalne_opoznienie_pojemnosci_miesiace"):
                self.assertLessEqual(higher["podsumowanie"][key], lower["podsumowanie"][key] + 1e-7)
        self.assertAlmostEqual(results[-1]["podsumowanie"]["backlog_koniec_godziny"], 0)

    def test_obfita_obsada_zachowuje_nominalny_przeplyw(self):
        p = {**domyslne_parametry(), "liczba_pracownikow": 10}
        lifecycle = oblicz_model(p)
        result = oblicz_model_czasowy(p)
        shares = lifecycle["udzialy_ugod"]
        for row in result["tabela_miesieczna"]:
            m = row["Miesiąc"]
            self.assertAlmostEqual(row["Ugody zakończone"], 50 * shares["zakonczone_ugoda"] / 100 if m >= 7 else 0)
            self.assertAlmostEqual(row["Zakończenia po I instancji"], 50 * shares["bez_ugody"] / 200 if m >= 10 else 0)
            self.assertAlmostEqual(row["Zakończenia po II instancji"], 50 * shares["bez_ugody"] / 200 if m >= 16 else 0)
            self.assertAlmostEqual(row["Przychód z ugód"], lifecycle["ogolem"]["przychod_ugody"] / 12 if m >= 7 else 0)
            self.assertAlmostEqual(row["Przychód z wyroków"], lifecycle["ogolem"]["przychod_wyroki"] / 24 * (int(m >= 10) + int(m >= 16)))
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

    def test_kohorta_ma_szesc_sciezek_i_poprawne_etapy_automatyczne(self):
        lifecycle = oblicz_model(self.parametry)
        czas = domyslne_parametry_czasowe()
        pakiety = defaultdict(list)
        zakonczenia = []
        statystyki = _dodaj_kohorte(
            1, lifecycle, self.parametry, czas, pakiety, zakonczenia
        )
        wszystkie_pakiety = [pakiet for lista in pakiety.values() for pakiet in lista]
        bazowe_sciezki = {
            zakonczenie.path.split(":", 1)[0] for zakonczenie in zakonczenia
        }
        self.assertEqual(
            bazowe_sciezki,
            {
                "kategoryczna_odmowa",
                "automatyczne_ramy_ugoda",
                "automatyczne_ramy_brak_ugody",
                "brak_szans",
                "zawarte_poza_ramami",
                "brak_ugody_poza_ramami",
            },
        )
        automatyczne = [
            pakiet
            for pakiet in wszystkie_pakiety
            if pakiet.path.startswith("automatyczne_ramy")
        ]
        self.assertNotIn("analiza_ugody", {pakiet.stage for pakiet in automatyczne})
        nieudane = [
            pakiet
            for pakiet in automatyczne
            if pakiet.stage == "nieudana_proba_ugody"
        ]
        self.assertTrue(nieudane)
        self.assertTrue(
            all(
                pakiet.due_month <= 1 + czas["miesiace_do_wyroku_i"]
                for pakiet in nieudane
            )
        )
        self.assertAlmostEqual(
            statystyki["direct_minutes"],
            lifecycle["bezposrednie_minuty_spraw"] / 12,
        )

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

    def test_pojemnosc_i_pelny_koszt_obsady_skaluja_sie_liniowo(self):
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
            "miesieczny_narzut_kosztow_ogolnych",
            "miesieczny_koszt_wynagrodzen",
        ):
            self.assertAlmostEqual(dwoch[klucz], 2 * jeden[klucz])
        self.assertAlmostEqual(jeden["miesieczny_narzut_kosztow_ogolnych"], 6_012.0)
        self.assertAlmostEqual(jeden["miesieczny_koszt_wynagrodzen"], 9_999.96)
        self.assertAlmostEqual(jeden["miesieczny_koszt_obsady"], 16_011.96)
        self.assertAlmostEqual(dwoch["miesieczny_koszt_obsady"], 32_023.92)
        trzech = oblicz_pojemnosc_miesieczna(
            {**self.parametry, "liczba_pracownikow": 3}
        )
        self.assertAlmostEqual(trzech["miesieczny_koszt_obsady"], 48_035.88)
        dziesieciu = oblicz_pojemnosc_miesieczna(
            {**self.parametry, "liczba_pracownikow": 10}
        )
        self.assertAlmostEqual(dziesieciu["miesieczny_koszt_obsady"], 160_119.60)

    def test_wzor_na_domyslna_pojemnosc_brutto(self):
        pojemnosc = oblicz_pojemnosc_miesieczna(self.parametry)
        self.assertAlmostEqual(
            pojemnosc["pojemnosc_brutto_minuty"], 2 * 167 * 60
        )
        self.assertAlmostEqual(pojemnosc["pojemnosc_brutto_minuty"], 20_040)

    def test_90_minut_dziennie_jest_wewnatrz_167_godzin(self):
        pojemnosc = oblicz_pojemnosc_miesieczna(
            {**self.parametry, "liczba_pracownikow": 1}
        )
        self.assertAlmostEqual(pojemnosc["ekwiwalent_dni_pracy_miesiecznie"], 20.875)
        self.assertAlmostEqual(
            pojemnosc["czynnosci_dzienne_na_pracownika_godziny"], 31.3125
        )
        self.assertAlmostEqual(pojemnosc["pojemnosc_na_sprawy_minuty"] / 60, 135.6875)

    def test_brak_pracy_bezposredniej_nie_usuwa_kosztu_zespolu(self):
        wynik = oblicz_model_czasowy({**self.parametry, "liczba_spraw": 0})
        wiersz = wynik["tabela_miesieczna"][0]
        self.assertEqual(wiersz["Wykonana praca (h)"], 0.0)
        self.assertAlmostEqual(
            wiersz["Niewykorzystana pojemność (h)"],
            wiersz["Pojemność brutto (h)"] - wiersz["Czynności dzienne (h)"],
        )
        self.assertGreater(wiersz["Miesięczny koszt obsady"], 0.0)
        self.assertEqual(
            wiersz["Wynik miesięczny przed podatkiem"],
            -wiersz["Miesięczny koszt obsady"],
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
            normalne["pojemnosc"]["miesieczny_koszt_obsady"],
            bez_dziennych["pojemnosc"]["miesieczny_koszt_obsady"],
        )

    def test_koszt_zespolu_nie_odejmuje_ponownie_niewykorzystania(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 10},
            {"horyzont_miesiace": 12},
        )
        for wiersz in wynik["tabela_miesieczna"]:
            self.assertAlmostEqual(
                wiersz["Wynik miesięczny przed podatkiem"],
                wiersz["Przychód razem"] - wiersz["Miesięczny koszt obsady"],
            )

    def test_koszt_niewykorzystanej_pojemnosci_uzywa_pelnej_stawki_zasobu(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 10},
            {"horyzont_miesiace": 12},
        )
        for wiersz in wynik["tabela_miesieczna"]:
            self.assertAlmostEqual(
                wiersz["Koszt niewykorzystanej pojemności"],
                wiersz["Niewykorzystana pojemność (h)"]
                * (
                    self.parametry["koszt_staly_na_godzine"]
                    + self.parametry["wynagrodzenie_pracownika_na_godzine"]
                ),
            )

    def test_czynnosci_dzienne_moga_wyczerpac_cala_pojemnosc(self):
        parametry = {
            **self.parametry,
            "codzienne_czynnosci": {"Czynności dzienne": MINUTY_DNIA_PRACY},
        }
        with self.assertRaisesRegex(ValueError, "cały dzień"):
            oblicz_model_czasowy(parametry, {"horyzont_miesiace": 12})

        bez_spraw = oblicz_pojemnosc_miesieczna(
            {**parametry, "liczba_spraw": 0, "liczba_pracownikow": 1}
        )
        self.assertEqual(bez_spraw["pojemnosc_na_sprawy_minuty"], 0.0)
        self.assertTrue(bez_spraw["brak_pojemnosci_na_sprawy"])
        self.assertAlmostEqual(bez_spraw["miesieczny_koszt_obsady"], 16_011.96)

    def test_lifecycle_i_timeline_maja_wspolna_fizyke_pojemnosci(self):
        lifecycle = oblicz_model(self.parametry)
        pojemnosc = oblicz_pojemnosc_miesieczna(
            {**self.parametry, "liczba_pracownikow": 1}, lifecycle
        )
        dzienne = sum(self.parametry["codzienne_czynnosci"].values())
        self.assertAlmostEqual(
            pojemnosc["pojemnosc_na_sprawy_minuty"] * 12,
            GODZINY_ETATU_MIESIECZNIE
            * 12
            * 60
            * (MINUTY_DNIA_PRACY - dzienne)
            / MINUTY_DNIA_PRACY,
        )
        self.assertAlmostEqual(
            lifecycle["laczne_minuty_zasobu_lifecycle"],
            lifecycle["bezposrednie_minuty_spraw"]
            * MINUTY_DNIA_PRACY
            / (MINUTY_DNIA_PRACY - dzienne),
        )

    def test_twardy_limit_167_godzin_i_backlog(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 1},
            {"horyzont_miesiace": 24},
        )
        for wiersz in wynik["tabela_miesieczna"]:
            self.assertLessEqual(
                wiersz["Wykorzystane płatne godziny"], 167.0 + 1e-9
            )
            self.assertLessEqual(
                wiersz["Wykonana praca (h)"], 135.6875 + 1e-9
            )
        self.assertGreater(wynik["podsumowanie"]["backlog_koniec_godziny"], 0.0)

    def test_10_godzin_pracy_nadal_kosztuje_pelny_fte(self):
        parametry = {
            **self.parametry,
            "liczba_spraw": 60,
            "liczba_pracownikow": 1,
            "wspolne_czynnosci": {"Praca": 120},
            "procesowe_czynnosci": {},
            "ugodowe_czynnosci": {},
            "analiza_mozliwosci_ugody": 0,
            "codzienne_czynnosci": {},
            "dodatkowe_minuty": {"P1": 0, "P2": 0, "P3": 0},
            "kategoryczna_odmowa_percent": 0.0,
            "automatyczne_ramy_percent": 100.0,
            "udzial_ii_instancji_percent": 0.0,
            "obsluga_ii_instancji_minuty": 0,
        }
        wynik = oblicz_model_czasowy(parametry, {"horyzont_miesiace": 12})
        pierwszy = wynik["tabela_miesieczna"][0]
        self.assertAlmostEqual(pierwszy["Wykonana praca (h)"], 10.0)
        self.assertAlmostEqual(pierwszy["Miesięczny koszt obsady"], 16_011.96)
        self.assertAlmostEqual(pierwszy["Niewykorzystana pojemność (h)"], 157.0)


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
            pieciu["pojemnosc"]["miesieczny_koszt_obsady"],
            jeden["pojemnosc"]["miesieczny_koszt_obsady"],
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
        self.assertEqual(niedobor["kpi"]["break_even_status"], "brak_pojemnosci")
        self.assertEqual(niedobor["kpi"]["pierwsze_przeciecie_status"], "osiagniety")
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
            "liczba_pracownikow": 10,
            "wynagrodzenie_pracownika_na_godzine": 59.88,
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
        self.assertEqual(
            temporal["kpi"]["status_break_even"],
            "Brak trwałego break-even przy obecnej ekonomice",
        )
        self.assertTrue(temporal["kpi"]["wynik_nadal_narasta"])
        short = oblicz_model_czasowy(tanio, {"horyzont_miesiace": 12})
        self.assertIsNone(short["kpi"]["wynik_miesieczny_w_stanie_stabilnym"])
        self.assertLess(short["kpi"]["wynik_miesieczny_biezacej_obsady"], 0)
        self.assertTrue(short["kpi"]["wynik_nadal_narasta"])

    def test_strata_rozruchowa_nie_oznacza_trwalego_spadku(self):
        parametry = {
            **self.parametry,
            "liczba_pracownikow": 3,
            "koszt_staly_na_godzine": 20.0,
            "wynagrodzenie_pracownika_na_godzine": 20.0,
        }
        short = oblicz_model_czasowy(parametry, {"horyzont_miesiace": 12})
        self.assertEqual(short["kpi"]["status_kontraktu"], "Rentowny i stabilny")
        self.assertGreater(short["kpi"]["wynik_miesieczny_biezacej_obsady"], 0)
        self.assertLess(short["kpi"]["wynik_skumulowany_na_koniec_horyzontu"], 0)
        self.assertLess(short["kpi"]["trend_miesieczny_wyniku"], 0)
        self.assertIsNone(short["kpi"]["wynik_miesieczny_w_stanie_stabilnym"])
        self.assertFalse(short["kpi"]["wynik_nadal_narasta"])

        mature = oblicz_model_czasowy(parametry, {"horyzont_miesiace": 60})
        self.assertEqual(mature["kpi"]["status_kontraktu"], "Rentowny i stabilny")
        self.assertGreater(mature["kpi"]["wynik_miesieczny_w_stanie_stabilnym"], 0)
        self.assertGreater(mature["kpi"]["wynik_skumulowany_na_koniec_horyzontu"], 0)
        self.assertFalse(mature["kpi"]["wynik_nadal_narasta"])

    def test_niedobor_obsady_nie_dowodzi_trwalego_spadku(self):
        for horizon in (12, 60):
            result = oblicz_model_czasowy(self.parametry, {"horyzont_miesiace": horizon})
            self.assertEqual(result["pojemnosc"]["status_pojemnosci"], "Niewystarczająca")
            self.assertIsNone(result["kpi"]["wynik_miesieczny_biezacej_obsady"])
            self.assertLess(result["kpi"]["trend_miesieczny_wyniku"], 0)
            self.assertFalse(result["kpi"]["wynik_nadal_narasta"])

    def test_zerowa_dojrzala_ekonomika_nie_jest_trwalym_spadkiem(self):
        parametry = {**self.parametry, "liczba_pracownikow": 3, "koszt_staly_na_godzine": 0.0}
        parametry["wynagrodzenie_pracownika_na_godzine"] = (
            oblicz_model(parametry)["ogolem"]["przychod"] / 12
            / (parametry["liczba_pracownikow"] * GODZINY_ETATU_MIESIECZNIE)
        )
        result = oblicz_model_czasowy(parametry, {"horyzont_miesiace": 12})
        self.assertEqual(result["pojemnosc"]["status_pojemnosci"], "Stabilna")
        self.assertAlmostEqual(result["kpi"]["wynik_miesieczny_biezacej_obsady"], 0)
        self.assertFalse(result["kpi"]["wynik_nadal_narasta"])

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
        wymagane = {
            "Liczba pracowników",
            "Pojemność brutto (h/mies.)",
            "Pojemność na sprawy (h/mies.)",
            "Miesięczny narzut kosztów ogólnych",
            "Miesięczne wynagrodzenia",
            "Miesięczny koszt obsady",
            "Wykorzystanie",
            "Backlog (h)",
            "Break-even",
            "Dojrzały wynik miesięczny",
        }
        self.assertTrue(wymagane.issubset(rows[0]))
        self.assertAlmostEqual(rows[1]["Miesięczny koszt obsady"], 32_023.92)

    def test_roznica_kosztow_to_wylacznie_niewykorzystana_praca(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 3},
            {"horyzont_miesiace": 120},
        )
        diagnoza = wynik["diagnoza"]
        self.assertGreater(diagnoza["bilans_pojemnosci_rocznie_godziny"], 0)
        self.assertAlmostEqual(
            diagnoza["roznica_kosztu_czasowy_minus_lifecycle"],
            diagnoza["bilans_pojemnosci_rocznie_godziny"]
            * (
                self.parametry["koszt_staly_na_godzine"]
                + self.parametry["wynagrodzenie_pracownika_na_godzine"]
            ),
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


class TestStatusKontraktu(unittest.TestCase):
    def test_wynik_biezacej_obsady_wymaga_wystarczajacej_pojemnosci(self):
        for obsada in (1, 2, 3, 10):
            with self.subTest(obsada=obsada):
                wynik = oblicz_model_czasowy({**domyslne_parametry(), "liczba_pracownikow": obsada})
                kpi = wynik["kpi"]
                self.assertNotIn("wynik_miesieczny_docelowy", kpi)
                current = kpi["wynik_miesieczny_biezacej_obsady"]
                self.assertEqual(current, kpi["status_kontraktu_skladniki"]["wynik_miesieczny_biezacej_obsady"])
                if obsada < wynik["pojemnosc"]["minimalna_liczba_pracownikow_dla_stabilnosci"]:
                    self.assertIsNone(current)
                else:
                    self.assertAlmostEqual(
                        current,
                        oblicz_model(domyslne_parametry())["ogolem"]["przychod"] / 12
                        - wynik["pojemnosc"]["miesieczny_koszt_obsady"],
                    )
                self.assertEqual(kpi["status_kontraktu"], "Nierentowna ekonomika sprawy")

    def test_klasyfikator_nie_ujawnia_hipotetycznego_wyniku_malej_obsady(self):
        for obsada, status in ((1, "Stabilna"), (2, "Niewystarczająca")):
            wynik = klasyfikuj_status_kontraktu(600, 10, obsada, 2, 100, 1000, status)
            self.assertIsNone(wynik["wynik_miesieczny_biezacej_obsady"])
        wynik = klasyfikuj_status_kontraktu(600, 10, 2, 2, 100, 100, "Na granicy")
        self.assertEqual(wynik["wynik_miesieczny_biezacej_obsady"], 100)

    def test_parametry_czasowe_pochodza_z_toml_i_sa_izolowane(self):
        from config import wczytaj_defaults
        oczekiwane = wczytaj_defaults()["timeline"]
        pierwsze = domyslne_parametry_czasowe()
        self.assertEqual(pierwsze, oczekiwane)
        pierwsze["horyzont_miesiace"] = -1
        self.assertEqual(domyslne_parametry_czasowe(), oczekiwane)

    def test_statusy_wynikaja_z_jawnych_przeslanek(self):
        przypadki = (
            (
                (600.0, -1.0, 3, 2, 100.0, 100.0, "Stabilna"),
                "Nierentowna ekonomika sprawy",
            ),
            (
                (600.0, 10.0, 3, 2, -1.0, 100.0, "Stabilna"),
                "Brak rentownej stabilnej obsady",
            ),
            (
                (600.0, 10.0, 1, 2, 100.0, 100.0, "Niewystarczająca"),
                "Rentowny, wymaga większej obsady",
            ),
            (
                (600.0, 10.0, 2, 2, 100.0, 100.0, "Stabilna"),
                "Rentowny i stabilny",
            ),
            (
                (600.0, 10.0, 3, 2, 100.0, -1.0, "Stabilna"),
                "Stabilny, ale obsada zbyt kosztowna",
            ),
            (
                (0.0, -1.0, 3, None, None, -1.0, "Stabilna"),
                "Brak napływu spraw",
            ),
        )
        for argumenty, oczekiwany in przypadki:
            with self.subTest(oczekiwany=oczekiwany):
                self.assertEqual(
                    klasyfikuj_status_kontraktu(*argumenty)["etykieta"],
                    oczekiwany,
                )

    def test_surowy_break_even_pozostaje_widoczny_przy_braku_pojemnosci(self):
        parametry = {
            **domyslne_parametry(),
            "koszt_staly_na_godzine": 1.0,
            "wynagrodzenie_pracownika_na_godzine": 1.0,
            "liczba_pracownikow": 1,
        }
        wynik = oblicz_model_czasowy(parametry)
        self.assertEqual(wynik["pojemnosc"]["status_pojemnosci"], "Niewystarczająca")
        self.assertEqual(wynik["kpi"]["pierwsze_przeciecie_status"], "osiagniety")
        self.assertIsNotNone(wynik["kpi"]["pierwsze_przeciecie_miesiac"])
        self.assertEqual(
            wynik["kpi"]["status_kontraktu"],
            "Rentowny, wymaga większej obsady",
        )


class TestDojrzaloscAktywnychSciezek(unittest.TestCase):
    def setUp(self):
        self.parametry = {
            **domyslne_parametry(),
            "liczba_pracownikow": 3,
            "koszt_staly_na_godzine": 20.0,
            "wynagrodzenie_pracownika_na_godzine": 20.0,
            "udzial_ii_instancji_percent": 0.0,
        }

    def assert_roczne_uzgodnienie(self, wynik, parametry):
        lifecycle = oblicz_model(parametry)
        rows = wynik["tabela_miesieczna"][-12:]
        self.assertTrue(wynik["podsumowanie"]["dojrzalosc_osiagnieta"])
        self.assertAlmostEqual(sum(
            row["Ugody zakończone"] + row["Zakończenia po I instancji"]
            + row["Zakończenia po II instancji"] for row in rows
        ), parametry["liczba_spraw"])
        self.assertAlmostEqual(sum(row["Przychód razem"] for row in rows), lifecycle["ogolem"]["przychod"])
        self.assertAlmostEqual(sum(row["Nowa praca (h)"] * 60 for row in rows), lifecycle["bezposrednie_minuty_spraw"])
        self.assertTrue(all(abs(row["Backlog na koniec (h)"]) < 1e-8 for row in rows))

    def test_zero_ii_potwierdza_dojrzalosc_i_break_even_w_miesiacu_17(self):
        wynik = oblicz_model_czasowy(self.parametry, {"horyzont_miesiace": 24})
        self.assert_roczne_uzgodnienie(wynik, self.parametry)
        self.assertEqual(wynik["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 10)
        self.assertAlmostEqual(wynik["kpi"]["wynik_miesieczny_w_stanie_stabilnym"], 17623.6045)
        self.assertEqual(wynik["kpi"]["break_even_status"], "osiagniety")
        self.assertEqual(wynik["kpi"]["break_even_miesiac"], 17)
        self.assertEqual(wynik["kpi"]["status_break_even"], "Break-even trwały")

    def test_same_ii_respektuja_termin_ii_i_pelny_rok(self):
        parametry = {**self.parametry, "udzial_ii_instancji_percent": 100.0, "liczba_pracownikow": 10}
        short = oblicz_model_czasowy(parametry, {"horyzont_miesiace": 26})
        self.assertEqual(short["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 16)
        self.assertFalse(short["podsumowanie"]["dojrzalosc_osiagnieta"])
        mature = oblicz_model_czasowy(parametry, {"horyzont_miesiace": 27})
        self.assert_roczne_uzgodnienie(mature, parametry)
        self.assertTrue(all(row["Zakończenia po I instancji"] == 0 for row in mature["tabela_miesieczna"]))
        self.assertEqual(pierwszy_miesiac_z_wartoscia(mature["tabela_miesieczna"], "Zakończenia po II instancji"), 16)

    def test_zero_ugod_pomija_ich_termin(self):
        parametry = {**self.parametry, "automatyczne_ramy_percent": 0.0,
                     "zawarte_ugody_percent": 0.0, "liczba_pracownikow": 10}
        for settlement_lag in (0, 100):
            with self.subTest(settlement_lag=settlement_lag):
                czas = {"miesiace_do_ugody": settlement_lag, "horyzont_miesiace": 21}
                wynik = oblicz_model_czasowy(parametry, czas)
                self.assertEqual(wynik["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 10)
                self.assert_roczne_uzgodnienie(wynik, parametry)
                short = oblicz_model_czasowy(parametry, {**czas, "horyzont_miesiace": 20})
                self.assertFalse(short["podsumowanie"]["dojrzalosc_osiagnieta"])

    def test_same_ugody_pomijaja_obydwa_terminy_wyrokow(self):
        parametry = {**self.parametry, "kategoryczna_odmowa_percent": 0.0,
                     "automatyczne_ramy_percent": 100.0,
                     "skutecznosc_automatycznych_ram_percent": 100.0,
                     "udzial_ii_instancji_percent": 100.0, "liczba_pracownikow": 10}
        czas = {"miesiace_do_wyroku_i": 100, "miesiace_wyrok_i_do_ii": 100,
                "horyzont_miesiace": 18}
        wynik = oblicz_model_czasowy(parametry, czas)
        self.assertEqual(wynik["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 7)
        self.assert_roczne_uzgodnienie(wynik, parametry)
        short = oblicz_model_czasowy(parametry, {**czas, "horyzont_miesiace": 17})
        self.assertFalse(short["podsumowanie"]["dojrzalosc_osiagnieta"])

    def test_platnosc_opoznia_dojrzalosc_przychodu_ale_nie_prace(self):
        czas = {"opoznienie_platnosci_miesiace": 4, "horyzont_miesiace": 25}
        delayed = oblicz_model_czasowy(self.parametry, czas)
        self.assertEqual(delayed["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 14)
        self.assert_roczne_uzgodnienie(delayed, self.parametry)
        short = oblicz_model_czasowy(self.parametry, {**czas, "horyzont_miesiace": 24})
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
            oblicz_model(parametry), domyslne_parametry_czasowe()
        ), 10)

    def test_poprawny_termin_nie_zastepuje_wystarczajacej_pojemnosci(self):
        wynik = oblicz_model_czasowy({**self.parametry, "liczba_pracownikow": 1}, {"horyzont_miesiace": 24})
        self.assertEqual(wynik["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 10)
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
                == -w["Miesięczny koszt obsady"]
                for w in wynik["tabela_miesieczna"]
            )
        )

    def test_zero_pracownikow(self):
        wynik = oblicz_model_czasowy(
            {**self.parametry, "liczba_pracownikow": 0},
            {"horyzont_miesiace": 24},
        )
        self.assertEqual(wynik["pojemnosc"]["pojemnosc_brutto_minuty"], 0.0)
        self.assertEqual(wynik["pojemnosc"]["miesieczny_koszt_wynagrodzen"], 0.0)
        self.assertEqual(wynik["pojemnosc"]["miesieczny_narzut_kosztow_ogolnych"], 0.0)
        self.assertEqual(wynik["pojemnosc"]["miesieczny_koszt_obsady"], 0.0)
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
                "skutecznosc_automatycznych_ram_percent": 100.0,
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
