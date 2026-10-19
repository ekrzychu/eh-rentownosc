"""Regresje reguł A–AK z niezależnymi oczekiwaniami i audytem zdarzeń.

Scenariusze jednorodne nie korzystają z pomocników wyliczających pracę,
pojemność, opłaty lub harmonogram modelu.
"""

from collections import defaultdict
from copy import deepcopy
from math import fsum, isfinite
from time import perf_counter
import unittest
from unittest.mock import patch

import timeline
from model import domyslne_parametry, oblicz_model, oblicz_przeplyw, _skaluj_bezposrednie_czasy
from staff import pojemnosc_obsady, srednie_stawki_wedlug_roli
from timeline import oblicz_model_czasowy
from workflow import etapy_sprawy


def osoba(rola, godziny=167, placa=60):
    return {'rola': rola, 'stawka': float(placa), 'wykorzystanie_percent': godziny / 167 * 100}


def proste(naplyw=12, proces=60, przyjecie=0):
    p = domyslne_parametry()
    p.update(liczba_spraw=naplyw, kategoryczna_odmowa_percent=100., automatyczne_ramy_percent=0.,
        udzial_ii_instancji_percent=0., udzialy_rodzajow={'P1': 100., 'P2': 0., 'P3': 0.},
        wysoki_wps_procent=100., wspolne_czynnosci={'Przyjęcie': przyjecie},
        procesowe_czynnosci={'Proces': proces}, dodatkowe_minuty={'P1': 0, 'P2': 0, 'P3': 0},
        codzienne_czynnosci={}, pracownicy=[osoba('EH'), osoba('UGODY')])
    return p


def ugody(naplyw=12, praca=60, przyjecie=0, sukces=100.):
    p = proste(naplyw, proces=60, przyjecie=przyjecie)
    p.update(kategoryczna_odmowa_percent=0., automatyczne_ramy_percent=100.,
             skutecznosc_automatycznych_ram_percent=sukces,
             ugodowe_czynnosci={'Oferta ugody': praca, 'Projekt ugody': 0, 'Podpisanie ugody': 0})
    return p


def licz(p, miesiace=12, narzut=43, sekretariat=7, **czasy):
    return oblicz_model_czasowy(p, {'horyzont_miesiace': miesiace, **czasy}, zapisz_zdarzenia=True,
        koszty_kontraktu={'ogolne_na_aktywna_sprawe': narzut, 'sekretariat_na_aktywna_sprawe': sekretariat})


def zdarzenia_spraw(w):
    grouped = defaultdict(list)
    for e in w['zdarzenia']:
        grouped[e['sprawa']].append(e)
    return grouped


