"""Porównanie rocznej ekonomiki kohorty z jawnym okresem realizacji kontraktu."""

from math import fsum
from model import oblicz_model, oblicz_przeplyw
from staff import srednie_stawki_wedlug_roli


def porownaj_panele(p, timeline):
    rows = timeline['tabela_miesieczna'][-12:]
    factor = 12 / len(rows)
    flow = oblicz_przeplyw(p)
    try:
        economics = oblicz_model(p)['ogolem']
    except ValueError as error:
        if 'Brak stawki godzinowej wymaganej roli' not in str(error):
            raise
        economics = None
    rates = srednie_stawki_wedlug_roli(p['pracownicy'])
    total = lambda col: fsum(r[col] for r in rows) * factor
    direct = flow['bezposrednie_minuty_spraw'] / 60
    daily = 12 * 167 / 8 * fsum(p['codzienne_czynnosci'].values()) / 60 if p['liczba_spraw'] else 0
    salaries = total('Wynagrodzenia EH') + total('Wynagrodzenia ugód')
    expected_salary = economics['koszt_wynagrodzenia'] if economics else None
    positions = []
    for label, expected, actual in (
        ('Przychód (zł)', flow['ogolem']['przychod'], total('Przychód razem')),
        ('Wynagrodzenia (zł)', expected_salary, salaries),
        ('Bezpośrednie godziny pracy', direct, total('Wykonana praca (h)')),
        ('Wspólne czynności dzienne (h)', daily, total('Czynności dzienne (h)')),
        ('Wspólny narzut (zł/h)', p['koszt_staly_na_godzine'], timeline['koszty_kontraktu']['general_overhead_per_hour']),
        ('Koszty ogólne (zł)', economics['koszt_narzutu_ogolnego'] if economics else None, total('Narzut kosztów ogólnych razem')),
        ('Sekretariat (zł)', economics['koszt_sekretariatu'] if economics else None, total('Jednorazowe koszty sekretariatu')),
        ('Sprawy zakończone', p['liczba_spraw'], sum(total(c) for c in ('Ugody zakończone', 'Zakończenia po I instancji', 'Zakończenia po II instancji'))),
        ('Backlog na koniec (h)', 0, rows[-1]['Backlog na koniec (h)']),
        ('Koszt całkowity (zł)', economics['koszt_calkowity'] if economics else None, total('Łączny koszt miesięczny')),
        ('Wynik przed podatkiem (zł)', economics['wynik_przed_podatkiem'] if economics else None, total('Wynik miesięczny przed podatkiem')),
    ):
        positions.append({'Pozycja': label, 'Panel 1 — rok kohorty': expected,
                          'Panel 2 — roczne tempo okresu': actual,
                          'Różnica': actual - expected if expected is not None else None})
    # Dokładne rozłożenie różnicy płac na wykorzystanie, czas pracy i rozkład stawek.
    idle_salary = work_timing_salary = wage_allocation = 0.0
    if economics:
        for role in ('EH', 'UGODY'):
            rate = rates[role] or 0
            used = total(f'Wykonana praca {role} (h)') + (total('Czynności dzienne (h)') if role == 'EH' else 0)
            funded = timeline['pojemnosc']['role'][role]['brutto_minuty'] / 60 * 12
            expected = flow['roczne_minuty_wedlug_roli'][role] / 60 + (daily if role == 'EH' else 0)
            idle_salary += (funded - used) * rate
            work_timing_salary += (used - expected) * rate
            wage_allocation += total('Wynagrodzenia EH' if role == 'EH' else 'Wynagrodzenia ugód') - funded * rate
    explanations = [
        'Panel 1 wycenia pełny cykl rocznej kohorty; Panel 2 pokazuje wykonanie i płatności wybranego okresu. Wyników całego horyzontu nie porównuje się z jedną kohortą.',
        f"Dojrzałość operacyjna: {timeline['podsumowanie']['dojrzalosc_osiagnieta']}. Nieukończone sprawy, kolejki, oczekiwanie formalne i opóźnienia płatności mogą przesuwać przychód oraz pracę poza okres.",
    ]
    if economics:
        explanations.append(f'Różnica płac: {salaries - expected_salary:.6f} zł = płatne niewykorzystane godziny {idle_salary:.6f} zł + inne wykonanie pracy w okresie {work_timing_salary:.6f} zł + indywidualne stawki względem średnich ról {wage_allocation:.6f} zł.')
    else:
        explanations.append('Brak stawki wymaganej roli uniemożliwia wycenę Panelu 1; przepływ i rzeczywiste koszty kontraktu pozostają dostępne.')
    if len(rows) < 12:
        explanations.append('Okres krótszy niż rok: pokazano przeliczenie × 12 / liczba miesięcy; nie jest to dojrzały rok porównawczy.')
    return {'okres': f"Panel 2: miesiące {rows[0]['Miesiąc']}–{rows[-1]['Miesiąc']} ({len(rows)} miesięcy); roczne tempo × {factor:g}.",
            'pozycje': positions, 'wyjasnienia': explanations,
            'roznica_plac_skladniki': {'bezczynnosc': idle_salary, 'wykonanie': work_timing_salary, 'stawki': wage_allocation} if economics else None}
