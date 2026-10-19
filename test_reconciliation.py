"""Niezależne regresje matematyczne wspólnej obsady i alternatywnych rachunków."""

from copy import deepcopy
from math import fsum
import unittest

from analysis import analiza_wrazliwosci, ekonomika_ugod, kopiuj_parametry, ustaw_parametr
from diagnostic_costs import scenariusze, sprawdz_niezaleznosc, niezalezne_minuty_roczne
from model import domyslne_parametry, oblicz_model, oblicz_przeplyw, oblicz_prog_wynagrodzenia_pracownika
from staff import srednie_stawki_wedlug_roli
from timeline import oblicz_model_czasowy


def osoba(rola, stawka, przydzial=100.0):
    return {'rola': rola, 'stawka': float(stawka), 'wykorzystanie_percent': float(przydzial)}


class TestWspolneStawkiIRole(unittest.TestCase):
    def setUp(self):
        self.p = {**domyslne_parametry(), 'pracownicy': [osoba('EH', 50), osoba('EH', 70, 1), osoba('UGODY', 45)]}

    def test_srednia_arytmetyczna_bez_wazenia_przydzialem(self):
        self.assertEqual(srednie_stawki_wedlug_roli(self.p['pracownicy']), {'EH': 60, 'UGODY': 45})
        self.assertEqual(oblicz_model(self.p)['stawki_wedlug_roli'], {'EH': 60, 'UGODY': 45})

    def test_zero_przydzialu_wylacza_osobe_ze_sredniej(self):
        p = deepcopy(self.p)
        p['pracownicy'][1]['wykorzystanie_percent'] = 0
        self.assertEqual(oblicz_model(p)['stawki_wedlug_roli']['EH'], 50)

    def test_brak_globalnej_stawki(self):
        self.assertNotIn('wynagrodzenie_pracownika_na_godzine', self.p)
        bez_obsady = {k: v for k, v in self.p.items() if k != 'pracownicy'}
        for funkcja in (oblicz_model, oblicz_model_czasowy):
            with self.assertRaisesRegex(ValueError, 'Brak wspólnej obsady'):
                funkcja(bez_obsady)
        with self.assertRaisesRegex(ValueError, 'wyłącznie w obsadzie'):
            oblicz_model({**self.p, 'wynagrodzenie_pracownika_na_godzine': 1})

    def test_niezalezne_minuty_i_przychod_referencyjny(self):
        r = oblicz_model(self.p)
        self.assertEqual(niezalezne_minuty_roczne(self.p), {'EH': 259942.5, 'UGODY': 25425.0})
        self.assertEqual(r['roczne_minuty_wedlug_roli'], {'EH': 259942.5, 'UGODY': 25425.0})
        self.assertAlmostEqual(r['bezposrednie_minuty_spraw'], 285367.5)
        self.assertAlmostEqual(r['ogolem']['przychod'], 451963.254)

    def test_obciazenia_dzienne_osobno_i_dokladny_koszt(self):
        r = oblicz_model(self.p)
        h_eh = 259942.5 / 60 * 480 / 420
        h_ug = 25425.0 / 60 * 480 / 450
        self.assertAlmostEqual(r['role']['EH']['laczne_godziny_zasobu_lifecycle'], h_eh)
        self.assertAlmostEqual(r['role']['UGODY']['laczne_godziny_zasobu_lifecycle'], h_ug)
        self.assertAlmostEqual(r['role']['EH']['mnoznik_zasobu'], 480 / 420)
        self.assertAlmostEqual(r['role']['UGODY']['mnoznik_zasobu'], 480 / 450)
        self.assertAlmostEqual(r['laczne_godziny_zasobu_lifecycle'] / 600, 9.00547619047619)
        self.assertAlmostEqual(r['koszt_wynagrodzen_lifecycle'], h_eh * 60 + h_ug * 45)
        self.assertAlmostEqual(r['koszt_lifecycle_razem'], h_eh * 60 + h_ug * 45 + (h_eh + h_ug) * 36)

    def test_sześć_sciezek_i_p_bez_zmiany_minut(self):
        r = oblicz_model(self.p)
        expected = {'kategoryczna_odmowa': (280, 0), 'automatyczne_ramy_ugoda': (30, 55),
                    'automatyczne_ramy_brak_ugody': (280, 35), 'brak_szans': (280, 30),
                    'zawarte_poza_ramami': (30, 85), 'brak_ugody_poza_ramami': (280, 65)}
        for path, (eh, ug) in expected.items():
            self.assertEqual(r['czasy_sciezek_wedlug_roli'][path], {'EH': eh, 'UGODY': ug})
            self.assertEqual(eh + ug, r['czasy_sciezek_ugod'][path])
        for g in r['grupy']:
            self.assertAlmostEqual(g['bezposrednie_minuty_wedlug_roli']['UGODY'], 42.375)
            self.assertAlmostEqual(g['bezposrednie_minuty_wedlug_roli']['EH'], 282.9375 + self.p['dodatkowe_minuty'][g['rodzaj']])
            expected_wage = g['godziny_zasobu_wedlug_roli']['EH'] * 60 + g['godziny_zasobu_wedlug_roli']['UGODY'] * 45
            self.assertAlmostEqual(g['koszt_wynagrodzenia'], expected_wage)

    def test_zmiana_przydzialu_dodatniego_nie_skaluje_lifecycle(self):
        p = deepcopy(self.p)
        p['pracownicy'][0]['wykorzystanie_percent'] = 0.01
        p['pracownicy'][1]['wykorzystanie_percent'] = 90
        p['pracownicy'][2]['wykorzystanie_percent'] = 0.01
        self.assertEqual(oblicz_model(p), oblicz_model(self.p))
        self.assertGreater(oblicz_model(p)['laczne_godziny_zasobu_lifecycle'], 167 * 12)

    def test_stawka_kazdej_roli_zmienia_wycene_tej_roli(self):
        for indeks, rola, liczba in ((0, 'EH', 2), (2, 'UGODY', 1)):
            p = deepcopy(self.p)
            p['pracownicy'][indeks]['stawka'] += 10
            a, b = oblicz_model(self.p), oblicz_model(p)
            self.assertAlmostEqual(b['koszt_wynagrodzen_lifecycle'] - a['koszt_wynagrodzen_lifecycle'],
                                   a['role'][rola]['laczne_godziny_zasobu_lifecycle'] * 10 / liczba)
            self.assertEqual(a['koszt_narzutu_ogolnego_lifecycle'], b['koszt_narzutu_ogolnego_lifecycle'])
            self.assertEqual(a['ogolem']['przychod'], b['ogolem']['przychod'])

    def test_brak_wymaganej_stawki_nie_jest_zerem(self):
        for osoby in ([], [osoba('EH', 50)], [osoba('UGODY', 45)],
                      [osoba('EH', 50, 0), osoba('UGODY', 45)]):
            p = {**self.p, 'pracownicy': osoby}
            with self.subTest(osoby=osoby), self.assertRaisesRegex(ValueError, 'Brak stawki godzinowej wymaganej roli'):
                oblicz_model(p)
            self.assertEqual(oblicz_przeplyw(p)['bezposrednie_minuty_spraw'], 285367.5)
            self.assertEqual(oblicz_model_czasowy(p)['pojemnosc']['status_pojemnosci'], 'Niewystarczająca')

    def test_brak_stawki_nieblokujacej_roli_zero_pracy(self):
        p = {**self.p, 'kategoryczna_odmowa_percent': 100.0, 'automatyczne_ramy_percent': 0.0,
             'pracownicy': [osoba('EH', 50)]}
        r = oblicz_model(p)
        self.assertIsNone(r['stawki_wedlug_roli']['UGODY'])
        self.assertEqual(r['role']['UGODY']['laczne_godziny_zasobu_lifecycle'], 0)
        p = {**self.p, 'kategoryczna_odmowa_percent': 0.0, 'automatyczne_ramy_percent': 100.0,
             'skutecznosc_automatycznych_ram_percent': 100.0, 'pracownicy': [osoba('UGODY', 45)],
             'wspolne_czynnosci': {}, 'dodatkowe_minuty': {'P1': 0, 'P2': 0, 'P3': 0}}
        r = oblicz_model(p)
        self.assertIsNone(r['stawki_wedlug_roli']['EH'])
        self.assertAlmostEqual(r['koszt_wynagrodzen_lifecycle'], 600 * 55 / 60 * 480 / 450 * 45)

    def test_pusty_segment_z_niewycenialna_rola_ma_brak_wyceny(self):
        p = {**self.p, 'kategoryczna_odmowa_percent': 0.0, 'automatyczne_ramy_percent': 100.0,
             'skutecznosc_automatycznych_ram_percent': 100.0, 'pracownicy': [osoba('UGODY', 45)],
             'wspolne_czynnosci': {}, 'udzialy_rodzajow': {'P1': 100, 'P2': 0, 'P3': 0},
             'dodatkowe_minuty': {'P1': 0, 'P2': 0, 'P3': 90}}
        r = oblicz_model(p)
        for g in r['grupy']:
            if g['rodzaj'] == 'P3':
                self.assertIsNone(g['koszt_calkowity'])
                self.assertEqual(g['laczny_koszt_calkowity'], 0)

    def test_zero_naplywu_i_zero_osob_ma_jawny_brak_stawek(self):
        r = oblicz_model({**self.p, 'liczba_spraw': 0, 'pracownicy': []})
        self.assertEqual(r['stawki_wedlug_roli'], {'EH': None, 'UGODY': None})
        self.assertEqual(r['ogolem']['koszt_calkowity'], 0)
        self.assertEqual(r['ogolem']['przychod'], 0)

    def test_wynagrodzenie_timeline_indywidualne_nie_srednie(self):
        r = oblicz_model_czasowy(self.p)
        self.assertAlmostEqual(r['pojemnosc']['miesieczny_koszt_wynagrodzen'], 167 * (50 + .01 * 70 + 45))
        zmiana = deepcopy(self.p)
        zmiana['pracownicy'][1]['stawka'] += 10
        b = oblicz_model_czasowy(zmiana)
        self.assertAlmostEqual(b['pojemnosc']['miesieczny_koszt_wynagrodzen'] - r['pojemnosc']['miesieczny_koszt_wynagrodzen'], 167 * .01 * 10)

    def test_progi_plac_osobne_i_kopie_obsady_niezalezne(self):
        p = {**self.p, 'koszt_staly_na_godzine': 1.0}
        for indeks in (0, 1, 2):
            prog = oblicz_prog_wynagrodzenia_pracownika(p, indeks)
            self.assertTrue(prog['mozliwe'])
            po = ustaw_parametr(p, f'placa:{indeks}', prog['prog'])
            self.assertAlmostEqual(oblicz_model(po)['ogolem']['wynik_przed_podatkiem'], 0, places=6)
            self.assertNotEqual(p['pracownicy'][indeks]['stawka'], po['pracownicy'][indeks]['stawka'])
        kopia = kopiuj_parametry(p)
        kopia['pracownicy'][0]['stawka'] = 999
        self.assertEqual(p['pracownicy'][0]['stawka'], 50)

    def test_wartosc_minuty_jest_wlasciwa_dla_roli(self):
        p = {**self.p, 'podatek_dochodowy_percent': 0.0}
        bazowy = oblicz_model(p)
        for key, nazwa, rola, liczba_spraw in (('wspolne_czynnosci', 'Analiza sprawy i kompletowanie załącznika', 'EH', 600),
                                             ('ugodowe_czynnosci', 'Podpisanie ugody', 'UGODY', 600 * .2875)):
            zmiana = deepcopy(p)
            zmiana[key][nazwa] -= 1
            w = 60 if rola == 'EH' else 45
            mnoznik = 480 / (420 if rola == 'EH' else 450)
            self.assertAlmostEqual(bazowy['koszt_lifecycle_razem'] - oblicz_model(zmiana)['koszt_lifecycle_razem'],
                                   liczba_spraw / 60 * mnoznik * (w + 36))

    def test_ugody_porownuja_wlasciwe_stawki_i_mnozniki(self):
        porownanie = ekonomika_ugod(self.p)['porownania'][0]
        expected = (250 + 105) / 60 * 480 / 420 * (60 + 36) + (35 - 55) / 60 * 480 / 450 * (45 + 36)
        self.assertAlmostEqual(porownanie['Różnica PLN na sprawę'], expected)


