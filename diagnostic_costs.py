"""Niezależne uzgodnienie finansów A–G; nie wylicza ponownie harmonogramu pracy.

Koszty, podstawę opłat, saldo spraw i całą pracę odtwarza ze wzorów wejściowych
oraz zaobserwowanych przepływów miesięcznych, bez pomocników finansowych modelu.
"""

import argparse
import csv
import json
from math import fsum, isclose
from pathlib import Path

from model import domyslne_parametry, oblicz_model
from staff import nowy_pracownik
from timeline import oblicz_model_czasowy

MIESIACE_KONTROLI = (1, 6, 10, 16, 24, 36, 60)


def sprawdz(a, b, opis):
    if not isclose(a, b, rel_tol=1e-10, abs_tol=1e-6):
        raise AssertionError(f"{opis}: {a} != {b}")


def niezalezne_minuty_roczne(p):
    """Bez wywoływania funkcji ścieżek, pakietów i pojemności modelu."""
    odmowa = p['kategoryczna_odmowa_percent'] / 100
    ramy = p['automatyczne_ramy_percent'] / 100
    sukces_ram = p['skutecznosc_automatycznych_ram_percent'] / 100
    szansa = p['szansa_na_ugode_percent'] / 100
    sukces_poza = p['zawarte_ugody_percent'] / 100
    reszta = 1 - odmowa - ramy
    ugody = ramy * sukces_ram + reszta * szansa * sukces_poza
    proby = ramy * (1 - sukces_ram) + reszta * szansa * (1 - sukces_poza)
    eh = (sum(p['wspolne_czynnosci'].values())
          + (1 - ugody) * sum(p['procesowe_czynnosci'].values())
          + sum(p['udzialy_rodzajow'][k] / 100 * v for k, v in p['dodatkowe_minuty'].items())
          + (1 - ugody) * p['udzial_ii_instancji_percent'] / 100 * p['obsluga_ii_instancji_minuty'])
    ug = (ugody * sum(p['ugodowe_czynnosci'].values())
          + proby * sum(p['ugodowe_czynnosci'].get(k, 0) for k in ('Oferta ugody', 'Projekt ugody'))
          + reszta * p['analiza_mozliwosci_ugody'])
    return {'EH': p['liczba_spraw'] * eh, 'UGODY': p['liczba_spraw'] * ug}