class TestFIFOIKoszty(unittest.TestCase):
    def test_A_B_50_wplywa_45_pracuje_piec_czeka_a_nastepnie_55(self):
        p = proste(600, proces=480)
        p['pracownicy'] = [osoba('EH'), osoba('EH'), osoba('EH', 26)]
        a, b = licz(p, 2)['tabela_miesieczna']
        self.assertEqual(a['Nowe sprawy'], 50)
        self.assertEqual(a['Ukończona praca: proces'], 45)
        self.assertEqual(a['Sprawy, nad którymi pracowano w miesiącu'], 45)
        self.assertEqual(a['Sprawy oczekujące na pracę'], 5)
        self.assertEqual(a['Backlog EH (h)'], 5 * 8)
        self.assertEqual(b['Sprawy oczekujące na pracę na początku'] + b['Nowe sprawy'], 55)
        self.assertEqual(b['Sprawy oczekujące na pracę'], 10)

    def test_C_kolejka_i_oczekiwanie_formalne_nie_sa_oplata(self):
        p = proste(12, proces=60)
        w = licz(p, 8)
        for row in w['tabela_miesieczna']:
            self.assertEqual(row['Sprawy, nad którymi pracowano w miesiącu'], 1)
            self.assertEqual(row['Koszty ogólne spraw, nad którymi pracowano'], 43)
        self.assertEqual(w['tabela_miesieczna'][-1]['Sprawy otwarte'], 8)
        self.assertEqual(w['tabela_miesieczna'][-1]['Sprawy oczekujące na formalne zakończenie'], 8)
        p['pracownicy'] = []
        self.assertTrue(all(r['Koszty ogólne spraw, nad którymi pracowano'] == 0 for r in licz(p)['tabela_miesieczna']))

    def test_D_praca_w_dwoch_miesiacach_szesc_oczekiwania_dwie_oplaty(self):
        p = proste(12, proces=334 * 60)
        w = licz(p, 8, miesiace_do_wyroku_i=7)
        first = zdarzenia_spraw(w)[0]
        months = {e['miesiac'] for e in first if e['rodzaj'] == 'praca'}
        self.assertEqual(months, {1, 2})
        self.assertEqual(sum(43 for _ in months), 86)
        self.assertEqual([e['miesiac'] for e in first if e['rodzaj'] == 'zakonczenie'], [8])

    def test_E_AF_EH_i_ugody_pracuja_w_jednym_miesiacu_jedna_oplata(self):
        w = licz(ugody(praca=1, przyjecie=1), 1)
        work = [e for e in w['zdarzenia'] if e['rodzaj'] == 'praca']
        self.assertEqual({e['rola'] for e in work}, {'EH', 'UGODY'})
        r = w['tabela_miesieczna'][0]
        self.assertEqual(r['Sprawy, nad którymi pracowano w miesiącu'], 1)
        self.assertEqual(r['Koszty ogólne spraw, nad którymi pracowano'], 43)
        self.assertEqual(r['Koszt sekretariatu spraw, nad którymi pracowano'], 7)

    def test_F_G_koszt_0_i_43_nie_zmienia_przeplywu(self):
        p = domyslne_parametry()
        a, b = licz(p, 60, narzut=0), licz(p, 60, narzut=43)
        self.assertEqual(a['zdarzenia'], b['zdarzenia'])
        for x, y in zip(a['tabela_miesieczna'], b['tabela_miesieczna']):
            for key in x:
                if not any(k in key.lower() for k in ('koszt', 'wynik')):
                    self.assertEqual(x[key], y[key])
        total = fsum(r['Sprawy, nad którymi pracowano w miesiącu'] for r in b['tabela_miesieczna'])
        self.assertAlmostEqual(b['kpi']['wynik_skumulowany_na_koniec_horyzontu'] - a['kpi']['wynik_skumulowany_na_koniec_horyzontu'], -43 * total)

    def test_czesciowa_sprawa_zachowuje_tozsamosc_i_minuty(self):
        p = proste(12, proces=100 * 60)
        p['pracownicy'] = [osoba('EH', 60)]
        w = licz(p, 3)
        first = zdarzenia_spraw(w)[0]
        self.assertEqual([e['minuty'] for e in first if e['rodzaj'] == 'praca'], [3600, 2400])
        self.assertEqual([e['miesiac'] for e in first if e['rodzaj'] == 'koniec_pracy' and e['etap'] == 'proces'], [2])
        self.assertEqual([r['Sprawy, nad którymi pracowano w miesiącu'] for r in w['tabela_miesieczna']], [1, 2, 1])

    def test_ulamkowe_wagi_nie_sa_zaokraglane_i_nie_staja_sie_przychodem_za_czesc_pracy(self):
        p = proste(30, proces=100 * 60)
        p['pracownicy'] = [osoba('EH', 167)]
        w = licz(p, 1, miesiace_do_wyroku_i=0)
        row = w['tabela_miesieczna'][0]
        self.assertEqual(row['Nowe sprawy'], 2.5)
        self.assertEqual(row['Zakończenia po I instancji'], 1)
        self.assertEqual(row['Sprawy, nad którymi pracowano w miesiącu'], 2)
        self.assertEqual(row['Sprawy oczekujące na pracę'], 1.5)


