"""Regresje wspólnego rachunku: pieniądze, jednorazowe zdarzenia i granice czasu."""

from math import fsum, isfinite
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from diagnostic_costs import uzgodnij
from model import oblicz_model, _skaluj_bezposrednie_czasy
from reconcile_shared_costs import referencyjne_parametry, sprawdz_referencje
from reconciliation import porownaj_panele
from timeline import oblicz_model_czasowy
from test_workflow import proste, osoba, zdarzenia_spraw


class TestReferencyjneKoszty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {r: sprawdz_referencje(referencyjne_parametry(r)) for r in (0., 10., 36., 60.)}
        cls.secretary = sprawdz_referencje(referencyjne_parametry(36., 30., 30.))

    def test_dokladne_kwoty_i_pochodne_ekonomiczne(self):
        cohort, timeline, amounts = self.results[36.]
        self.assertAlmostEqual(cohort['sredni_narzut_ogolny_na_sprawe'], 307.9125)
        self.assertAlmostEqual(amounts['koszt'], 492044.175)
        self.assertAlmostEqual(amounts['wynik'], -40080.921)
        self.assertAlmostEqual(cohort['wynagrodzenia_bezposrednie'] + cohort['wynagrodzenia_dzienne'], 307296.675)
        self.assertAlmostEqual(timeline['tabela_miesieczna'][-1]['Narzut od wspólnych czynności dziennych'], 1127.25)

    def test_narzut_nie_zmienia_harmonogramu_przychodow_ani_plac(self):
        base = self.results[0.][1]
        for rate, (_, timeline, amounts) in self.results.items():
            self.assertEqual(base['zdarzenia'], timeline['zdarzenia'])
            self.assertEqual(base['pojemnosc'], timeline['pojemnosc'])
            for a, b in zip(base['tabela_miesieczna'], timeline['tabela_miesieczna']):
                for column in a:
                    if not any(word in column.lower() for word in ('narzut', 'koszt', 'wynik')):
                        self.assertEqual(a[column], b[column], column)
            self.assertAlmostEqual(amounts['narzut'] - self.results[0.][2]['narzut'], rate * 5131.875)

    def test_dodatni_sekretariat_nie_dodaje_pracy_ani_plac(self):
        cohort, timeline, amounts = self.secretary
        self.assertAlmostEqual(cohort['koszt_sekretariatu_na_sprawe'], 15)
        self.assertAlmostEqual(amounts['sekretariat'], 9000)
        self.assertAlmostEqual(amounts['koszt'], 501044.175)
        self.assertAlmostEqual(amounts['wynik'], -49080.921)
        base = self.results[36.][1]
        self.assertEqual(base['pojemnosc'], timeline['pojemnosc'])
        for a, b in zip(base['tabela_miesieczna'], timeline['tabela_miesieczna']):
            for column in a:
                if not any(word in column.lower() for word in ('koszt', 'wynik')):
                    self.assertEqual(a[column], b[column])
        self.assertEqual([{k:v for k,v in e.items() if k != 'koszt'} for e in base['zdarzenia']],
                         [{k:v for k,v in e.items() if k != 'koszt'} for e in timeline['zdarzenia']])

    def test_miesieczne_inwarianty_i_skonczone_wartosci(self):
        for _, timeline, _ in [*self.results.values(), self.secretary]:
            cumulative = 0
            for row in timeline['tabela_miesieczna']:
                rate = timeline['koszty_kontraktu']['general_overhead_per_hour']
                direct = row['Wykonana praca EH (h)'] + row['Wykonana praca UGODY (h)']
                self.assertAlmostEqual(direct, row['Wykonana praca (h)'])
                self.assertAlmostEqual(row['Narzut od wykonanej pracy nad sprawami'], direct * rate)
                self.assertAlmostEqual(row['Narzut od wspólnych czynności dziennych'], row['Czynności dzienne (h)'] * rate)
                self.assertAlmostEqual(row['Narzut kosztów ogólnych razem'], (direct + row['Czynności dzienne (h)']) * rate)
                cost = row['Wynagrodzenia EH'] + row['Wynagrodzenia ugód'] + row['Narzut kosztów ogólnych razem'] + row['Jednorazowe koszty sekretariatu']
                self.assertAlmostEqual(cost, row['Łączny koszt miesięczny'])
                self.assertAlmostEqual(row['Wynik miesięczny przed podatkiem'], row['Przychód razem'] - cost)
                cumulative += row['Wynik miesięczny przed podatkiem']
                self.assertAlmostEqual(cumulative, row['Wynik skumulowany przed podatkiem'])
                self.assertTrue(all(isfinite(v) for v in row.values() if isinstance(v, (int, float))))

    def test_kazda_sciezka_i_instancja_ma_dokladnie_jeden_sekretariat(self):
        _, timeline, _ = self.secretary
        paths, outcomes = set(), set()
        for events in zdarzenia_spraw(timeline).values():
            started = [e for e in events if e['rodzaj'] == 'inicjacja' and e['etap'] == 'przyjecie']
            secretary = [e for e in events if e['rodzaj'] == 'SEKRETARIAT_OBSLUZONY']
            self.assertEqual(len(secretary), len(started))
            self.assertLessEqual(len(secretary), 1)
            if secretary:
                self.assertEqual(secretary[0]['miesiac'], started[0]['miesiac'])
                self.assertAlmostEqual(secretary[0]['koszt'], 15 * secretary[0]['waga'])
                paths.add(secretary[0]['sciezka'])
                outcomes.add(secretary[0]['wynik'])
        self.assertEqual(len(paths), 6)
        self.assertEqual(outcomes, {'ugoda', 'i', 'ii'})


