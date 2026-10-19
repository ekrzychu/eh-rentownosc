# Rentowność spraw EH

Lokalna aplikacja Python/Streamlit: ekonomika pełnego cyklu sprawy i miesięczna
symulacja kontraktu. Wymaga Pythona 3.11 lub nowszego.

## Uruchomienie

macOS i Linux, z katalogu projektu:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Przy kolejnych uruchomieniach wystarczy ostatnie polecenie. Otwórz lokalny
adres podany przez Streamlit, zwykle `http://localhost:8501`. Zatrzymanie: Ctrl+C.

## Wspólne wejścia

`defaults.toml` zawiera niezmienione referencyjne parametry. Napływ roczny
jest dzielony przez 12. Miks WPS, P1/P2/P3, udziały sześciu ścieżek i wzory
przychodu są wspólne dla obu paneli. Stawki prawników pochodzą wyłącznie ze
wspólnej obsady: rola, stawka godzinowa i procent przydziału. EH i UGODY mają
rozłączne zasoby. Zmiany obsady oraz ustawień kontraktu przetrwają zmianę
widoku w bieżącej sesji.

| Ścieżka | Referencyjny udział | Praca przed procesem |
| --- | ---: | --- |
| Kategoryczna odmowa | 15% | EH |
| Automatyczne ramy — ugoda | 15% | EH → UGODY |
| Automatyczne ramy — brak ugody | 15% | EH → UGODY → odrzucenie → EH |
| Brak szans | 27,5% | EH, w tym 30 minut kwalifikacji |
| Zawarte poza ramami | 13,75% | EH → UGODY |
| Brak ugody poza ramami | 13,75% | EH → UGODY → odrzucenie → EH |

Ugody kończą 28,75% spraw, ale rzeczywistej pracy UGODY wymaga 57,5%.
Brak prawnika ugód blokuje również nieudane próby. Pozostałe 42,5% może
przechodzić przez proces niezależnie. P1/P2/P3 i II instancja należą do EH.
Definicja etapów znajduje się w `workflow.py`.

## Ekonomika sprawy — Panel 1

Rachunek jednostkowy nie ogranicza pracy miesięczną dostępnością zespołu.
Średnia stawka roli jest arytmetyczną średnią stawek osób z dodatnim
przydziałem, bez ważenia procentem. Brak potrzebnej stawki jest jawny.

```text
koszt bezpośredni = godziny EH × średnia EH + godziny UGODY × średnia UGODY
narzut bezpośredni = bezpośrednie godziny obu ról × narzut godzinowy
roczne dni projektu = 12 × 167 / 8 = 250,5
roczne godziny dzienne = 250,5 × suma minut dziennych / 60
koszt dzienny / sprawę = roczne godziny dzienne × (średnia EH + narzut) / roczny napływ
sekretariat / sprawę = minuty sekretariatu / 60 × stawka sekretariatu
```

Koszt sprawy to suma czterech powyższych składników. Dla pustego portfela
nie alokuje się rocznego kosztu dziennego; koszt i przychód kohorty są zerowe.
Czynności dzienne nie mnożą czasu bezpośredniego. Wszystkie analizy, segmenty,
progi i wrażliwość korzystają z tego samego rachunku. Podatek dotyczy wyłącznie
zysku. Przy referencji koszt to 820,073625 zł/sprawę, przychód 753,27209 zł.

## Kontrakt w czasie — Panel 2

Miesiąc ma referencyjnie 167 płatnych godzin na pełny przydział osoby.
Pensja każdej osoby to `167 × przydział / 100 × indywidualna stawka`.
Jest płatna także przy niewykorzystaniu mocy.

Wszystkie trzy czynności dzienne należą do EH i występują **raz dla projektu**.
90 minut dziennie to 31,3125 h/mies. Zasób rezerwuje jedna osoba EH o największym
przydziale, przy remisie pierwsza w obsadzie. Gdy nie wystarcza jej godzin,
raportowana jest niewykonana część; pozostałe osoby nie przejmują jej po cichu.
Brak EH oznacza niewykonane czynności dzienne. Nie powstaje dodatkowa pensja.

```text
koszt miesiąca = pensje EH + pensje UGODY
              + unikalne sprawy z dodatnią pracą × (narzut miesięczny + sekretariat miesięczny)
wynik miesiąca = rzeczywiste płatności − koszt miesiąca
wynik skumulowany = suma wyników miesięcznych
```

Sprawy w kolejce i oczekujące na wyrok/ugodę nie naliczają kosztów spraw.
Kilka etapów albo obu prawników pracujących nad tą samą sprawą w miesiącu
powoduje jedną opłatę. Te koszty są niezależne od godzinowego narzutu i
jednorazowego sekretariatu Panelu 1. Rachunków paneli nie należy sumować.

### Harmonogram i granice miesięcy

1. Napływ i uwolnienie etapów dostępnych w tym miesiącu.
2. Rezerwacja stałych czynności dziennych EH.
3. FIFO w osobnych kolejkach ról; najstarsza data dostępności, potem wpływ,
   potem stały identyfikator. Kolejność segmentów przy remisie jest kanoniczna:
   P, grupa WPS, ścieżka, wynik instancji, kolejny reprezentant.