class TestRoleIZaleznosci(unittest.TestCase):
    def test_H_I_bez_ugod_blokuje_57_5_procent_i_puszcza_42_5(self):
        p = domyslne_parametry()
        p['pracownicy'] = [osoba('EH') for _ in range(3)]
        w = licz(p, 60)
        rows = w['tabela_miesieczna']
        self.assertEqual(sum(r['Ugody zakończone'] for r in rows), 0)
        settled_paths = {'automatyczne_ramy_ugoda', 'zawarte_poza_ramami', 'automatyczne_ramy_brak_ugody', 'brak_ugody_poza_ramami'}
        self.assertFalse(any(e['etap'] == 'proces' and e['sciezka'] in settled_paths for e in w['zdarzenia']))
        ended = [e for e in w['zdarzenia'] if e['rodzaj'] == 'zakonczenie']
        self.assertEqual({e['sciezka'] for e in ended}, {'kategoryczna_odmowa', 'brak_szans'})
        self.assertAlmostEqual(fsum(r['Zakończenia po I instancji'] + r['Zakończenia po II instancji'] for r in rows[-12:]), 600 * .425)
        self.assertGreaterEqual(rows[-1]['Sprawy otwarte'], 3000 * .575)

    def test_J_odrzucona_ugoda_przekazuje_proces_dopiero_nastepny_miesiac(self):
        w = licz(ugody(sukces=0), 4, miesiace_do_wyroku_i=0)
        for events in zdarzenia_spraw(w).values():
            rejection = next(e['miesiac'] for e in events if e['etap'] == 'proba_ugody' and e['rodzaj'] == 'koniec_pracy')
            process = [e for e in events if e['etap'] == 'proces']
            self.assertTrue(all(e['miesiac'] == rejection + 1 for e in process))
        self.assertEqual(w['tabela_miesieczna'][0]['Ukończona praca: proces'], 0)
        self.assertEqual(w['tabela_miesieczna'][1]['Ukończona praca: proces'], 1)

    def test_K_udana_ugoda_nigdy_nie_trafia_do_procesu(self):
        w = licz(ugody(), 20)
        self.assertFalse(any(e['etap'] in {'proces', 'ii_instancja'} for e in w['zdarzenia']))
        self.assertEqual(sum(r['Wykonana praca EH (h)'] for r in w['tabela_miesieczna']), 0)

    def test_przyjecie_EH_poprzedza_ugody_rowniez_gdy_czas_przyjecia_jest_zero(self):
        p = ugody(przyjecie=0)
        p['pracownicy'] = [osoba('UGODY')]
        w = licz(p, 20)
        self.assertEqual(w['zdarzenia'], [])
        self.assertEqual(sum(r['Ugody zakończone'] for r in w['tabela_miesieczna']), 0)

    def test_brak_szans_przenosi_30_minut_do_EH_bez_zmiany_szesciu_sum(self):
        p = domyslne_parametry()
        r = oblicz_przeplyw(p)
        expected = {'kategoryczna_odmowa': (280, 0), 'automatyczne_ramy_ugoda': (30, 55),
                    'automatyczne_ramy_brak_ugody': (280, 35), 'brak_szans': (310, 0),
                    'zawarte_poza_ramami': (30, 85), 'brak_ugody_poza_ramami': (280, 65)}
        for path, (eh, ug) in expected.items():
            self.assertEqual(r['czasy_sciezek_wedlug_roli'][path], {'EH': eh, 'UGODY': ug})
            self.assertEqual(eh + ug, r['czasy_sciezek_ugod'][path])
        self.assertEqual(r['roczne_minuty_wedlug_roli'], {'EH': 264892.5, 'UGODY': 20475.})
        self.assertEqual(r['bezposrednie_minuty_spraw'], 285367.5)

    def test_P1_P2_P3_naleza_do_EH_i_nie_sa_dodawane_drugi_raz(self):
        p = domyslne_parametry()
        for path in oblicz_przeplyw(p)['czasy_sciezek_ugod']:
            for typ, extra in p['dodatkowe_minuty'].items():
                a, b = etapy_sprawy(p, path, extra), etapy_sprawy(p, path)
                self.assertEqual(a[0].rola, 'EH')
                self.assertEqual(sum(e.minuty for e in a) - sum(e.minuty for e in b), extra)