class TestZdarzeniaIKolejkiKosztow(unittest.TestCase):
    def simulate(self, p, horizon=12, **time):
        p = {**p, 'sekretariat_minuty_na_sprawe': 30., 'koszt_sekretariatu_na_godzine': 30.}
        result = oblicz_model_czasowy(p, {'horyzont_miesiace': horizon, **time}, zapisz_zdarzenia=True)
        uzgodnij(p, result)
        return result

    def test_kolejka_przed_przyjeciem_nie_generuje_sekretariatu(self):
        p = proste(24, proces=0, przyjecie=60)
        p['pracownicy'] = [osoba('EH', 1)]
        result = self.simulate(p, 3)
        for row in result['tabela_miesieczna']:
            self.assertEqual(row['Nowe sprawy'], 2)
            self.assertEqual(row['Sprawy z jednorazową obsługą sekretariatu'], 1)
            self.assertEqual(row['Jednorazowe koszty sekretariatu'], 15)
        self.assertEqual(result['podsumowanie']['backlog_koniec_godziny'], 3)

    def test_zero_minut_przyjecia_i_brak_roli_sa_jawne(self):
        p = proste(proces=0)
        result = self.simulate(p, 1)
        row = result['tabela_miesieczna'][0]
        self.assertEqual(row['Wykonana praca (h)'], 0)
        self.assertEqual(row['Narzut kosztów ogólnych razem'], 0)
        self.assertEqual(row['Jednorazowe koszty sekretariatu'], 15)
        for staff in ([], [osoba('UGODY')], [osoba('EH', 0)]):
            p['pracownicy'] = staff
            result = self.simulate(p, 1)
            self.assertEqual(result['zdarzenia'], [])
            self.assertEqual(result['tabela_miesieczna'][0]['Jednorazowe koszty sekretariatu'], 0)

    def test_zero_jednego_parametru_sekretariatu(self):
        for minutes, rate in ((0., 30.), (30., 0.)):
            p = referencyjne_parametry(36., minutes, rate)
            result = oblicz_model_czasowy(p, {'horyzont_miesiace': 12}, zapisz_zdarzenia=True)
            uzgodnij(p, result)
            self.assertEqual(oblicz_model(p)['koszt_sekretariatu_na_sprawe'], 0)
            self.assertEqual(sum(r['Jednorazowe koszty sekretariatu'] for r in result['tabela_miesieczna']), 0)
            self.assertTrue(any(e['rodzaj'] == 'SEKRETARIAT_OBSLUZONY' for e in result['zdarzenia']))

    def test_podzial_pracy_na_miesiace_nie_mnozy_narzutu(self):
        p = proste(proces=600, przyjecie=0)
        for available in (6., 167.):
            p['pracownicy'] = [osoba('EH', available)]
            result = self.simulate(p, 4)
            events = zdarzenia_spraw(result)[0]
            hours = fsum(e['minuty'] for e in events if e['rodzaj'] == 'praca') / 60
            self.assertAlmostEqual(hours, 10)
            self.assertAlmostEqual(hours * 36, 360)
            self.assertEqual(fsum(e['koszt'] for e in events), 15)
        p['pracownicy'] = [osoba('EH', 6.)]
        rows = self.simulate(p, 2)['tabela_miesieczna']
        self.assertEqual([r['Narzut od wykonanej pracy nad sprawami'] for r in rows], [216, 216])
        # W drugim miesiącu 4 h kończą pierwszą sprawę, 2 h zaczynają następną.

    def test_formalne_czekanie_i_platnosci_nie_powtarzaja_kosztow(self):
        p = proste(proces=6)
        a = self.simulate(p, 24, miesiace_do_wyroku_i=0)
        b = self.simulate(p, 24, miesiace_do_wyroku_i=12, opoznienie_platnosci_miesiace=6)
        self.assertEqual(a['zdarzenia'][:4], b['zdarzenia'][:4])
        for x, y in zip(a['tabela_miesieczna'], b['tabela_miesieczna']):
            for col in ('Narzut kosztów ogólnych razem', 'Jednorazowe koszty sekretariatu', 'Miesięczny koszt wynagrodzeń'):
                self.assertEqual(x[col], y[col])
        self.assertLess(b['podsumowanie_finansowe']['Przychód razem'], a['podsumowanie_finansowe']['Przychód razem'])

    def test_zero_pracy_dzienne_rzeczywiste_i_niewykonane(self):
        p = _skaluj_bezposrednie_czasy(referencyjne_parametry(), 0)
        row = self.simulate(p, 1)['tabela_miesieczna'][0]
        self.assertEqual(row['Narzut od wykonanej pracy nad sprawami'], 0)
        self.assertEqual(row['Narzut od wspólnych czynności dziennych'], 1127.25)
        p['pracownicy'] = [osoba('EH', 10)]
        row = self.simulate(p, 1)['tabela_miesieczna'][0]
        self.assertEqual(row['Narzut od wspólnych czynności dziennych'], 360)
        self.assertEqual(row['Niewykonane czynności dzienne (h)'], 21.3125)
        p['pracownicy'] = [osoba('UGODY')]
        row = self.simulate(p, 1)['tabela_miesieczna'][0]
        self.assertEqual(row['Czynności dzienne (h)'], 0)
        self.assertEqual(row['Narzut kosztów ogólnych razem'], 0)
        self.assertEqual(row['Jednorazowe koszty sekretariatu'], 0)

    def test_stara_sekcja_toml_nie_moze_dodac_drugiego_kosztu(self):
        import config
        source = config.DEFAULTS_PATH.read_text()
        self.assertNotIn('koszty_kontraktu', config.wczytaj_defaults())
        with TemporaryDirectory() as directory:
            path = Path(directory, 'defaults.toml')
            for value in (0., 43.):
                path.write_text(source + f'\n[koszty_kontraktu]\nogolne_na_aktywna_sprawe = {value}\n')
                with patch.object(config, 'DEFAULTS_PATH', path):
                    if value:
                        with self.assertRaisesRegex(ValueError, 'Wycofany koszt'):
                            config.wczytaj_defaults()
                    else:
                        self.assertEqual(config.parametry_modelu()['koszt_staly_na_godzine'], 36)

    def test_diagnostyka_wyjasnia_pensje_okres_i_brak_stawki(self):
        for horizon in (6, 120):
            p = referencyjne_parametry()
            p['pracownicy'][2]['wykorzystanie_percent'] = 100
            p['pracownicy'][2]['stawka'] = 100
            result = self.simulate(p, horizon)
            p.update(sekretariat_minuty_na_sprawe=30., koszt_sekretariatu_na_godzine=30.)
            diagnostic = porownaj_panele(p, result)
            salary = next(r for r in diagnostic['pozycje'] if r['Pozycja'] == 'Wynagrodzenia (zł)')
            self.assertAlmostEqual(sum(diagnostic['roznica_plac_skladniki'].values()), salary['Różnica'])
            self.assertTrue(any('płatności' in text for text in diagnostic['wyjasnienia']))
        p['pracownicy'] = []
        diagnostic = porownaj_panele(p, self.simulate(p, 1))
        self.assertIsNone(diagnostic['roznica_plac_skladniki'])


if __name__ == '__main__':
    unittest.main()
