"""Odtwarza dane starego silnika z commitu 99a2f1e bez zmiany gałęzi.

Uruchamia historyczny kod w katalogu tymczasowym, wyłącznie lokalnie.
Nie nadpisuje utrwalonego punktu odniesienia: porównuje wszystkie dane.
"""

import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory


SKRYPT = '''
import json
from model import domyslne_parametry, _skaluj_bezposrednie_czasy
from timeline import oblicz_model_czasowy
from staff import nowy_pracownik
out = {}
for s in range(1, 11):
    p = domyslne_parametry()
    eh = 1 if s in (1, 2, 9, 10) else 0 if s == 8 else 3
    ug = 0 if s == 7 else 1
    p['pracownicy'] = [{**nowy_pracownik(0), 'rola': 'EH'} for _ in range(eh)] + [
        {**nowy_pracownik(1), 'rola': 'UGODY'} for _ in range(ug)]
    if s == 4:
        p['codzienne_czynnosci'] = {k: 0 for k in p['codzienne_czynnosci']}
    if s in (6, 9):
        p = _skaluj_bezposrednie_czasy(p, .5 if s == 6 else 0)
    costs = {'ogolne_na_aktywna_sprawe': 0 if s == 1 else 43, 'sekretariat_na_aktywna_sprawe': 0}
    r = oblicz_model_czasowy(p, koszty_kontraktu=costs)
    out[str(s)] = {'parametry': p, 'koszty': costs, 'miesiace': r['tabela_miesieczna'],
                   'walidacja': r['walidacja'], 'kpi': r['kpi']}
print(json.dumps({'commit': '99a2f1e', 'scenariusze': out}, ensure_ascii=False))
'''


def main():
    root = Path(__file__).resolve().parent
    archive = subprocess.run(['git', 'archive', '99a2f1e'], cwd=root, capture_output=True, check=True).stdout
    with TemporaryDirectory(prefix='eh-history-') as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for name in ('model.py', 'timeline.py', 'staff.py', 'config.py', 'defaults.toml'):
                Path(tmp, name).write_bytes(tar.extractfile(name).read())
        result = subprocess.run([sys.executable, '-c', SKRYPT], cwd=tmp, capture_output=True, text=True, check=True)
        fresh = json.loads(result.stdout)
    baseline = json.loads((root / 'audit_results/stary_model_99a2f1e.json').read_text())
    if fresh != baseline:
        raise AssertionError('Odtworzony stary model różni się od utrwalonych danych.')
    print('99a2f1e: wszystkie 10 scenariuszy i 600 miesięcy zgodne z zapisanym starym modelem — OK')


if __name__ == '__main__':
    main()