class TestZegary(unittest.TestCase):
    def test_L_ugoda_czeka_na_faktyczne_rozpoczecie_i_koniec_pracy(self):
        p = ugody(36, praca=200 * 60)
        w = licz(p, 15, miesiace_do_ugody=3)
        first_cohort = list(zdarzenia_spraw(w).values())[:3]
        self.assertEqual([next(e['miesiac'] for e in es if e['rodzaj'] == 'inicjacja' and e['etap'] == 'ugoda') for es in first_cohort], [1, 2, 3])
        for es in zdarzenia_spraw(w).values():
            start = next((e['miesiac'] for e in es if e['rodzaj'] == 'inicjacja' and e['etap'] == 'ugoda'), None)
            endwork = next((e['miesiac'] for e in es if e['rodzaj'] == 'koniec_pracy' and e['etap'] == 'ugoda'), None)
            for e in es:
                if e['rodzaj'] == 'zakonczenie':
                    self.assertEqual(e['miesiac'], max(start + 3, endwork))

    def test_M_proces_nie_startuje_zegara_w_kolejce_ani_przy_samym_przyjeciu(self):
        p = proste(12, proces=60, przyjecie=200 * 60)
        w = licz(p, 8, miesiace_do_wyroku_i=2)
        first = zdarzenia_spraw(w)[0]
        self.assertEqual(next(e['miesiac'] for e in first if e['rodzaj'] == 'inicjacja' and e['etap'] == 'proces'), 2)
        self.assertEqual(next(e['miesiac'] for e in first if e['rodzaj'] == 'zakonczenie'), 4)

    def test_N_O_ii_po_wyroku_i_z_wlasnym_zegarem_i_jednym_przychodem(self):
        p = proste()
        p.update(udzial_ii_instancji_percent=100., obsluga_ii_instancji_minuty=200 * 60)
        w = licz(p, 12, miesiace_do_wyroku_i=2, miesiace_wyrok_i_do_ii=3)
        first = zdarzenia_spraw(w)[0]
        self.assertEqual(next(e['miesiac'] for e in first if e['rodzaj'] == 'wyrok_i'), 3)
        self.assertEqual(next(e['miesiac'] for e in first if e['rodzaj'] == 'inicjacja' and e['etap'] == 'ii_instancja'), 4)
        self.assertEqual(next(e['miesiac'] for e in first if e['rodzaj'] == 'zakonczenie'), 7)
        self.assertTrue(all(r['Zakończenia po I instancji'] == 0 for r in w['tabela_miesieczna']))
        self.assertTrue(all(r['Przychód z wyroków'] == 0 for r in w['tabela_miesieczna'][:6]))
        self.assertEqual(len([e for e in first if e['rodzaj'] == 'zakonczenie']), 1)

    def test_zerowy_lag_nie_pozwala_wyprzedzic_konca_pracy(self):
        w = licz(ugody(praca=200 * 60), 3, miesiace_do_ugody=0)
        first = zdarzenia_spraw(w)[0]
        self.assertEqual(next(e['miesiac'] for e in first if e['rodzaj'] == 'zakonczenie'), 2)

    def test_AH_platnosc_przesuwa_pieniadze_bez_pracy_i_oplat(self):
        p = proste()
        a = licz(p, 20, miesiace_do_wyroku_i=0)
        b = licz(p, 20, miesiace_do_wyroku_i=0, opoznienie_platnosci_miesiace=3)
        self.assertEqual(a['zdarzenia'], b['zdarzenia'])
        for i, (x, y) in enumerate(zip(a['tabela_miesieczna'], b['tabela_miesieczna'])):
            for col in ('Sprawy, nad którymi pracowano w miesiącu', 'Łączny koszt miesięczny', 'Sprawy otwarte'):
                self.assertEqual(x[col], y[col])
            self.assertEqual(y['Przychód razem'], a['tabela_miesieczna'][i-3]['Przychód razem'] if i >= 3 else 0)