4. Przyjęcie EH wraz z czasem P i kwalifikacją „brak szans” poprzedza dalszą
   pracę. Po przyjęciu kolejny etap może zacząć się w tym samym miesiącu.
5. Nieudana próba kończy się odrzuceniem po zakończeniu pracy UGODY. Proces
   EH jest dostępny od następnego miesiąca. Nie dodano osobnego opóźnienia
   kalendarzowego odrzucenia ugody.
6. Zegar ugody, procesu lub II instancji zaczyna się przy pierwszej dodatniej
   pracy odpowiedniego etapu. Termin to `miesiąc inicjacji + opóźnienie`.
7. Wynik formalny na koniec miesiąca wymaga ukończonej pracy oraz terminu.
   II instancja wchodzi do kolejki od miesiąca po wyroku I i ma własny zegar.
   Sprawa kierowana do II instancji nie zarabia przy wyroku I.
8. Zapłata następuje w miesiącu zakończenia powiększonym o opóźnienie
   płatności. Opóźnienie zero pozwala na płatność w miesiącu zakończenia.
9. Uzgodnienie minut, spraw, wynagrodzeń, opłat i wyników.

Waga oczekiwana nie jest zaokrąglana. Jednorodny segment dzieli się na
reprezentantów o wadze najwyżej 1 oraz dokładną resztę. Częściowa praca
zmniejsza minuty tego samego reprezentanta. Jego etap kończy się po wykonaniu
całej pracy; częściowo wykonana pojedyncza sprawa nie daje częściowego przychodu.
Koszt miesiąca to suma wag **unikalnych identyfikatorów** z dodatnią pracą.

Etap zerowy nie zużywa minut i nie nalicza opłaty. Nadal wymaga obecnej roli
z dodatnią pojemnością po rezerwacji dziennych. Zegar startuje przy faktycznej
inicjacji, z zachowaniem przekazań między miesiącami.

### Znaczenie liczników

- **Sprawy otwarte**: wpływ skumulowany minus formalne zakończenia.
- **Sprawy oczekujące na pracę**: sprawy z pozostałą pracą, także przyszłych
  etapów, albo z wymaganym, jeszcze niezainicjowanym etapem zerowym.
- **Sprawy, nad którymi pracowano w miesiącu**: suma unikalnych wag z dodatnimi minutami.
- **Sprawy oczekujące na formalne zakończenie**: praca bieżącego etapu gotowa,
  ale termin formalny jeszcze nie nadszedł.
- **Backlog EH/ugód**: pozostałe minuty bieżącego odcinka tej samej roli,
  do przekazania innej roli albo wyniku formalnego. Przyjęcie i bezpośredni
  proces EH są jednym odcinkiem kolejki, ale mają odrębne warunki wykonania.
- **Praca przyszła i zablokowana**: dalsze odcinki czekające na przekazanie
  lub wynik. Nie jest tracona ani wykonywana przed warunkami wstępnymi.

Liczniki oczekiwania nie są rozłącznymi kategoriami: sprawa czekająca na
wyrok I może mieć jeszcze przyszłą pracę II instancji. Przy zerowych minutach
mogą pozostać formalnie otwarte sprawy i etapy zerowe czekające na miesiąc
przekazania, choć backlog godzin i opłaty za pracę są zerowe.

Stabilność wymaga wystarczającej mocy każdej wymaganej roli i obsługi
czynności dziennych przez jedną osobę. Dojrzały wynik jest potwierdzany po
12 miesiącach zgodnej obsługi pełnego napływu, bez zaległej pracy. Sam
płaski wynik przy rosnącej kolejce nie potwierdza stabilności.

## Testy i odtworzenie audytu

```bash
.venv/bin/python -m unittest discover -v
.venv/bin/python reproduce_baseline.py
.venv/bin/python diagnostic_costs.py --output-dir audit_results
.venv/bin/python audit_checks.py
```

Na Windows użyj `.\.venv\Scripts\python.exe` zamiast `.venv/bin/python`.

Raport: [AUDYT.md](AUDYT.md). Pełne dane 10 scenariuszy, bez zaokrąglania:
[JSON](audit_results/rekonsyliacja.json),
[CSV dla 12/24/60 miesięcy](audit_results/rekonsyliacja.csv),
[most starego i nowego wyniku](audit_results/porownanie_stary_nowy.json).
Stary model pochodzi dokładnie z `99a2f1e`; skrypt odtwarza go z lokalnej
historii Git bez zmiany gałęzi. Pomiary: [wydajność](audit_results/wydajnosc.json).

Nazwy kluczy TOML `ogolne_na_aktywna_sprawe` i `sekretariat_na_aktywna_sprawe`
zachowano dla zgodności konfiguracji. Oznaczają teraz stawki za sprawę z
**wykonaną pracą**, co jednoznacznie opisuje interfejs. Ich wartości domyślne
pozostały zerowe; 43 zł występuje w diagnostyce jako jawny przykład.

Model używa wartości oczekiwanych i stałych miesięcznych przydziałów. Nie
modeluje sezonowości, urlopów, inflacji, zmiennej obsady w trakcie pojedynczego
przebiegu ani terminu zapłaty podatku. Wynik kontraktu pozostaje przed podatkiem.