def uzgodnij(p, koszty, wynik):
    """Odtwarza każdy miesiąc, nie używając podsumowania finansowego timeline."""
    osoby = p['pracownicy']
    pensje = {r: fsum(167 * o['wykorzystanie_percent'] / 100 * o['stawka']
                      for o in osoby if o['rola'] == r) for r in ('EH', 'UGODY')}
    dzienne = p['codzienne_czynnosci']
    minuty_dnia = {'EH': sum(dzienne.get(k, 0) for k in (
        'Komunikacja z EH i zlecanie opłat w SOSS', 'Umieszczanie dokumentów w SOSS')),
        'UGODY': dzienne.get('Obsługa skrzynki ugody EH', 0)}
    pojemnosc = {r: fsum(167 * o['wykorzystanie_percent'] / 100 * (1 - minuty_dnia[r] / 480)
                         for o in osoby if o['rola'] == r) for r in pensje}
    praca_roczna = niezalezne_minuty_roczne(p)
    naplyw = zakonczone = sprawomiesiace = przychod = saldo = 0.0
    praca = {'EH': 0.0, 'UGODY': 0.0}
    miesiace = []
    for row in wynik['tabela_miesieczna']:
        m = row['Miesiąc']
        podstawa = naplyw - zakonczone + p['liczba_spraw'] / 12
        sprawdz(row['Sprawy naliczające koszt w miesiącu'], podstawa, 'Podstawa opłat')
        sprawomiesiace += podstawa
        naplyw += p['liczba_spraw'] / 12
        zakonczone += sum(row[k] for k in ('Ugody zakończone', 'Zakończenia po I instancji', 'Zakończenia po II instancji'))
        sprawdz(row['Aktywne sprawy na koniec miesiąca'], naplyw - zakonczone, 'Stan zamknięcia')
        narzut_m = podstawa * koszty['ogolne_na_aktywna_sprawe']
        sekretariat_m = podstawa * koszty['sekretariat_na_aktywna_sprawe']
        koszt_m = pensje['EH'] + pensje['UGODY'] + narzut_m + sekretariat_m
        for key, val in (('Koszt wynagrodzeń EH', pensje['EH']), ('Koszt wynagrodzeń ugód', pensje['UGODY']),
                         ('Koszty ogólne aktywnych spraw', narzut_m),
                         ('Koszt sekretariatu aktywnych spraw', sekretariat_m), ('Łączny koszt miesięczny', koszt_m)):
            sprawdz(row[key], val, key)
        przychod += row['Przychód z ugód'] + row['Przychód z wyroków']
        saldo += row['Przychód razem'] - koszt_m
        sprawdz(saldo, row['Wynik skumulowany przed podatkiem'], 'Wynik skumulowany')
        przyszla = {}
        for r in pensje:
            wykonana = row[f'Wykonana praca {r} (h)']
            if wykonana > pojemnosc[r] + 1e-7:
                raise AssertionError(f'Przekroczona pojemność {r}')
            praca[r] += wykonana
            przyszla[r] = m * praca_roczna[r] / 12 / 60 - praca[r] - row[f'Backlog {r} (h)']
            if przyszla[r] < -1e-6:
                raise AssertionError(f'Utracona praca {r}')
        narzut = sprawomiesiace * koszty['ogolne_na_aktywna_sprawe']
        sekretariat = sprawomiesiace * koszty['sekretariat_na_aktywna_sprawe']
        koszt = m * (pensje['EH'] + pensje['UGODY']) + narzut + sekretariat
        sprawdz(przychod - koszt, saldo, 'Przychód minus wszystkie składniki')
        miesiace.append({'Miesiąc': m, 'Nowe sprawy łącznie': naplyw, 'Zakończone sprawy': zakonczone,
            'Aktywne sprawy na koniec': naplyw - zakonczone, 'Sprawomiesiące': sprawomiesiace,
            'Przychód': przychod, 'Wynagrodzenia EH': m * pensje['EH'], 'Wynagrodzenia ugód': m * pensje['UGODY'],
            'Koszty ogólne': narzut, 'Sekretariat': sekretariat, 'Koszt całkowity': koszt, 'Wynik': saldo,
            'Backlog EH (h)': row['Backlog EH (h)'], 'Backlog ugód (h)': row['Backlog UGODY (h)'],
            'Przyszła i zablokowana praca (h)': fsum(przyszla.values()),
            'W tym II instancja zablokowana pracą I (h)': row['II instancja oczekująca na pracę I (h)']})
    sprawdz(miesiace[-1]['Przyszła i zablokowana praca (h)'], wynik['walidacja']['praca_przyszla_minuty'] / 60,
             'Praca przyszła i zablokowana')
    return miesiace


def scenariusze():
    warianty = {}
    for nazwa, n, narzut in (('A', 1, 0), ('B', 1, 43), ('C', 3, 43), ('D', 3, 0),
                            ('E', 4, 43), ('F', 3, 43), ('G', 3, 43)):
        osoby = [{**nowy_pracownik(0), 'rola': 'EH'} for _ in range(n)] + [nowy_pracownik(1)]
        if nazwa == 'F':
            osoby[0]['stawka'] += 10.0
        if nazwa == 'G':
            osoby[-1]['stawka'] += 10.0
        p = {**domyslne_parametry(), 'pracownicy': osoby}
        koszty = {'ogolne_na_aktywna_sprawe': float(narzut), 'sekretariat_na_aktywna_sprawe': 0.0}
        wynik = oblicz_model_czasowy(p, {'horyzont_miesiace': 60}, koszty_kontraktu=koszty)
        miesiace = uzgodnij(p, koszty, wynik)
        warianty[nazwa] = {'obsada': osoby, 'koszty': koszty, 'podsumowanie': miesiace[-1],
                          'punkty_kontrolne': [m for m in miesiace if m['Miesiąc'] in MIESIACE_KONTROLI],
                          'miesiace': wynik['tabela_miesieczna']}
    return warianty