class TestZeroCzasu(unittest.TestCase):
    def test_P_R_zero_minut_zero_oplat_ale_otwarte_sprawy(self):
        p = _skaluj_bezposrednie_czasy(domyslne_parametry(), 0)
        w = licz(p, 60)
        self.assertTrue(all(r['Wykonana praca (h)'] == r['Sprawy, nad którymi pracowano w miesiącu'] == 0 for r in w['tabela_miesieczna']))
        self.assertTrue(all(r['Koszty ogólne spraw, nad którymi pracowano'] == r['Koszt sekretariatu spraw, nad którymi pracowano'] == 0 for r in w['tabela_miesieczna']))
        self.assertEqual(w['walidacja']['praca_wszystkich_kohort_minuty'], 0)
        self.assertEqual(w['walidacja']['backlog_minuty'], 0)
        self.assertGreater(w['podsumowanie']['aktywne_sprawy'], 0)

    def test_Q_zero_minut_nie_omija_zerowych_przydzialow_ani_braku_roli(self):
        p = _skaluj_bezposrednie_czasy(ugody(), 0)
        for roster in ([], [osoba('EH')], [osoba('UGODY')], [osoba('EH'), osoba('UGODY', 0)]):
            with self.subTest(roster=roster):
                p['pracownicy'] = roster
                w = licz(p, 20, miesiace_do_ugody=0)
                self.assertEqual(w['walidacja']['laczne_zakonczenia_spraw'], 0)
                self.assertEqual(w['pojemnosc']['status_pojemnosci'], 'Niewystarczająca')
                self.assertEqual(w['walidacja']['praca_wykonana_minuty'], 0)

    def test_zero_minut_nie_omija_EH_zajetego_w_calosci_dziennymi(self):
        p = _skaluj_bezposrednie_czasy(proste(), 0)
        p['codzienne_czynnosci'] = {'Obsługa skrzynki ugody EH': 480}
        self.assertEqual(licz(p, 20)['walidacja']['laczne_zakonczenia_spraw'], 0)

    def test_zero_etapow_po_handoff_startuje_zegar_od_nastepnego_miesiaca(self):
        p = _skaluj_bezposrednie_czasy(ugody(sukces=0), 0)
        w = licz(p, 5, miesiace_do_wyroku_i=2)
        es = zdarzenia_spraw(w)[0]
        self.assertEqual(next(e['miesiac'] for e in es if e['rodzaj'] == 'inicjacja' and e['etap'] == 'proces'), 2)
        self.assertEqual(next(e['miesiac'] for e in es if e['rodzaj'] == 'zakonczenie'), 4)

    def test_zero_minut_bez_ugod_nie_blokuje_wstepnej_kwalifikacji_EH(self):
        p = _skaluj_bezposrednie_czasy(domyslne_parametry(), 0)
        p['pracownicy'] = [osoba('EH')]
        w = licz(p, 60)
        last = w['tabela_miesieczna'][-12:]
        self.assertAlmostEqual(sum(r['Zakończenia po I instancji'] + r['Zakończenia po II instancji'] for r in last), 600 * .425)
        self.assertEqual(sum(r['Ugody zakończone'] for r in last), 0)
        self.assertTrue(all(r['Sprawy, nad którymi pracowano w miesiącu'] == 0 for r in last))


