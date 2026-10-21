"""Powtarzalny niezależny audyt bilansów i pomiar czasu 60/120/360 miesięcy."""

import json
from math import isclose
from pathlib import Path
from random import Random
from time import perf_counter

from diagnostic_costs import niezalezne_minuty_roczne, uzgodnij
from model import domyslne_parametry, _skaluj_bezposrednie_czasy
from timeline import oblicz_model_czasowy


def main():
    rng = Random(19102026)
    for scenario in range(40):
        p = domyslne_parametry()
        p.update(liczba_spraw=rng.randrange(0, 1000),
                 udzial_ii_instancji_percent=rng.choice([0., 50., 100.]))
        p['pracownicy'] = [{'rola': rng.choice(['EH', 'UGODY']), 'stawka': rng.randrange(0, 120),
                          'wykorzystanie_percent': rng.choice([0., 15., 60., 100.])}
                         for _ in range(rng.randrange(0, 9))]
        daily = rng.choice([0, 90, 480])
        p['codzienne_czynnosci'] = {'Obsługa skrzynki ugody EH': daily}
        p = _skaluj_bezposrednie_czasy(p, rng.choice([0, .5, 1, 2]))
        p.update(koszt_staly_na_godzine=rng.randrange(0, 80),
                 sekretariat_minuty_na_sprawe=rng.randrange(0, 90),
                 koszt_sekretariatu_na_godzine=rng.randrange(0, 80))
        horizon = rng.randrange(12, 60)
        result = oblicz_model_czasowy(p, {'horyzont_miesiace': horizon,
            'miesiace_do_ugody': rng.randrange(0, 30), 'miesiace_do_wyroku_i': rng.randrange(0, 30),
            'miesiace_wyrok_i_do_ii': rng.randrange(0, 20), 'opoznienie_platnosci_miesiace': rng.randrange(0, 12)},
            zapisz_zdarzenia=True)
        uzgodnij(p, result)
        w = result['walidacja']
        expected = sum(niezalezne_minuty_roczne(p).values()) * horizon / 12
        assert isclose(w['praca_wykonana_minuty'] + w['backlog_minuty'] + w['praca_przyszla_minuty'], expected, abs_tol=1e-5)
    print('40 scenariuszy: niezależne bilanse kosztów, spraw, zdarzeń i minut — OK')
    timings = []
    for name in ('Przeciążenie EH', 'Stabilny operacyjnie', 'Brak pracowników'):
        for horizon in (60, 120, 360):
            p = domyslne_parametry()
            if name == 'Stabilny operacyjnie':
                p['pracownicy'] = [dict(p['pracownicy'][0]) for _ in range(3)] + [p['pracownicy'][1]]
            elif name == 'Brak pracowników':
                p['pracownicy'] = []
            start = perf_counter()
            result = oblicz_model_czasowy(p, {'horyzont_miesiace': horizon})
            elapsed = perf_counter() - start
            timings.append({'Wariant': name, 'Miesiące': horizon, 'Sekundy': elapsed,
                            'Backlog (h)': result['podsumowanie']['backlog_koniec_godziny'],
                            'Przyszła praca (h)': result['walidacja']['praca_przyszla_minuty'] / 60,
                            'Status': result['kpi']['status_kontraktu']})
            print(f'{name}, {horizon} mies.: {elapsed:.3f} s')
    Path('audit_results/wydajnosc.json').write_text(json.dumps(timings, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