class TestNiezaleznaRekonsyliacja(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.warianty = scenariusze()

    def test_scenariusze_A_G_nie_zmienily_przeplywow_po_naprawie_lifecycle(self):
        oczekiwane = {'A': -338578.75394139247, 'B': -2972228.455115,
                      'C': -1803737.4297, 'D': -488622.7422, 'E': -2403735.0297,
                      'F': -1903937.4297, 'G': -1903937.4297}
        for nazwa, wynik in oczekiwane.items():
            self.assertAlmostEqual(self.warianty[nazwa]['podsumowanie']['Wynik'], wynik, places=5)
        sprawdz_niezaleznosc(self.warianty)

    def test_punkty_kontrolne_i_pelne_skladniki(self):
        for w in self.warianty.values():
            self.assertEqual([r['Miesiąc'] for r in w['punkty_kontrolne']], [1, 6, 10, 16, 24, 36, 60])
            for row in w['punkty_kontrolne']:
                self.assertAlmostEqual(row['Koszt całkowity'], row['Wynagrodzenia EH'] + row['Wynagrodzenia ugód'] + row['Koszty ogólne'] + row['Sekretariat'])
                self.assertAlmostEqual(row['Wynik'], row['Przychód'] - row['Koszt całkowity'], places=6)
                self.assertAlmostEqual(row['Koszty ogólne'], row['Sprawomiesiące'] * w['koszty']['ogolne_na_aktywna_sprawe'], places=6)

    def test_c_dojrzaly_przeplyw_i_e_dodatkowa_osoba_nie_tworzy_pracy(self):
        c, e = self.warianty['C'], self.warianty['E']
        for w in (c, e):
            ostatni_rok = w['miesiace'][-12:]
            self.assertAlmostEqual(fsum(r['Przychód razem'] for r in ostatni_rok), 451963.254)
            self.assertAlmostEqual(fsum(r['Wykonana praca EH (h)'] * 60 for r in ostatni_rok), 259942.5)
            self.assertAlmostEqual(fsum(r['Wykonana praca UGODY (h)'] * 60 for r in ostatni_rok), 25425)
        self.assertEqual(c['podsumowanie']['Przychód'], e['podsumowanie']['Przychód'])
        self.assertEqual(c['podsumowanie']['Sprawomiesiące'], e['podsumowanie']['Sprawomiesiące'])


if __name__ == '__main__':
    unittest.main()
