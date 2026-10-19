"""Niezależny bilans dziesięciu scenariuszy i porównanie ze starym modelem.

Nie wywołuje pomocników kosztów, pojemności, etapów ani kolejek modelu.
Podstawę opłat odtwarza ze zbioru identyfikatorów dodatniej pracy w dzienniku.
To audyt arytmetyczny i zdarzeniowy, nie drugi symulator harmonogramu.
"""

import argparse
import csv
import json
from math import fsum, isclose
from pathlib import Path
from time import perf_counter

from model import domyslne_parametry, _skaluj_bezposrednie_czasy
from timeline import oblicz_model_czasowy

MIESIACE_KONTROLI = (12, 24, 60)


def sprawdz(a, b, opis):
    if not isclose(a, b, rel_tol=1e-10, abs_tol=1e-6):
        raise AssertionError(f"{opis}: {a} != {b}")


def niezalezne_minuty_roczne(p):
    odmowa = p['kategoryczna_odmowa_percent'] / 100
    ramy = p['automatyczne_ramy_percent'] / 100
    sukces_ram = p['skutecznosc_automatycznych_ram_percent'] / 100
    szansa = p['szansa_na_ugode_percent'] / 100
    sukces_poza = p['zawarte_ugody_percent'] / 100
    reszta = 1 - odmowa - ramy
    ugody = ramy * sukces_ram + reszta * szansa * sukces_poza
    proby = ramy * (1 - sukces_ram) + reszta * szansa * (1 - sukces_poza)
    eh = (fsum(p['wspolne_czynnosci'].values())
          + reszta * (1 - szansa) * p['analiza_mozliwosci_ugody']
          + (1 - ugody) * fsum(p['procesowe_czynnosci'].values())
          + fsum(p['udzialy_rodzajow'][k] / 100 * v for k, v in p['dodatkowe_minuty'].items())
          + (1 - ugody) * p['udzial_ii_instancji_percent'] / 100 * p['obsluga_ii_instancji_minuty'])
    ug = (ugody * fsum(p['ugodowe_czynnosci'].values())
          + proby * fsum(p['ugodowe_czynnosci'].get(k, 0) for k in ('Oferta ugody', 'Projekt ugody'))
          + reszta * szansa * p['analiza_mozliwosci_ugody'])
    return {'EH': p['liczba_spraw'] * eh, 'UGODY': p['liczba_spraw'] * ug}


