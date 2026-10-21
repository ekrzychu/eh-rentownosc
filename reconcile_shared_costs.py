"""Akceptacja finansowa: roczna kohorta i wyłącznie miesiące 109–120 kontraktu.

Dokładne przydziały pochodzą z niezależnych referencyjnych godzin, bez
zaokrąglania procentów. Kwoty są sprawdzane z tolerancją 0,01 zł.
"""

import json
from math import fsum, isclose
from pathlib import Path
import argparse

from diagnostic_costs import uzgodnij
from model import domyslne_parametry, oblicz_model
from timeline import oblicz_model_czasowy
from reconciliation import porownaj_panele


def referencyjne_parametry(rate=36., minutes=0., secretary_rate=0.):
    p = domyslne_parametry()
    p.update(koszt_staly_na_godzine=rate, sekretariat_minuty_na_sprawe=minutes,
             koszt_sekretariatu_na_godzine=secretary_rate)
    p['pracownicy'] = [
        {'rola': role, 'stawka': 59.88, 'wykorzystanie_percent': allocation}
        for role, allocation in (
            ('EH', 100.), ('EH', 100.),
            ('EH', ((4414.875 / 12 + 375.75 / 12 - 334) / 167) * 100),
            ('UGODY', (341.25 / 12 / 167) * 100),
        )
    ]
    p['liczba_pracownikow'] = len(p['pracownicy'])
    return p


def sprawdz_referencje(p):
    cohort = oblicz_model(p)
    timeline = oblicz_model_czasowy(p, {'horyzont_miesiace': 120}, zapisz_zdarzenia=True)
    uzgodnij(p, timeline)
    diagnostic = porownaj_panele(p, timeline)
    for row in diagnostic['pozycje']:
        assert row['Różnica'] is not None and abs(row['Różnica']) < .01, row
    rows = timeline['tabela_miesieczna'][-12:]
    total = lambda col: fsum(r[col] for r in rows)
    expected_overhead = 5131.875 * p['koszt_staly_na_godzine']
    expected_secretary = 600 * p['sekretariat_minuty_na_sprawe'] / 60 * p['koszt_sekretariatu_na_godzine']
    expected_cost = 307296.675 + expected_overhead + expected_secretary
    amounts = {
        'przychod': (total('Przychód razem'), 451963.254),
        'place': (total('Wynagrodzenia EH') + total('Wynagrodzenia ugód'), 307296.675),
        'narzut': (total('Narzut kosztów ogólnych razem'), expected_overhead),
        'sekretariat': (total('Jednorazowe koszty sekretariatu'), expected_secretary),
        'koszt': (total('Łączny koszt miesięczny'), expected_cost),
        'wynik': (total('Wynik miesięczny przed podatkiem'), 451963.254 - expected_cost),
        'EH_h': (total('Wykonana praca EH (h)'), 4414.875),
        'UGODY_h': (total('Wykonana praca UGODY (h)'), 341.25),
        'dzienne_h': (total('Czynności dzienne (h)'), 375.75),
        'zakonczone': (sum(total(k) for k in ('Ugody zakończone', 'Zakończenia po I instancji', 'Zakończenia po II instancji')), 600),
    }
    for name, (actual, expected) in amounts.items():
        assert isclose(actual, expected, rel_tol=0, abs_tol=.01), (name, actual, expected)
    assert timeline['podsumowanie']['dojrzalosc_osiagnieta']
    assert timeline['podsumowanie']['backlog_koniec_godziny'] < 1e-6
    return cohort, timeline, {k: actual for k, (actual, _) in amounts.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = {}
    for rate in (0., 10., 36., 60.):
        _, _, amounts = sprawdz_referencje(referencyjne_parametry(rate))
        report[f'{rate:g} PLN/h'] = amounts
    _, _, amounts = sprawdz_referencje(referencyjne_parametry(36., 30., 30.))
    report['36 PLN/h + sekretariat 15 PLN/sprawę'] = amounts
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    print(rendered)
    if args.output:
        args.output.write_text(rendered)


if __name__ == '__main__':
    main()