class TestDzienneIKoszty(unittest.TestCase):
    def test_T_U_trzy_EH_maja_469_6875_godzin_i_jednego_opiekuna(self):
        roster = [osoba('EH') for _ in range(3)]
        r = pojemnosc_obsady(roster, domyslne_parametry()['codzienne_czynnosci'])['EH']
        self.assertEqual(r['brutto_minuty'] / 60, 501)
        self.assertEqual(r['dzienne_minuty'] / 60, 31.3125)
        self.assertEqual(r['netto_minuty'] / 60, 469.6875)
        self.assertEqual(r['opiekun_dziennych'], 0)
        for n in (1, 3, 10):
            r = pojemnosc_obsady([osoba('EH') for _ in range(n)], domyslne_parametry()['codzienne_czynnosci'])
            self.assertEqual(r['EH']['dzienne_wymagane_minuty'] / 60, 31.3125)
            self.assertEqual(r['UGODY']['dzienne_minuty'], 0)

    def test_V_srednia_15_i_22_50_za_dzien(self):
        roster = [osoba('EH', placa=w) for w in (10, 15, 20)]
        average = srednie_stawki_wedlug_roli(roster)['EH']
        self.assertEqual(average, 15)
        self.assertEqual(90 / 60 * average, 22.5)
        p = {**domyslne_parametry(), 'pracownicy': roster + [osoba('UGODY')]}
        self.assertAlmostEqual(oblicz_model(p)['czynnosci_dzienne_lifecycle_koszt'], 375.75 * (15 + 36))

    def test_W_AD_AE_dzienne_nie_sa_dodatkowa_pensja(self):
        p = proste()
        p['pracownicy'] = [osoba('EH', placa=10), osoba('EH', placa=15), osoba('EH', placa=20), osoba('UGODY', placa=30)]
        a = licz(p, 1)['tabela_miesieczna'][0]
        p['codzienne_czynnosci'] = domyslne_parametry()['codzienne_czynnosci']
        b = licz(p, 1)['tabela_miesieczna'][0]
        self.assertEqual(a['Miesięczny koszt wynagrodzeń'], 167 * (10 + 15 + 20 + 30))
        self.assertEqual(a['Miesięczny koszt wynagrodzeń'], b['Miesięczny koszt wynagrodzeń'])
        self.assertEqual(a['Łączny koszt miesięczny'], b['Łączny koszt miesięczny'])

    def test_X_Y_dzienne_480_zmniejszaja_pojemnosc_i_tworza_backlog(self):
        p = proste(600, proces=180)
        a = licz(p, 24)
        p['codzienne_czynnosci'] = {'Obsługa skrzynki ugody EH': 480}
        b = licz(p, 24)
        self.assertEqual(a['pojemnosc']['role']['EH']['netto_minuty'], 10020)
        self.assertEqual(b['pojemnosc']['role']['EH']['netto_minuty'], 0)
        self.assertGreater(b['podsumowanie']['backlog_koniec_godziny'], a['podsumowanie']['backlog_koniec_godziny'])
        self.assertLess(b['walidacja']['laczne_zakonczenia_spraw'], a['walidacja']['laczne_zakonczenia_spraw'])

    def test_Z_nadmiar_mocy_dopuszcza_niezmieniony_przychod(self):
        p = proste()
        p['pracownicy'] = [osoba('EH') for _ in range(3)]
        a = licz(p, 24)
        p['codzienne_czynnosci'] = {'Obsługa skrzynki ugody EH': 480}
        b = licz(p, 24)
        self.assertEqual([r['Przychód razem'] for r in a['tabela_miesieczna']], [r['Przychód razem'] for r in b['tabela_miesieczna']])
        self.assertEqual(b['pojemnosc']['role']['EH']['netto_minuty'] / 60, 334)
        self.assertEqual(b['tabela_miesieczna'][0]['Czynności dzienne (h)'], 167)

    def test_niepelne_przydzialy_nie_rozdzielaja_dziennych_na_kilka_osob(self):
        roster = [osoba('EH', 20), osoba('EH', 20)]
        r = pojemnosc_obsady(roster, domyslne_parametry()['codzienne_czynnosci'])['EH']
        self.assertEqual(r['dzienne_minuty'] / 60, 20)
        self.assertEqual(r['dzienne_niewykonane_minuty'] / 60, 11.3125)
        self.assertEqual(r['netto_minuty'] / 60, 20)
        p = {**proste(), 'pracownicy': roster, 'codzienne_czynnosci': domyslne_parametry()['codzienne_czynnosci']}
        self.assertEqual(licz(p)['pojemnosc']['status_pojemnosci'], 'Niewystarczająca')

    def test_brak_EH_ujawnia_niewykonane_dzienne(self):
        p = domyslne_parametry()
        p['pracownicy'] = [osoba('UGODY')]
        r = licz(p, 1)['tabela_miesieczna'][0]
        self.assertEqual(r['Czynności dzienne (h)'], 0)
        self.assertEqual(r['Niewykonane czynności dzienne (h)'], 31.3125)

    def test_AA_AB_AC_stawki_rol_i_koszty_paneli_niezalezne(self):
        p = domyslne_parametry()
        for idx, col in ((0, 'Wynagrodzenia EH'), (1, 'Wynagrodzenia ugód')):
            q = deepcopy(p)
            q['pracownicy'][idx]['stawka'] += 10
            a, b = oblicz_model(p), oblicz_model(q)
            role = p['pracownicy'][idx]['rola']
            expected = a['role'][role]['laczne_godziny_zasobu_lifecycle'] * 10
            self.assertAlmostEqual(b['ogolem']['koszt_calkowity'] - a['ogolem']['koszt_calkowity'], expected)
            x, y = licz(p, 1), licz(q, 1)
            self.assertEqual(x['zdarzenia'], y['zdarzenia'])
            self.assertAlmostEqual(y['tabela_miesieczna'][0][col] - x['tabela_miesieczna'][0][col], 1670)
        p1 = deepcopy(p)
        p1.update(koszt_staly_na_godzine=999., koszt_sekretariatu_na_godzine=999., sekretariat_minuty_na_sprawe=999.)
        self.assertEqual(licz(p, 1), licz(p1, 1))

    def test_kazde_wejscie_czasowe_ma_niezalezna_wycene_przypisanej_roli(self):
        p = domyslne_parametry()
        p['pracownicy'] = [osoba('EH', placa=15), osoba('UGODY', placa=60)]
        base = oblicz_model(p)['ogolem']['koszt_calkowity']
        entries = []
        entries.extend(('wspolne_czynnosci', k, 600 / 60 * (15 + 36)) for k in p['wspolne_czynnosci'])
        entries.extend(('procesowe_czynnosci', k, 600 * .7125 / 60 * (15 + 36)) for k in p['procesowe_czynnosci'])
        entries.extend(('ugodowe_czynnosci', k, 600 * (.2875 if k == 'Podpisanie ugody' else .575) / 60 * (60 + 36)) for k in p['ugodowe_czynnosci'])
        entries.extend(('dodatkowe_minuty', k, 600 * share / 100 / 60 * (15 + 36)) for k, share in p['udzialy_rodzajow'].items())
        entries.extend(('codzienne_czynnosci', k, 250.5 / 60 * (15 + 36)) for k in p['codzienne_czynnosci'])
        entries.extend(((None, 'analiza_mozliwosci_ugody', 600 * .275 / 60 * (15 + 36 + 60 + 36)),
                        (None, 'obsluga_ii_instancji_minuty', 600 * .35625 / 60 * (15 + 36))))
        for section, key, expected in entries:
            q = deepcopy(p)
            target = q[section] if section else q
            target[key] += 1
            with self.subTest(section=section, key=key):
                self.assertAlmostEqual(oblicz_model(q)['ogolem']['koszt_calkowity'] - base, expected)