def uzgodnij(p, koszty, wynik):
    osoby = p['pracownicy']
    pensje = {r: fsum(167 * o['wykorzystanie_percent'] / 100 * o['stawka']
                      for o in osoby if o['rola'] == r) for r in ('EH', 'UGODY')}
    brutto = {r: fsum(167 * o['wykorzystanie_percent'] / 100
                      for o in osoby if o['rola'] == r) for r in pensje}
    dzienne_wymagane = fsum(p['codzienne_czynnosci'].values()) / 60 * 167 / 8
    jedna_osoba = max((167 * o['wykorzystanie_percent'] / 100
                      for o in osoby if o['rola'] == 'EH'), default=0)
    dzienne = min(dzienne_wymagane, jedna_osoba)
    pojemnosc = {'EH': brutto['EH'] - dzienne, 'UGODY': brutto['UGODY']}
    praca_roczna = niezalezne_minuty_roczne(p)
    prace_miesiaca, minuty_miesiaca = {}, {}
    for event in wynik['zdarzenia']:
        if event['rodzaj'] == 'praca':
            if event['minuty'] <= 0:
                raise AssertionError('Zdarzenie pracy bez dodatnich minut')
            prace_miesiaca.setdefault(event['miesiac'], {})[event['sprawa']] = event['waga']
            klucz = (event['miesiac'], event['rola'])
            minuty_miesiaca[klucz] = minuty_miesiaca.get(klucz, 0) + event['minuty']
    if not wynik['zdarzenia'] and any(r['Wykonana praca (h)'] > 0 for r in wynik['tabela_miesieczna']):
        raise AssertionError('Audyt wymaga zapisu zdarzeń')
    naplyw = zakonczone = sprawomiesiace = przychod = saldo = 0.0
    praca = {'EH': 0.0, 'UGODY': 0.0}
    konce = {'ugoda': 0.0, 'i': 0.0, 'ii': 0.0}
    miesiace = []
    for row in wynik['tabela_miesieczna']:
        m = row['Miesiąc']
        podstawa = fsum(prace_miesiaca.get(m, {}).values())
        sprawdz(row['Sprawy, nad którymi pracowano w miesiącu'], podstawa, 'Unikalne sprawy z dodatnią pracą')
        sprawomiesiace += podstawa
        naplyw += p['liczba_spraw'] / 12
        for k, col in (('ugoda', 'Ugody zakończone'), ('i', 'Zakończenia po I instancji'), ('ii', 'Zakończenia po II instancji')):
            konce[k] += row[col]
        zakonczone = fsum(konce.values())
        sprawdz(row['Sprawy otwarte'], naplyw - zakonczone, 'Stan zamknięcia')
        narzut_m = podstawa * koszty['ogolne_na_aktywna_sprawe']
        sekretariat_m = podstawa * koszty['sekretariat_na_aktywna_sprawe']
        koszt_m = pensje['EH'] + pensje['UGODY'] + narzut_m + sekretariat_m
        for key, val in (('Wynagrodzenia EH', pensje['EH']), ('Wynagrodzenia ugód', pensje['UGODY']),
                         ('Koszty ogólne spraw, nad którymi pracowano', narzut_m),
                         ('Koszt sekretariatu spraw, nad którymi pracowano', sekretariat_m), ('Łączny koszt miesięczny', koszt_m),
                         ('Czynności dzienne (h)', dzienne), ('Niewykonane czynności dzienne (h)', dzienne_wymagane - dzienne)):
            sprawdz(row[key], val, key)
        przychod += row['Przychód z ugód'] + row['Przychód z wyroków']
        saldo += row['Przychód razem'] - koszt_m
        sprawdz(saldo, row['Wynik skumulowany przed podatkiem'], 'Wynik skumulowany')
        przyszla = {}
        for r in pensje:
            wykonana = row[f'Wykonana praca {r} (h)']
            sprawdz(wykonana * 60, minuty_miesiaca.get((m, r), 0), f'Dziennik pracy {r}')
            if wykonana > pojemnosc[r] + 1e-7:
                raise AssertionError(f'Przekroczona pojemność {r}')
            praca[r] += wykonana
            przyszla[r] = m * praca_roczna[r] / 12 / 60 - praca[r] - row[f'Backlog {r} (h)']
            if przyszla[r] < -1e-6:
                raise AssertionError(f'Utracona praca {r}')
        sprawdz(fsum(przyszla.values()), row['Praca przyszła i zablokowana (h)'], 'Przyszła praca')
        narzut = sprawomiesiace * koszty['ogolne_na_aktywna_sprawe']
        sekretariat = sprawomiesiace * koszty['sekretariat_na_aktywna_sprawe']
        koszt = m * fsum(pensje.values()) + narzut + sekretariat
        sprawdz(przychod - koszt, saldo, 'Przychód minus wszystkie składniki')
        miesiace.append({'Miesiąc': m, 'Nowe sprawy łącznie': naplyw, 'Zakończone sprawy': zakonczone,
            'Sprawy otwarte': naplyw - zakonczone, 'Sprawy oczekujące na pracę': row['Sprawy oczekujące na pracę'],
            'Sprawy, nad którymi pracowano w miesiącu': podstawa,
            'Sprawy oczekujące na formalne zakończenie': row['Sprawy oczekujące na formalne zakończenie'],
            'Sprawomiesiące faktycznej pracy': sprawomiesiace,
            'Zakończone ugodą': konce['ugoda'], 'Zakończone w I instancji': konce['i'], 'Zakończone w II instancji': konce['ii'],
            'Praca EH (h)': praca['EH'], 'Praca ugód (h)': praca['UGODY'], 'Czynności dzienne (h)': m * dzienne,
            'Przychód': przychod, 'Wynagrodzenia EH': m * pensje['EH'], 'Wynagrodzenia ugód': m * pensje['UGODY'],
            'Koszty ogólne': narzut, 'Sekretariat': sekretariat, 'Koszt całkowity': koszt, 'Wynik': saldo,
            'Backlog EH (h)': row['Backlog EH (h)'], 'Backlog ugód (h)': row['Backlog UGODY (h)'],
            'Przyszła i zablokowana praca (h)': fsum(przyszla.values())})
    return miesiace


