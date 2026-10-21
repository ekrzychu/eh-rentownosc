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
widoku w bieżącej sesji. Koszty ustawia się raz we wspólnym pasku bocznym:
`koszt_staly_na_godzine` (domyślnie 36 zł/h),
`sekretariat_minuty_na_sprawe` i `koszt_sekretariatu_na_godzine`.
Zmiana dowolnej z tych wartości automatycznie przelicza oba widoki.

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
              + wykonane godziny spraw × wspólny narzut godzinowy
              + wykonane godziny czynności dziennych × wspólny narzut godzinowy
              + wagi spraw rozpoczynających przyjęcie × jednorazowy sekretariat / sprawę
wynik miesiąca = rzeczywiste płatności − koszt miesiąca
wynik skumulowany = suma wyników miesięcznych
```

Narzut = `(wykonane minuty EH + wykonane minuty UGODY + wykonane minuty dzienne) / 60 × koszt_staly_na_godzine`.
Nie obejmuje kolejki, oczekiwania formalnego, przyszłej pracy ani płatnych
niewykorzystanych godzin. Praca rozłożona na miesiące zachowuje ten sam narzut
od sumy godzin. Czynności dzienne mają narzut 1127,25 zł/mies. przy 36 zł/h,
wyłącznie w wykonanej części. Ich pensja mieści się już w płatnym przydziale.

Sekretariat = `sekretariat_minuty_na_sprawe / 60 × koszt_sekretariatu_na_godzine`.
Zdarzenie `SEKRETARIAT_OBSLUZONY` występuje raz przy pierwszej inicjacji
`przyjecie`, ze stałą tożsamością sprawy, jej dokładną wagą i kwotą kosztu.
Sam wpływ do kolejki nie wystarcza. Zerominutowe przyjęcie z dostępną rolą
może wygenerować koszt sekretariatu, nawet bez pracy prawnika. Brak roli lub
zerowy przydział blokuje inicjację. Odrzucenie ugody, przekazanie do procesu,
II instancja, zamknięcie i płatność nie powtarzają kosztu. Przy zerowej stawce
lub czasie zdarzenie ma koszt zero. Sekretariat nie zajmuje minut prawnika,
nie dokłada pensji i nie zmienia zegarów formalnych ani ścieżek.

To wspólna **stawka alokacji kosztu od pracy**, a nie stały wydatek
kalendarzowy. Model nie zawiera dodatkowego budżetu kosztów stałych na miesiąc.
Koszt godzinowy i wynagrodzenia są odrębnymi składnikami; żaden nie jest
naliczany ponownie przy wykonaniu etapu lub zamknięciu sprawy.

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
przekazania, choć backlog godzin i narzut bezpośredni są zerowe. Jednorazowy
sekretariat i faktycznie wykonane czynności dzienne mogą nadal kosztować.

Stabilność wymaga wystarczającej mocy każdej wymaganej roli i obsługi
czynności dziennych przez jedną osobę. Dojrzały wynik jest potwierdzany po
12 miesiącach zgodnej obsługi pełnego napływu, bez zaległej pracy. Sam
płaski wynik przy rosnącej kolejce nie potwierdza stabilności.

Historyczny, wcześniej nieśledzony test dwóch niezależnych stawek zachowano
bez zmiany treści w [archiwum](audit_results/history/test_koszty_ogolne.py.txt).
Jego założenie 43 zł/sprawomiesiąc zostało zastąpione; nie jest bieżącym testem.

## Testy i odtworzenie audytu

```bash
.venv/bin/python -m unittest discover -v
.venv/bin/python reproduce_baseline.py
.venv/bin/python diagnostic_costs.py --output-dir audit_results
.venv/bin/python audit_checks.py
.venv/bin/python reconcile_shared_costs.py --output audit_results/wspolne_koszty.json
.venv/bin/python -m compileall -q *.py
```

Na Windows użyj `.\.venv\Scripts\python.exe` zamiast `.venv/bin/python`.

Raport: [AUDYT.md](AUDYT.md). Archiwalne dane audytu z 19 października
(przed wspólnym modelem kosztów; aktualne można odtworzyć powyższymi poleceniami):
[JSON](audit_results/rekonsyliacja.json),
[CSV dla 12/24/60 miesięcy](audit_results/rekonsyliacja.csv),
[most starego i nowego wyniku](audit_results/porownanie_stary_nowy.json).
Stary model pochodzi dokładnie z `99a2f1e`; skrypt odtwarza go z lokalnej
historii Git bez zmiany gałęzi. Pomiary: [wydajność](audit_results/wydajnosc.json).

Dawne klucze `ogolne_na_aktywna_sprawe` i `sekretariat_na_aktywna_sprawe`
usunięto z TOML i interfejsu. API `koszty_kontraktu` akceptuje jeszcze pusty
lub zerowy stary słownik dla zgodności; każda niezerowa wartość zgłasza
`ValueError` z instrukcją migracji. Dotyczy to także słownika dołączonego
do parametrów modelu i dawnej sekcji TOML. Nie można dodać drugiej opłaty.
Słownik `koszty_kontraktu` w **wyniku** symulacji raportuje wyłącznie pochodne
wspólnych ustawień: `general_overhead_per_hour` i `secretariat_cost_per_case`.

## Uzgodnienie obu paneli

`reconcile_shared_costs.py` sprawdza roczną kohortę 600 spraw z miesiącami
109–120 symulacji. Dokładny przydział EH3 to
`((4414.875 / 12 + 375.75 / 12 - 334) / 167) × 100`,
a UGODY `341.25 / 12 / 167 × 100`. Stawki wszystkich osób: 59,88 zł/h.
W obu panelach praca to 4756,125 h bezpośrednio + 375,750 h dziennie rocznie;
pensje 307296,675 zł, przychód 451963,254 zł, ukończone sprawy 600,
końcowy backlog 0 h i dojrzałość operacyjna `True`.

| Narzut zł/h | Narzut roczny zł | Koszt roczny zł | Wynik roczny zł |
| ---: | ---: | ---: | ---: |
| 0 | 0,000 | 307296,675 | 144666,579 |
| 10 | 51318,750 | 358615,425 | 93347,829 |
| 36 | 184747,500 | 492044,175 | −40080,921 |
| 60 | 307912,500 | 615209,175 | −163245,921 |

Przy 36 zł/h średni narzut na sprawę wynosi 307,9125 zł. To wskaźnik
pochodny Panelu 1, a nie opłata wejściowa w kontrakcie. Sekretariat 30 min
po 30 zł/h to 15 zł/sprawę, 9000 zł/rok, 501044,175 zł kosztów i
−49080,921 zł wyniku w obu panelach. Tolerancja uzgodnienia: 0,01 zł.
Wyniki maszynowe: [wspolne_koszty.json](audit_results/wspolne_koszty.json).
Kontrole 10 scenariuszy w miesiącach 12/24/60:
[wspolne_scenariusze.csv](audit_results/wspolne_scenariusze.csv).

`reconciliation.porownaj_panele` oraz rozwijana diagnostyka Panelu 2 zestawiają
roczne tempo ostatnich maksymalnie 12 miesięcy z pełnym rokiem kohorty.
Pokazują godziny, koszty, ukończenia, backlog i wynik oraz jawne granice okresu.
Rozkładają różnicę płac na bezczynność, inne wykonanie pracy w okresie
i indywidualne stawki względem arytmetycznych średnich ról.
Nie uzgadniają sztucznie wyniku. Płatny zapas obsady zwiększa pensje Panelu 2;
mała pojemność, przyszła II instancja i opóźnienia płatności mogą przesunąć
pracę oraz przychód poza porównywany rok. Krótszy okres i niepotwierdzona
dojrzałość są jawnie opisane. Brak stawki roli pozostawia niewycenialne pola
Panelu 1 puste, zachowując diagnostykę przepływu Panelu 2.

Model używa wartości oczekiwanych i stałych miesięcznych przydziałów. Nie
modeluje sezonowości, urlopów, inflacji, zmiennej obsady w trakcie pojedynczego
przebiegu ani terminu zapłaty podatku. Wynik kontraktu pozostaje przed podatkiem.