def sprawdz_niezaleznosc(warianty):
    for drozszy, tanszy in (('B', 'A'), ('C', 'D')):
        a, b = warianty[drozszy], warianty[tanszy]
        for x, y in zip(a['miesiace'], b['miesiace']):
            for key in x:
                if not any(word in key for word in ('Koszt', 'koszt', 'Wynik')):
                    if x[key] != y[key]:
                        raise AssertionError(f'Narzut zmienił przepływy: {key}')
        sprawdz(a['podsumowanie']['Wynik'] - b['podsumowanie']['Wynik'],
                 -43 * a['podsumowanie']['Sprawomiesiące'], 'Różnica wyniku równa opłacie')
    for nazwa in ('F', 'G'):
        a, b = warianty[nazwa], warianty['C']
        for x, y in zip(a['miesiace'], b['miesiace']):
            for key in x:
                if not any(word in key for word in ('Koszt', 'koszt', 'Wynik')) and x[key] != y[key]:
                    raise AssertionError(f'Stawka zmieniła przepływy: {key}')
        sprawdz(a['podsumowanie']['Wynik'] - b['podsumowanie']['Wynik'], -60 * 167 * 10, 'Zmiana jednej stawki')
    # Niezależne uzgodnienie lifecycle, także przy różnych stawkach ról.
    for nazwa in ('C', 'F', 'G'):
        p = {**domyslne_parametry(), 'pracownicy': warianty[nazwa]['obsada']}
        model = oblicz_model(p)
        direct = niezalezne_minuty_roczne(p)
        sprawdz(direct['EH'], 259942.5, 'Roczne minuty EH')
        sprawdz(direct['UGODY'], 25425.0, 'Roczne minuty ugód')
        godziny = {'EH': direct['EH'] / 60 * 480 / 420, 'UGODY': direct['UGODY'] / 60 * 480 / 450}
        place = 0.0
        for r in godziny:
            osoby = [o for o in p['pracownicy'] if o['rola'] == r and o['wykorzystanie_percent'] > 0]
            srednia = sum(o['stawka'] for o in osoby) / len(osoby)
            place += godziny[r] * srednia
        sprawdz(model['koszt_wynagrodzen_lifecycle'], place, 'Wynagrodzenia lifecycle')
        sprawdz(model['laczne_godziny_zasobu_lifecycle'] / 600, 9.00547619047619, 'Godziny lifecycle')
        sprawdz(model['ogolem']['przychod'], 451963.254, 'Przychód lifecycle')


def zapisz(warianty, katalog):
    katalog.mkdir(parents=True, exist_ok=True)
    dane = {n: {k: v for k, v in w.items() if k != 'miesiace'} for n, w in warianty.items()}
    (katalog / 'rekonsyliacja.json').write_text(json.dumps(dane, ensure_ascii=False, indent=2) + '\n')
    with (katalog / 'rekonsyliacja.csv').open('w', newline='') as plik:
        kolumny = ['Scenariusz', *warianty['A']['podsumowanie']]
        writer = csv.DictWriter(plik, fieldnames=kolumny)
        writer.writeheader()
        writer.writerows({'Scenariusz': n, **row} for n, w in warianty.items() for row in w['punkty_kontrolne'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, help='Katalog raportów JSON i CSV')
    args = parser.parse_args()
    wyniki = scenariusze()
    sprawdz_niezaleznosc(wyniki)
    for nazwa, wynik in wyniki.items():
        w = wynik['podsumowanie']
        print(f"{nazwa}: wynik {w['Wynik']:.6f} zł; przychód {w['Przychód']:.6f} zł; "
              f"sprawomiesiące {w['Sprawomiesiące']:.6f}; zakończenia {w['Zakończone sprawy']:.6f}")
    print('Uzgodnienie składników, niezmienności przepływów i godzin ról: OK')
    if args.output_dir:
        zapisz(wyniki, args.output_dir)


if __name__ == '__main__':
    main()