def scenariusze():
    warianty = {}
    for s in range(1, 11):
        p = domyslne_parametry()
        eh = 1 if s in (1, 2, 9, 10) else 0 if s == 8 else 3
        ug = 0 if s == 7 else 1
        p['pracownicy'] = [{'rola': r, 'stawka': p['pracownicy'][0]['stawka'], 'wykorzystanie_percent': 100.0}
                           for r in ['EH'] * eh + ['UGODY'] * ug]
        if s == 4:
            p['codzienne_czynnosci'] = {k: 0 for k in p['codzienne_czynnosci']}
        if s in (6, 9):
            p = _skaluj_bezposrednie_czasy(p, .5 if s == 6 else 0)
        costs = {'ogolne_na_aktywna_sprawe': 0.0 if s == 1 else 43.0, 'sekretariat_na_aktywna_sprawe': 0.0}
        start = perf_counter()
        wynik = oblicz_model_czasowy(p, zapisz_zdarzenia=True, koszty_kontraktu=costs)
        elapsed = perf_counter() - start
        miesiace = uzgodnij(p, costs, wynik)
        warianty[str(s)] = {'parametry': p, 'koszty': costs, 'podsumowanie': miesiace[-1],
                          'punkty_kontrolne': [m for m in miesiace if m['Miesiąc'] in MIESIACE_KONTROLI],
                          'czas_obliczen_s': elapsed, 'status': wynik['kpi']['status_kontraktu'],
                          'miesiace': wynik['tabela_miesieczna']}
    return warianty


def sprawdz_niezaleznosc(warianty):
    a, b = warianty['2'], warianty['1']
    for x, y in zip(a['miesiace'], b['miesiace']):
        for key in x:
            if not any(word in key for word in ('Koszt', 'koszt', 'Wynik')) and x[key] != y[key]:
                raise AssertionError(f'Narzut zmienił przepływy: {key}')
    sprawdz(a['podsumowanie']['Wynik'] - b['podsumowanie']['Wynik'],
            -43 * a['podsumowanie']['Sprawomiesiące faktycznej pracy'], 'Różnica wyniku równa opłacie')


