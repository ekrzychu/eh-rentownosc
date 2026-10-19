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
    Completion,
    GODZINY_ETATU_MIESIECZNIE,
    _dodaj_kohorte,
    _dodaj_pakiet,
    _nominalny_miesiac_dojrzalosci,
    _przyrost_zakonczenia,
    _wykonaj_prace,
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
    def zbuduj_kohorte(self, parametry=None, **czasy):
        parametry = domyslne_parametry() if parametry is None else parametry
        lifecycle = oblicz_przeplyw(parametry)
        pakiety, zakonczenia = defaultdict(list), []
        statystyki = _dodaj_kohorte(
            5, lifecycle, parametry,
            {**domyslne_parametry_czasowe(), **czasy}, pakiety, zakonczenia,
        )
        self.assertAlmostEqual(statystyki["direct_minutes"], lifecycle["bezposrednie_minuty_spraw"] / 12)
        self.assertAlmostEqual(statystyki["revenue"], lifecycle["ogolem"]["przychod"] / 12)
        return [p for lista in pakiety.values() for p in lista], zakonczenia

    def test_proces_od_razu_niezaleznie_od_terminu_wyroku(self):
        for lag in (9, 20):
            with self.subTest(lag=lag):
                pakiety, _ = self.zbuduj_kohorte(miesiace_do_wyroku_i=lag)
                proces = [p for p in pakiety if p.stage == "proces"]
                self.assertTrue(proces)
                self.assertEqual({p.due_month for p in proces}, {5})
                self.assertAlmostEqual(sum(p.minutes_remaining for p in proces), 50 * .7125 * 250)

    def test_caly_czas_p_od_razu_dla_kazdej_sciezki(self):
        for lag in (6, 60):
            with self.subTest(lag=lag):
                pakiety, zakonczenia = self.zbuduj_kohorte(
                    miesiace_do_ugody=lag, miesiace_do_wyroku_i=lag,
                    miesiace_wyrok_i_do_ii=lag,
                )
                dodatkowe = [p for p in pakiety if p.stage == "praca_dodatkowa_p"]
                self.assertEqual({p.due_month for p in dodatkowe}, {5})
                self.assertEqual({p.completion_id for p in dodatkowe}, set(range(len(zakonczenia))))
                self.assertAlmostEqual(sum(p.minutes_remaining for p in dodatkowe), 50 * 150.3)

    def test_caly_pakiet_ugodowy_od_razu_nawet_przy_dlugim_terminie(self):
        for lag in (6, 60):
            with self.subTest(lag=lag):
                pakiety, _ = self.zbuduj_kohorte(miesiace_do_ugody=lag)
                ugody = [p for p in pakiety if p.stage == "zawarcie_ugody"]
                self.assertEqual({p.due_month for p in ugody}, {5})
                self.assertAlmostEqual(sum(p.minutes_remaining for p in ugody), 50 * .2875 * (15 + 20 + 20))

    def test_nieudane_proby_i_analiza_od_razu(self):
        pakiety, _ = self.zbuduj_kohorte(miesiace_do_ugody=60, miesiace_do_wyroku_i=20)
        proby = [p for p in pakiety if p.stage == "nieudana_proba_ugody"]
        self.assertEqual({p.due_month for p in proby}, {5})
        self.assertAlmostEqual(sum(p.minutes_remaining for p in proby), 50 * (.15 + .1375) * 35)
        self.assertEqual({p.due_month for p in pakiety if p.stage in {"przyjecie", "analiza_ugody"}}, {5})

    def test_oczekiwanie_nie_dodaje_pracy_ani_kosztu(self):
        p = {**domyslne_parametry(), "pracownicy": [nowy_pracownik(i) for i in range(10)], "udzial_ii_instancji_percent": 0.0}
        krotko = oblicz_model_czasowy(p, {"horyzont_miesiace": 72})
        dlugo = oblicz_model_czasowy(p, {"miesiace_do_ugody": 60, "miesiace_do_wyroku_i": 60, "horyzont_miesiace": 72})
        miesieczna_praca = oblicz_przeplyw(p)["bezposrednie_minuty_spraw"] / 12
        for a, b in zip(krotko["tabela_miesieczna"], dlugo["tabela_miesieczna"]):
            for key in ("Nowa praca (h)", "Wykonana praca (h)", "Backlog na koniec (h)", "Łączny koszt miesięczny"):
                self.assertAlmostEqual(a[key], b[key])
            self.assertAlmostEqual(b["Nowa praca (h)"] * 60, miesieczna_praca)
        self.assertGreater(dlugo["tabela_miesieczna"][0]["Aktywne sprawy"], 0)
        self.assertEqual(dlugo["tabela_miesieczna"][0]["Przychód razem"], 0)

    def test_ii_caly_pakiet_przy_wyroku_i_niezaleznie_od_odstepu_do_ii(self):
        for lag in (0, 6, 60):
            with self.subTest(lag=lag):
                pakiety, _ = self.zbuduj_kohorte(miesiace_do_wyroku_i=9, miesiace_wyrok_i_do_ii=lag)
                ii = [p for p in pakiety if p.stage == "ii_instancja"]
                self.assertEqual({p.due_month for p in ii}, {14})
                self.assertAlmostEqual(sum(p.minutes_remaining for p in ii), 50 * .35625 * 210)
                self.assertEqual({p.due_month for p in pakiety if p.stage != "ii_instancja"}, {5})

    def test_wczesna_praca_nie_przyspiesza_zakonczenia_i_przychodu(self):
        bazowe = {**domyslne_parametry(), "pracownicy": [nowy_pracownik(i) for i in range(10)]}
        warianty = (
            ("ugoda", {"kategoryczna_odmowa_percent": 0.0, "automatyczne_ramy_percent": 100.0, "skutecznosc_automatycznych_ram_percent": 100.0}, "Ugody zakończone", 7),
            ("i", {"kategoryczna_odmowa_percent": 100.0, "automatyczne_ramy_percent": 0.0, "udzial_ii_instancji_percent": 0.0}, "Zakończenia po I instancji", 10),
            ("ii", {"kategoryczna_odmowa_percent": 100.0, "automatyczne_ramy_percent": 0.0, "udzial_ii_instancji_percent": 100.0}, "Zakończenia po II instancji", 16),
        )
        for nazwa, zmiany, kolumna, nominalny in warianty:
            with self.subTest(sciezka=nazwa):
                p = {**bazowe, **zmiany}
                wynik = oblicz_model_czasowy(p, {"horyzont_miesiace": nominalny + 2, "opoznienie_platnosci_miesiace": 2})
                rows = wynik["tabela_miesieczna"]
                pakiety, _ = self.zbuduj_kohorte(p)
                pre_i = sum(x.minutes_remaining for x in pakiety if x.stage != "ii_instancja")
                self.assertAlmostEqual(rows[0]["Wykonana praca (h)"], pre_i / 60)
                self.assertEqual(rows[0]["Backlog na koniec (h)"], 0)
                for row in rows[:nominalny - 1]:
                    self.assertEqual(row[kolumna], 0)
                    self.assertAlmostEqual(row["Aktywne sprawy"], 50 * row["Miesiąc"])
                self.assertEqual(pierwszy_miesiac_z_wartoscia(rows, kolumna), nominalny)
                self.assertEqual(pierwszy_miesiac_z_wartoscia(rows, "Przychód razem"), nominalny + 2)
                if nazwa == "ii":
                    self.assertEqual(rows[9]["Zakończenia po I instancji"], 0)

    def test_dojrzalosc_i_roczne_uzgodnienie_przy_dlugich_terminach(self):
        p = {**domyslne_parametry(), "pracownicy": [nowy_pracownik(i) for i in range(10)]}
        czas = {"miesiace_do_ugody": 60, "miesiace_do_wyroku_i": 20, "miesiace_wyrok_i_do_ii": 45}
        short = oblicz_model_czasowy(p, {**czas, "horyzont_miesiace": 76})
        self.assertFalse(short["podsumowanie"]["dojrzalosc_osiagnieta"])
        wynik = oblicz_model_czasowy(p, {**czas, "horyzont_miesiace": 77})
        self.assertEqual(wynik["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 66)
        self.assertTrue(wynik["podsumowanie"]["dojrzalosc_osiagnieta"])
        last = wynik["tabela_miesieczna"][-12:]
        self.assertAlmostEqual(sum(row[key] for row in last for key in ("Ugody zakończone", "Zakończenia po I instancji", "Zakończenia po II instancji")), 600)
        lifecycle = oblicz_przeplyw(p)
        self.assertAlmostEqual(sum(row["Nowa praca (h)"] * 60 for row in last), lifecycle["bezposrednie_minuty_spraw"])
        self.assertAlmostEqual(sum(row["Przychód razem"] for row in last), lifecycle["ogolem"]["przychod"])


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

    def test_kazdy_etap_rejestruje_caly_pakiet_w_odpowiednim_miesiacu(self):
        p = domyslne_parametry()
        packets, completions = defaultdict(list), []
        _dodaj_kohorte(1, oblicz_przeplyw(p), p, domyslne_parametry_czasowe(), packets, completions)
        for i, c in enumerate(completions):
            for stage, total in c.stage_total_minutes.items():
                stage_packets = [packet for bucket in packets.values() for packet in bucket
                                 if packet.completion_id == i and packet.stage == stage]
                self.assertEqual(len(stage_packets), 1)
                self.assertEqual(stage_packets[0].due_month, 10 if stage == "ii_instancja" else 1)
                self.assertAlmostEqual(total, stage_packets[0].minutes_remaining)
        self.assertTrue(any(c.outcome == "ii" and "ii_instancja" in c.stage_total_minutes for c in completions))

    def test_czesc_agregatu_zamyka_sie_z_proporcjonalnym_przychodem(self):
        p = parametry_jednej_sciezki()
        result = oblicz_model_czasowy(p, {"miesiace_do_ugody": 0, "horyzont_miesiace": 2}, pracownicy=[osoba("UGODY")])
        first, second = result["tabela_miesieczna"]
        self.assertAlmostEqual(first["Wykonana praca (h)"], 167)
        self.assertAlmostEqual(first["Ugody zakończone"], 1.67)
        unit_revenue = oblicz_przeplyw(p)["ogolem"]["przychod"] / 30
        self.assertAlmostEqual(first["Przychód z ugód"], 1.67 * unit_revenue)
        self.assertAlmostEqual(second["Ugody zakończone"], 1.67)
        self.assertAlmostEqual(first["Aktywne sprawy"], .83)
        self.assertAlmostEqual(result["podsumowanie"]["srednie_opoznienie_pojemnosci_miesiace"], .83 / 3.34)
        self.assertEqual(result["podsumowanie"]["maksymalne_opoznienie_pojemnosci_miesiace"], 1)

    def test_opoznienie_platnosci_przesuwa_osobno_kazdy_przyrost(self):
        p = parametry_jednej_sciezki()
        time = {"miesiace_do_ugody": 0, "horyzont_miesiace": 5}
        direct = oblicz_model_czasowy(p, time, pracownicy=[osoba("UGODY")])["tabela_miesieczna"]
        delayed = oblicz_model_czasowy(p, {**time, "opoznienie_platnosci_miesiace": 2}, pracownicy=[osoba("UGODY")])["tabela_miesieczna"]
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
        self.assertAlmostEqual(rows[0]["Wykonana praca (h)"], 167)
        self.assertAlmostEqual(rows[1]["Zakończenia po II instancji"], 2.5)
        self.assertEqual(rows[1]["Przychód razem"], 0)
        unit_revenue = oblicz_przeplyw(p)["ogolem"]["przychod"] / 30
        self.assertAlmostEqual(rows[2]["Przychód razem"], 2.5 * unit_revenue)


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
                self.assertLessEqual(b["Backlog na koniec (h)"], a["Backlog na koniec (h)"] + 1e-7)
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

    def test_kohorta_ma_szesc_sciezek_i_poprawne_etapy_automatyczne(self):
        lifecycle = oblicz_przeplyw(self.parametry)
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
                pakiet.due_month == 1
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
        self.assertEqual(wynik["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 10)
        self.assertAlmostEqual(wynik["kpi"]["wynik_miesieczny_w_stanie_stabilnym"], 24303.6045)
        self.assertEqual(wynik["kpi"]["break_even_status"], "osiagniety")
        self.assertEqual(wynik["kpi"]["break_even_miesiac"], 12)
        self.assertEqual(wynik["kpi"]["status_break_even"], "Break-even trwały")

    def test_same_ii_respektuja_termin_ii_i_pelny_rok(self):
        parametry = {**self.parametry, "udzial_ii_instancji_percent": 100.0, "pracownicy": [nowy_pracownik(i) for i in range(10)]}
        short = oblicz_model_czasowy(parametry, {"horyzont_miesiace": 26})
        self.assertEqual(short["podsumowanie"]["nominalny_miesiac_dojrzalosci"], 16)
        self.assertFalse(short["podsumowanie"]["dojrzalosc_osiagnieta"])
        mature = oblicz_model_czasowy(parametry, {"horyzont_miesiace": 27})
        self.assert_roczne_uzgodnienie(mature, parametry)
        self.assertTrue(all(row["Zakończenia po I instancji"] == 0 for row in mature["tabela_miesieczna"]))
        self.assertEqual(pierwszy_miesiac_z_wartoscia(mature["tabela_miesieczna"], "Zakończenia po II instancji"), 16)

    def test_zero_ugod_pomija_ich_termin(self):
        parametry = {**self.parametry, "automatyczne_ramy_percent": 0.0,
                     "zawarte_ugody_percent": 0.0, "pracownicy": [nowy_pracownik(i) for i in range(10)]}
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
                     "udzial_ii_instancji_percent": 100.0, "pracownicy": [nowy_pracownik(i) for i in range(10)]}
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
            oblicz_przeplyw(parametry), domyslne_parametry_czasowe()
        ), 10)

    def test_poprawny_termin_nie_zastepuje_wystarczajacej_pojemnosci(self):
        wynik = oblicz_model_czasowy({**self.parametry, "pracownicy": [nowy_pracownik(i) for i in range(1)]}, {"horyzont_miesiace": 24})
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
        self.costs = {"ogolne_na_aktywna_sprawe": 43.0, "sekretariat_na_aktywna_sprawe": 7.0}

    def licz(self, p=None, czas=None, roster=None, costs=None):
        return oblicz_model_czasowy(p or self.p, czas, pracownicy=self.roster if roster is None else roster,
                                    koszty_kontraktu=self.costs if costs is None else costs)

    def test_A_godzinowy_narzut_nie_zmienia_kontraktu(self):
        self.assertEqual(self.licz()["tabela_miesieczna"], self.licz({**self.p, "koszt_staly_na_godzine": 999.0})["tabela_miesieczna"])

    def test_B_koszty_kontraktu_nie_zmieniaja_ekonomiki(self):
        przed = oblicz_model(self.p)
        self.licz(costs={"ogolne_na_aktywna_sprawe": 9999.0})
        self.assertEqual(przed, oblicz_model(self.p))
        # Panel 1 ignoruje również dołączone ustawienia kosztów i obsady.
        self.assertEqual(przed, oblicz_model({**self.p, "koszty_kontraktu": self.costs,
                                             "liczba_pracownikow": 0}))

    def test_D_sekretariat_nie_zuzywa_pojemnosci(self):
        zmiana = {**self.p, "sekretariat_minuty_na_sprawe": 10000.0, "koszt_sekretariatu_na_godzine": 50.0}
        self.assertEqual(self.licz()["pojemnosc"], self.licz(zmiana)["pojemnosc"])

    def test_E_stawka_sekretariatu_jest_niezalezna(self):
        zmiana = {**self.p, "koszt_sekretariatu_na_godzine": 500.0, "sekretariat_minuty_na_sprawe": 10.0,
                  }
        self.assertEqual(self.licz()["tabela_miesieczna"], self.licz(zmiana)["tabela_miesieczna"])

    def test_F_50_razy_43(self):
        pierwszy = self.licz()["tabela_miesieczna"][0]
        self.assertEqual(pierwszy["Sprawy naliczające koszt w miesiącu"], 50)
        self.assertEqual(pierwszy["Koszty ogólne aktywnych spraw"], 2150)
        self.assertEqual(pierwszy["Koszt sekretariatu aktywnych spraw"], 350)

    def test_GHI_naliczanie_od_wplywu_do_zakonczenia_wlacznie(self):
        p = {**self.p, "liczba_spraw": 12, "kategoryczna_odmowa_percent": 0.0,
             "automatyczne_ramy_percent": 100.0, "skutecznosc_automatycznych_ram_percent": 100.0}
        rows = self.licz(p, {"miesiace_do_ugody": 2, "horyzont_miesiace": 6})["tabela_miesieczna"]
        # Jedna nowa sprawa na miesiąc: pierwsza jest obciążana w 1, 2 i 3.
        self.assertEqual([r["Sprawy naliczające koszt w miesiącu"] for r in rows], [1, 2, 3, 3, 3, 3])
        self.assertEqual([r["Aktywne sprawy na koniec miesiąca"] for r in rows], [1, 2, 2, 2, 2, 2])
        # Od miesiąca 4 pierwsza sprawa nie nalicza kosztu; zastępuje ją nowy wpływ.
        self.assertEqual([r["Koszty ogólne aktywnych spraw"] for r in rows], [43, 86, 129, 129, 129, 129])

    def test_GH_nawet_natychmiastowe_zakonczenie_kosztuje_jeden_miesiac(self):
        czas = {"miesiace_do_ugody": 0, "miesiace_do_wyroku_i": 0, "miesiace_wyrok_i_do_ii": 0}
        for r in self.licz(czas=czas)["tabela_miesieczna"]:
            self.assertAlmostEqual(r["Aktywne sprawy na koniec miesiąca"], 0)
            self.assertAlmostEqual(r["Sprawy naliczające koszt w miesiącu"], 50)
            self.assertAlmostEqual(r["Koszty ogólne aktywnych spraw"], 2150)

    def test_IJ_opoznienie_platnosci_nie_przedluza_kosztu(self):
        a, b = self.licz(), self.licz(czas={"opoznienie_platnosci_miesiace": 8})
        for x, y in zip(a["tabela_miesieczna"], b["tabela_miesieczna"]):
            for key in ("Sprawy naliczające koszt w miesiącu", "Aktywne sprawy", "Łączny koszt miesięczny"):
                self.assertEqual(x[key], y[key])
        self.assertEqual(pierwszy_miesiac_z_wartoscia(b["tabela_miesieczna"], "Przychód razem"),
                         pierwszy_miesiac_z_wartoscia(a["tabela_miesieczna"], "Przychód razem") + 8)

    def test_KL_60_procent_daje_6012_i_proporcjonalna_pojemnosc(self):
        p = oblicz_pojemnosc_miesieczna(self.p, pracownicy=[osoba("EH", 60, 60)])
        eh = p["role"]["EH"]
        self.assertAlmostEqual(eh["wynagrodzenia"], 6012)
        self.assertAlmostEqual(eh["brutto_minuty"] / 60, 100.2)
        self.assertAlmostEqual(eh["dzienne_minuty"] / 60, 100.2 / 8 * 60 / 60)
        self.assertAlmostEqual(eh["netto_minuty"] / 60, 87.675)
        full = oblicz_pojemnosc_miesieczna(self.p, pracownicy=[osoba("EH", 60)])
        self.assertAlmostEqual(eh["netto_minuty"], .6 * full["role"]["EH"]["netto_minuty"])

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

    def test_T_II_nie_wyprzedza_pracy_I_i_nie_placi_przy_I(self):
        # Niezależna kontrola każdego wywołania wykonawcy na rzeczywistych etapach.
        original = timeline._wykonaj_prace
        observed = []
        def checked(queue, completions, available):
            value = original(queue, completions, available)
            for c in completions:
                ii = c.stage_total_minutes.get("ii_instancja", 0)
                if ii:
                    progress = min((c.stage_executed_minutes[k] / v for k, v in c.stage_total_minutes.items()
                                    if k != "ii_instancja" and v > 0), default=1)
                    self.assertLessEqual(c.stage_executed_minutes["ii_instancja"], ii * progress + 1e-6)
                    observed.append(c.stage_executed_minutes["ii_instancja"])
            return value
        p = {**self.p, "udzial_ii_instancji_percent": 100.0}
        with patch.object(timeline, "_wykonaj_prace", checked):
            result = self.licz(p, roster=[osoba("EH", 20, 80), osoba("UGODY", 20, 10)])
        self.assertTrue(observed)
        self.assertTrue(all(r["Zakończenia po I instancji"] == 0 for r in result["tabela_miesieczna"]))
        self.assertTrue(all(r["Przychód z wyroków"] == 0 for r in result["tabela_miesieczna"][:15]))

    def test_T_II_czeka_na_termin_I_nawet_gdy_wczesniej_ma_moc(self):
        p = {**self.p, "udzial_ii_instancji_percent": 100.0}
        result = self.licz(p)
        self.assertEqual(result["tabela_miesieczna"][0]["Nowa praca EH (h)"],
                         (21661.875 - 3740.625) / 60)
        self.assertGreater(result["tabela_miesieczna"][9]["Nowa praca EH (h)"],
                           result["tabela_miesieczna"][0]["Nowa praca EH (h)"])

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
                    self.assertAlmostEqual(row["Sprawy naliczające koszt w miesiącu"], opening + row["Nowe sprawy"], places=6)
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
        eh = 50 * (30 + 150.3 + .7125 * 250 + .7125 * .5 * 210)
        ugody = 50 * (.2875 * 55 + (.15 + .1375) * 35 + (.275 + .1375 + .1375) * 30)
        self.assertAlmostEqual(result["pojemnosc"]["role"]["EH"]["popyt_minuty"], eh)
        self.assertAlmostEqual(result["pojemnosc"]["role"]["UGODY"]["popyt_minuty"], ugody)
        # Aktywne miesiące obejmują miesiąc zakończenia, stąd +1.
        active_billable = 50 * (.2875 * 7 + .35625 * 10 + .35625 * 16)
        expected_cost = 167 * (3 * 20 + 30) + active_billable * 50
        self.assertAlmostEqual(rows[-1]["Sprawy naliczające koszt w miesiącu"], active_billable)
        self.assertAlmostEqual(rows[-1]["Łączny koszt miesięczny"], expected_cost)
        self.assertAlmostEqual(result["kpi"]["wynik_miesieczny_w_stanie_stabilnym"], lifecycle["ogolem"]["przychod"] / 12 - expected_cost)

    def test_W_ujemna_ekonomika_panelu_1_nie_wymusza_straty_kontraktu(self):
        p = {**self.p, "koszt_staly_na_godzine": 500.0, "koszt_sekretariatu_na_godzine": 500.0,
             "sekretariat_minuty_na_sprawe": 60.0}
        self.assertLess(oblicz_model(p)["ogolem"]["wynik_przed_podatkiem"], 0)
        result = self.licz(p, costs={"ogolne_na_aktywna_sprawe": 0.0, "sekretariat_na_aktywna_sprawe": 0.0})
        self.assertEqual(result["kpi"]["status_kontraktu"], "Rentowny i stabilny")
        self.assertGreater(result["kpi"]["wynik_miesieczny_w_stanie_stabilnym"], 0)

    def test_dodatnia_ekonomika_panelu_1_i_strata_kontraktu(self):
        p = {**self.p, "koszt_staly_na_godzine": 0.0, "pracownicy": [osoba("EH", 1), osoba("UGODY", 1)]}
        self.assertGreater(oblicz_model(p)["ogolem"]["wynik_przed_podatkiem"], 0)
        result = self.licz(p, costs={"ogolne_na_aktywna_sprawe": 1000.0})
        self.assertEqual(result["kpi"]["status_kontraktu"], "Stabilny, ale nierentowny")
        self.assertEqual(result["kpi"]["break_even_status"], "brak_ekonomiczny")
        self.assertTrue(result["kpi"]["wynik_nadal_narasta"])

    def test_XY_dokladna_suma_bez_podwojnych_kosztow(self):
        for r in self.licz()["tabela_miesieczna"]:
            total = r["Koszt wynagrodzeń EH"] + r["Koszt wynagrodzeń ugód"] + r["Koszty ogólne aktywnych spraw"] + r["Koszt sekretariatu aktywnych spraw"]
            self.assertEqual(r["Łączny koszt miesięczny"], total)
            self.assertEqual(r["Wynik miesięczny przed podatkiem"], r["Przychód razem"] - total)

    def test_niepelny_rozruch_nie_fabrykuje_dojrzalego_kosztu(self):
        result = self.licz(czas={"horyzont_miesiace": 12})
        self.assertIsNone(result["kpi"]["wynik_miesieczny_w_stanie_stabilnym"])
        self.assertEqual(result["kpi"]["status_kontraktu"], "Stabilny operacyjnie, rentowność niepotwierdzona")
        self.assertEqual(result["kpi"]["break_even_status"], "niepotwierdzony")

    def test_dluzsze_oczekiwanie_zwieksza_koszt_bez_dodatkowej_pracy(self):
        a = self.licz(czas={"horyzont_miesiace": 120})
        b = self.licz(czas={"miesiace_do_ugody": 60, "miesiace_do_wyroku_i": 60, "horyzont_miesiace": 120})
        self.assertTrue(b["podsumowanie"]["dojrzalosc_osiagnieta"])
        self.assertGreater(b["diagnoza"]["koszt_kontraktu_horyzont"], a["diagnoza"]["koszt_kontraktu_horyzont"])
        self.assertAlmostEqual(a["walidacja"]["praca_wszystkich_kohort_minuty"], b["walidacja"]["praca_wszystkich_kohort_minuty"])
        self.assertAlmostEqual(oblicz_model(self.p)["bezposrednie_minuty_spraw"], b["walidacja"]["dojrzaly_popyt_roczny_minuty"])

    def test_zero_spraw_zero_oplat_aktywnych_ale_pelna_placa(self):
        result = self.licz({**self.p, "liczba_spraw": 0})
        for r in result["tabela_miesieczna"]:
            self.assertEqual(r["Koszty ogólne aktywnych spraw"], 0)
            self.assertEqual(r["Koszt sekretariatu aktywnych spraw"], 0)
            self.assertEqual(r["Łączny koszt miesięczny"], 167 * 90)
        self.assertFalse(result["podsumowanie"]["dojrzalosc_osiagnieta"])

    def test_placa_nie_zalezy_od_wykonanej_pracy(self):
        a = self.licz()
        b = self.licz({**self.p, "liczba_spraw": 0})
        self.assertEqual(a["pojemnosc"]["miesieczny_koszt_wynagrodzen"], b["pojemnosc"]["miesieczny_koszt_wynagrodzen"])

    def test_mieszane_przydzialy_i_stawki_sumowane_osobno(self):
        result = self.licz(roster=[osoba("EH", 60, 60), osoba("EH", 80, 25), osoba("UGODY", 100, 0)])
        self.assertAlmostEqual(result["pojemnosc"]["miesieczny_koszt_wynagrodzen"], 6012 + 3340)
        self.assertAlmostEqual(result["pojemnosc"]["role"]["EH"]["netto_minuty"] / 60, 167 * .85 * .875)

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

    def test_wszystkie_sciezki_maja_poprawne_role_bez_dodatkowej_analizy(self):
        packets, completions = defaultdict(list), []
        _dodaj_kohorte(1, oblicz_model(self.p), self.p, domyslne_parametry_czasowe(), packets, completions)
        for p in (p for bucket in packets.values() for p in bucket):
            self.assertEqual(p.role, "UGODY" if p.stage in {"analiza_ugody", "zawarcie_ugody", "nieudana_proba_ugody"} else "EH")
            if p.stage == "analiza_ugody":
                self.assertNotIn("automatyczne_ramy", p.path)


class TestWyczerpanaPojemnoscRoli(unittest.TestCase):
    def test_caly_dzien_EH_blokuje_tylko_EH(self):
        p = {**domyslne_parametry(), "codzienne_czynnosci": {
            "Komunikacja z EH i zlecanie opłat w SOSS": 480}}
        result = oblicz_model_czasowy(p)
        self.assertEqual(result["pojemnosc"]["role"]["EH"]["netto_minuty"], 0)
        self.assertEqual(result["pojemnosc"]["role"]["UGODY"]["netto_minuty"], 10020)
        self.assertTrue(all(r["Wykonana praca EH (h)"] == 0 for r in result["tabela_miesieczna"]))
        self.assertGreater(sum(r["Wykonana praca UGODY (h)"] for r in result["tabela_miesieczna"]), 0)

    def test_dwie_role_nie_maja_wspolnego_mnoznika_dziennego(self):
        p = {**domyslne_parametry(), "codzienne_czynnosci": {"Obsługa skrzynki ugody EH": 480}}
        result = oblicz_model_czasowy(p)
        self.assertEqual(result["pojemnosc"]["role"]["UGODY"]["netto_minuty"], 0)
        self.assertEqual(result["pojemnosc"]["role"]["EH"]["netto_minuty"], 10020)
        self.assertGreater(sum(r["Wykonana praca EH (h)"] for r in result["tabela_miesieczna"]), 0)


class TestFaktycznaWymagalnoscII(unittest.TestCase):
    def test_ii_trafia_do_fifo_z_data_faktycznego_odblokowania(self):
        from timeline import WorkPacket, _uwolnij_ii
        c = Completion(1, "test:ii", "ii", 2, 1, 1000,
                       {"proces": 100, "analiza_ugody": 100, "ii_instancja": 200},
                       {"proces": 0, "analiza_ugody": 0, "ii_instancja": 0})
        pending = [WorkPacket(2, 1, "test:ii", "ii_instancja", 200, 0)]
        self.assertEqual(_uwolnij_ii(pending, [c], 2), [])
        c.stage_executed_minutes["proces"] = 100
        self.assertEqual(_uwolnij_ii(pending, [c], 3), [])
        c.stage_executed_minutes["analiza_ugody"] = 25
        first = _uwolnij_ii(pending, [c], 4)
        self.assertEqual([(p.due_month, p.minutes_remaining) for p in first], [(4, 50)])
        self.assertEqual(_uwolnij_ii(pending, [c], 4), [])
        c.stage_executed_minutes["analiza_ugody"] = 75
        second = _uwolnij_ii(pending, [c], 7)
        self.assertEqual([(p.due_month, p.minutes_remaining) for p in second], [(7, 100)])
        c.stage_executed_minutes["analiza_ugody"] = 100
        third = _uwolnij_ii(pending, [c], 8)
        self.assertEqual([(p.due_month, p.minutes_remaining) for p in third], [(8, 50)])
        self.assertEqual(pending, [])
        c.stage_executed_minutes["ii_instancja"] = 0
        self.assertEqual(_uwolnij_ii([WorkPacket(9, 1, "test:ii", "ii_instancja", 200, 0)], [c], 8), [])
        self.assertEqual(sum(p.minutes_remaining for p in first + second + third), 200)
        self.assertEqual(c.stage_total_minutes["ii_instancja"], 200)


if __name__ == "__main__":
    unittest.main()
