"""Niezależny bilans arytmetyczny, bez funkcji pojemności i kolejek modelu."""
from math import isclose
from random import Random
from model import domyslne_parametry, oblicz_model
from timeline import oblicz_model_czasowy
rng = Random(19102026)
for scenario in range(30):
    p = {**domyslne_parametry(), 'liczba_spraw': rng.randrange(0, 1000),
         'udzial_ii_instancji_percent': rng.choice([0., 50., 100.])}
    roster = [{'rola': rng.choice(['EH', 'UGODY']), 'stawka': rng.randrange(0, 120),
               'wykorzystanie_percent': rng.choice([0., 15., 60., 100.])}
              for _ in range(rng.randrange(0, 9))]
    costs = {'ogolne_na_aktywna_sprawe': rng.randrange(0, 80),
             'sekretariat_na_aktywna_sprawe': rng.randrange(0, 40)}
    horizon = rng.randrange(12, 60)
    result = oblicz_model_czasowy(p, {'horyzont_miesiace': horizon,
        'miesiace_do_ugody': rng.randrange(0, 30), 'miesiace_do_wyroku_i': rng.randrange(0, 30),
        'miesiace_wyrok_i_do_ii': rng.randrange(0, 20), 'opoznienie_platnosci_miesiace': rng.randrange(0, 12)},
        pracownicy=roster, koszty_kontraktu=costs)
    salary = sum(167 * e['wykorzystanie_percent'] / 100 * e['stawka'] for e in roster)
    role_cap = {role: sum(167 * e['wykorzystanie_percent'] / 100 * (1 - daily / 480)
                         for e in roster if e['rola'] == role)
                for role, daily in [('EH', 60), ('UGODY', 30)]}
    inflow = completions = balance = 0.
    previous_active = 0.
    for row in result['tabela_miesieczna']:
        billable = previous_active + p['liczba_spraw'] / 12
        overhead = billable * costs['ogolne_na_aktywna_sprawe']
        secretariat = billable * costs['sekretariat_na_aktywna_sprawe']
        cost = salary + overhead + secretariat
        inflow += p['liczba_spraw'] / 12
        completions += sum(row[k] for k in ('Ugody zakończone', 'Zakończenia po I instancji', 'Zakończenia po II instancji'))
        balance += row['Przychód razem'] - cost
        assert isclose(row['Łączny koszt miesięczny'], cost, abs_tol=1e-6)
        assert isclose(row['Wynik skumulowany przed podatkiem'], balance, abs_tol=1e-6)
        assert isclose(row['Aktywne sprawy'], inflow - completions, abs_tol=1e-6)
        previous_active = inflow - completions
        for role in ('EH', 'UGODY'):
            assert row[f'Wykonana praca {role} (h)'] <= role_cap[role] + 1e-7
    w = result['walidacja']
    expected_work = oblicz_model(p)['bezposrednie_minuty_spraw'] * horizon / 12
    assert isclose(w['praca_wykonana_minuty'] + w['backlog_minuty'] + w['praca_przyszla_minuty'], expected_work, abs_tol=1e-5)
print('30 scenariuszy: niezależne bilanse kosztów, aktywności, pojemności ról i wszystkich minut — OK')