def porownaj_stary_model(warianty):
    baseline = json.loads(Path(__file__).with_name('audit_results').joinpath('stary_model_99a2f1e.json').read_text())
    comparisons = {}
    for s in ('2', '3', '10'):
        old = baseline['scenariusze'][s]['miesiace']
        new = warianty[s]['miesiace']
        snapshots = []
        for m in MIESIACE_KONTROLI:
            a, b = old[:m], new[:m]
            old_result = a[-1]['Wynik skumulowany przed podatkiem']
            new_result = b[-1]['Wynik skumulowany przed podatkiem']
            old_open_months = fsum(r['Sprawy naliczające koszt w miesiącu'] for r in a)
            new_open_months = fsum(r['Sprawy otwarte'] + r['Ugody zakończone']
                                  + r['Zakończenia po I instancji'] + r['Zakończenia po II instancji'] for r in b)
            new_worked = fsum(r['Sprawy, nad którymi pracowano w miesiącu'] for r in b)
            salary_delta = fsum(r['Miesięczny koszt wynagrodzeń'] for r in b) - fsum(r['Miesięczny koszt wynagrodzeń'] for r in a)
            revenue_delta = fsum(r['Przychód razem'] for r in b) - fsum(r['Przychód razem'] for r in a)
            timeline_charge_delta = -43 * (new_open_months - old_open_months)
            rule_delta = 43 * (new_open_months - new_worked)
            sprawdz(new_result - old_result, -salary_delta + revenue_delta + timeline_charge_delta + rule_delta, 'Most starego i nowego wyniku')
            snapshots.append({'Miesiąc': m, 'Stary wynik': old_result, 'Nowy wynik': new_result,
                'Różnica wyniku': new_result - old_result, 'Zmiana kosztu pensji': salary_delta,
                'Zmiana przychodu przez harmonogram': revenue_delta,
                'Zmiana opłat otwartych przez harmonogram': timeline_charge_delta,
                'Zmiana reguły z otwartych na pracowane': rule_delta,
                'Stare otwarte sprawomiesiące': old_open_months, 'Nowe otwarte sprawomiesiące': new_open_months,
                'Nowe sprawomiesiące pracy': new_worked,
                'Stare zakończenia': fsum(r['Ugody zakończone'] + r['Zakończenia po I instancji'] + r['Zakończenia po II instancji'] for r in a),
                'Nowe zakończenia': fsum(r['Ugody zakończone'] + r['Zakończenia po I instancji'] + r['Zakończenia po II instancji'] for r in b),
                'Stare sprawy otwarte': a[-1]['Aktywne sprawy'],
                'Nowe sprawy otwarte': b[-1]['Sprawy otwarte'],
                'Stary backlog EH (h)': a[-1]['Backlog EH (h)'],
                'Nowy backlog EH (h)': b[-1]['Backlog EH (h)'],
                'Stary backlog ugód (h)': a[-1]['Backlog UGODY (h)'],
                'Nowy backlog ugód (h)': b[-1]['Backlog UGODY (h)'],
                'Stare czynności dzienne (h)': fsum(r['Czynności dzienne (h)'] for r in a),
                'Nowe czynności dzienne (h)': fsum(r['Czynności dzienne (h)'] for r in b),
                'Stara pojemność EH (h/mies.)': a[-1]['Pojemność EH (h)'],
                'Nowa pojemność EH (h/mies.)': b[-1]['Pojemność EH (h)'],
                'Stara pojemność ugód (h/mies.)': a[-1]['Pojemność UGODY (h)'],
                'Nowa pojemność ugód (h/mies.)': b[-1]['Pojemność UGODY (h)'],
                'Pierwsze miesiące starego modelu': {col: next((r['Miesiąc'] for r in a if r[col] > 0), None)
                    for col in ('Ugody zakończone', 'Zakończenia po I instancji', 'Zakończenia po II instancji', 'Przychód razem')},
                'Pierwsze miesiące nowego modelu': {col: next((r['Miesiąc'] for r in b if r[col] > 0), None)
                    for col in ('Ugody zakończone', 'Zakończenia po I instancji', 'Zakończenia po II instancji', 'Przychód razem')}})
        comparisons[s] = snapshots
    return comparisons


def zapisz(warianty, katalog):
    katalog.mkdir(parents=True, exist_ok=True)
    (katalog / 'rekonsyliacja.json').write_text(json.dumps(warianty, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    (katalog / 'porownanie_stary_nowy.json').write_text(json.dumps(porownaj_stary_model(warianty), ensure_ascii=False, indent=2) + '\n')
    with (katalog / 'rekonsyliacja.csv').open('w', newline='') as plik:
        writer = csv.DictWriter(plik, fieldnames=['Scenariusz', *warianty['1']['podsumowanie']], lineterminator='\n')
        writer.writeheader()
        writer.writerows({'Scenariusz': n, **row} for n, w in warianty.items() for row in w['punkty_kontrolne'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, help='Katalog raportów JSON i CSV')
    args = parser.parse_args()
    wyniki = scenariusze()
    sprawdz_niezaleznosc(wyniki)
    for nazwa, wynik in wyniki.items():
        for w in wynik['punkty_kontrolne']:
            print(f"{nazwa}/{w['Miesiąc']} mies.: wynik {w['Wynik']:.6f} zł; przychód {w['Przychód']:.6f} zł; "
                  f"sprawomiesiące pracy {w['Sprawomiesiące faktycznej pracy']:.6f}; zakończenia {w['Zakończone sprawy']:.6f}")
    print('Uzgodnienie składników, zdarzeń pracy, niezmienności przepływów i godzin ról: OK')
    if args.output_dir:
        zapisz(wyniki, args.output_dir)


if __name__ == '__main__':
    main()