class TestBilansIWydajnosc(unittest.TestCase):
    def test_S_polowa_czasu_podwaja_potencjal_pracy_w_waskim_gardle(self):
        p = proste(600, proces=480)
        p['pracownicy'] = [osoba('EH', 160)]
        a = licz(p, 24, miesiace_do_wyroku_i=0)
        b = licz(_skaluj_bezposrednie_czasy(p, .5), 24, miesiace_do_wyroku_i=0)
        self.assertEqual(a['tabela_miesieczna'][0]['Ukończona praca: proces'], 20)
        self.assertEqual(b['tabela_miesieczna'][0]['Ukończona praca: proces'], 40)
        self.assertEqual(a['tabela_miesieczna'][0]['Wykonana praca EH (h)'], 160)
        self.assertEqual(b['tabela_miesieczna'][0]['Wykonana praca EH (h)'], 160)
        self.assertGreater(b['walidacja']['laczne_zakonczenia_spraw'], a['walidacja']['laczne_zakonczenia_spraw'])
        self.assertLess(b['podsumowanie']['backlog_koniec_godziny'], a['podsumowanie']['backlog_koniec_godziny'])

    def test_S_mieszany_portfel_polowa_czasu_nie_pogarsza_kolejek(self):
        p = domyslne_parametry()
        a, b = licz(p, 60), licz(_skaluj_bezposrednie_czasy(p, .5), 60)
        self.assertGreater(b['walidacja']['laczne_zakonczenia_spraw'], a['walidacja']['laczne_zakonczenia_spraw'])
        self.assertLess(b['podsumowanie']['sprawy_oczekujace_na_prace'], a['podsumowanie']['sprawy_oczekujace_na_prace'])
        self.assertLess(b['podsumowanie']['backlog_koniec_godziny'], a['podsumowanie']['backlog_koniec_godziny'])
        self.assertGreater(sum(r['Przychód razem'] for r in b['tabela_miesieczna']), sum(r['Przychód razem'] for r in a['tabela_miesieczna']))

    def test_AG_bilanse_minut_tozsamosci_pensji_i_przychodu(self):
        w = licz(domyslne_parametry(), 60)
        cumulative = inflow = completed = 0.
        for row in w['tabela_miesieczna']:
            cost = row['Wynagrodzenia EH'] + row['Wynagrodzenia ugód'] + row['Koszty ogólne spraw, nad którymi pracowano'] + row['Koszt sekretariatu spraw, nad którymi pracowano']
            self.assertAlmostEqual(row['Łączny koszt miesięczny'], cost)
            cumulative += row['Przychód razem'] - cost
            self.assertAlmostEqual(row['Wynik skumulowany przed podatkiem'], cumulative)
            inflow += row['Nowe sprawy']
            completed += row['Ugody zakończone'] + row['Zakończenia po I instancji'] + row['Zakończenia po II instancji']
            self.assertAlmostEqual(inflow - completed, row['Sprawy otwarte'])
        v = w['walidacja']
        self.assertAlmostEqual(v['praca_wykonana_minuty'] + v['backlog_minuty'] + v['praca_przyszla_minuty'], 285367.5 * 5)
        for events in zdarzenia_spraw(w).values():
            starts, ends, closed = set(), set(), False
            for e in events:
                self.assertFalse(closed)
                if e['rodzaj'] == 'inicjacja':
                    self.assertNotIn(e['etap'], starts)
                    starts.add(e['etap'])
                if e['rodzaj'] == 'koniec_pracy':
                    self.assertNotIn(e['etap'], ends)
                    ends.add(e['etap'])
                closed = e['rodzaj'] == 'zakonczenie'

    def test_AI_odwrocenie_slownikow_i_grup_nie_zmienia_harmonogramu(self):
        p = domyslne_parametry()
        baseline = licz(p, 24)
        q = deepcopy(p)
        for key, value in q.items():
            if isinstance(value, dict):
                q[key] = dict(reversed(list(value.items())))
        original = timeline.oblicz_przeplyw
        def reversed_groups(params):
            out = original(params)
            out['grupy'].reverse()
            return out
        with patch.object(timeline, 'oblicz_przeplyw', reversed_groups):
            got = licz(q, 24)
        self.assertEqual(got['tabela_miesieczna'], baseline['tabela_miesieczna'])
        self.assertEqual(got['zdarzenia'], baseline['zdarzenia'])

    def test_AJ_zero_osob_i_przydzialow_nie_wytwarza_mocy(self):
        for roster in ([], [osoba('EH', 0), osoba('UGODY', 0)]):
            p = {**domyslne_parametry(), 'pracownicy': roster}
            w = licz(p, 120)
            self.assertEqual(w['walidacja']['praca_wykonana_minuty'], 0)
            self.assertEqual(w['walidacja']['laczne_zakonczenia_spraw'], 0)
            self.assertEqual(w['pojemnosc']['miesieczny_koszt_wynagrodzen'], 0)
            self.assertEqual(w['tabela_miesieczna'][-1]['Sprawy otwarte'], 6000)

    def test_AK_60_120_360_miesiecy_i_skonczone_wartosci(self):
        for months in (60, 120, 360):
            start = perf_counter()
            w = oblicz_model_czasowy(domyslne_parametry(), {'horyzont_miesiace': months})
            self.assertLess(perf_counter() - start, 20)
            for row in w['tabela_miesieczna']:
                self.assertTrue(all(value is None or isfinite(value) for value in row.values()))
            self.assertEqual(w['walidacja']['laczny_naplyw_spraw'], months * 50)


if __name__ == '__main__':
    unittest.main()
