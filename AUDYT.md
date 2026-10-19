# Raport aktualizacji rachunku kosztów EH

Data: 19 października 2026.
Punkt odniesienia: `main`, `58657c7`.
Gałąź: `feature/role-based-timeline-costs`.
Zmiany są przygotowane lokalnie do niezależnego audytu przed scaleniem.
Nie wykonano push ani merge. Commit wdrożenia zawiera ten raport; identyfikator
można odczytać przez `git log -1 --oneline`.

## Zakres plików

| Pliki | Zmiana |
| --- | --- |
| `model.py`, `analysis.py` | Jednorazowy sekretariat, segmenty, koszty, marże, wrażliwość i progi |
| `staff.py` | Indywidualna obsada, walidacja, trwały magazyn ustawień, pojemność ról |
| `timeline.py` | Rozłączne kolejki, zależności II instancji, aktywność, miesięczne koszty i status |
| `app.py`, `ui_case.py`, `ui_timeline.py` | Polskie wejścia, opisy i zestawienia obu rachunków |
| `config.py`, `defaults.toml` | Nowe zerowe koszty, inicjalizacja edytowalnego przykładu obsady |
| `test_model.py`, `test_analysis.py`, `test_timeline.py`, `test_app.py` | Regresje i nowe zasady rachunku |
| `audit_checks.py` | Odtwarzalny niezależny audyt arytmetyczny 30 scenariuszy |
| `README.md`, `AUDYT.md` | Opis modelu, przykładów, walidacji i ograniczeń |

`test_ui_timeline.py` sprawdzono i uruchomiono bez zmiany; jego testy wykresów,
formatowania i finansowego break-even nadal obowiązują. `main.py` nie wymagał zmian.

## Poprzedni i nowy rachunek

| Zagadnienie | Poprzednio | Obecnie |
| --- | --- | --- |
| Ekonomika sprawy | Zużyty czas × referencyjna stawka pracy i narzutu | Ten sam rachunek oraz osobny sekretariat raz na sprawę |
| Wynagrodzenia kontraktu | Jedna globalna stawka × pełne godziny wszystkich osób | Indywidualne stawki × przydzielone płatne godziny |
| Narzut kontraktu | Godzinowy narzut Panelu 1 × godziny obsady | Niezależna kwota × sprawy aktywne w miesiącu |
| Sekretariat kontraktu | Brak osobnego składnika | Niezależna kwota × sprawy aktywne w miesiącu |
| Pojemność | Jeden wspólny zasób | EH i ugody bez zastępstw |
| Status finansowy | Marża lifecycle oraz koszt hipotetycznej minimalnej obsady | Potwierdzona dojrzała ekonomika jawnie ustawionej obsady i aktywnych spraw |

Nowe kwoty w `defaults.toml` wynoszą zero. Nie wpisano przykładów 43 zł,
50 zł ani 10 minut jako danych biznesowych. Referencyjna stawka 59,88 zł/h
pozostaje w jednym źródle TOML. Panel 1 nie zależy od liczby pracowników,
indywidualnych przydziałów, ról, stawek i miesięcznych kosztów aktywności.

## Dokładne wzory pracownika

Dla pracownika `i`, jego przydziału `u` w procentach, stawki `w` w zł/h
oraz dziennych minut czynności jego roli `d`:

```text
H = 167 × u / 100
wynagrodzenie miesięczne = H × w
ekwiwalent dni = H / 8
czas czynności dziennych w godzinach = H / 8 × d / 60
pojemność bezpośrednia w godzinach = max(H − H / 8 × d / 60, 0)
```

Sumowanie następuje osobno w każdej roli. Przydział 0% daje zerowe godziny
i koszt. Czas niewykorzystany pozostaje opłacony. Praca nad sprawami oraz
czynności dzienne nie powodują dodatkowego naliczenia wynagrodzenia.
Przykład: `167 × 60% = 100,2 h`, `100,2 × 60 = 6012 zł/mies.`.
Dla EH przy dziennym narzucie 60 minut pojemność wynosi 87,675 h/mies.

## Obciążenie ról

Dla niezmienionych założeń referencyjnych, 600 spraw/rok i przykładowej
początkowej obsady po jednej osobie każdej roli z przydziałem 100%:

| Rola | Wymagana praca miesięczna | Dostępna pojemność | Niedobór |
| --- | ---: | ---: | ---: |
| EH | 361,03125 h | 146,125 h | 214,90625 h |
| Ugody | 35,3125 h | 156,5625 h | 0 h |

EH obejmuje przyjęcie, proces, P1/P2/P3 i II instancję. Ugody obejmują analizę,
ofertę, projekt, podpisanie i nieudane próby. Analiza pozostaje tylko na
ścieżkach, które wymagały jej wcześniej. Nie została dodana automatycznym ramom.

Roczny popyt wynosi 259 942,5 min EH i 25 425 min ugód, razem 285 367,5 min.
Przy wystarczającym jawnym składzie roczny dojrzały przepływ uzgadnia się
z 600 sprawami, powyższymi minutami i przychodem lifecycle 451 963,254 zł.
Nadmiar mocy ugód nie obsługuje niedoboru EH. Brak którejkolwiek potrzebnej
roli blokuje odpowiednie etapy, zakończenia i przychód.

FIFO dotyczy dostępnej pracy według miesiąca wymagalności; w tej samej dacie
praca dzielona jest proporcjonalnie. II instancja ma dodatkowy warunek:
termin wyroku I oraz wykonanie wszystkich wymaganych wcześniejszych etapów
obu ról dla danego ułamka oczekiwanej grupy. Odblokowane części otrzymują w FIFO datę faktycznego odblokowania.
Wcześniej są wykazane jako praca przyszła, oddzielnie od wymagalnego backlogu.
Jej praca nie jest rozciągana
na okres oczekiwania. Wspólny rekord `Completion` blokuje przedwczesny przychód.

## Aktywność i miesięczne opłaty

```text
sprawy naliczające koszt = stan otwarcia + nowy wpływ
stan zamknięcia = wpływ skumulowany − zakończenia skumulowane
koszt miesięczny = wynagrodzenia EH + wynagrodzenia ugód
                  + podstawa × koszt ogólny
                  + podstawa × koszt sekretariatu
```

Miesiąc wpływu i rzeczywistego zakończenia są płatne, także gdy są tym samym
miesiącem. Po zakończeniu opłaty ustają. Termin płatności nie przedłuża
aktywności. Dłuższe oczekiwanie zwiększa koszty aktywności, lecz nie tworzy
minut pracy. Liczebności oczekiwane są ułamkowe, bez zaokrąglania podstawy opłat.

## Status, dojrzałość i break-even

Stabilność operacyjna wymaga wystarczającej mocy każdej roli. Diagnostyka
pojemności zastępuje pojedynczy minimalny FTE. Porównania API wymagają
jawnych list pracowników; nie tworzą hipotetycznych ról, stawek i przydziałów.
Czas potrzebny do rozładowania backlogu jest liczony według ról. Przy zerowej
mocy potrzebnej roli jest niedostępny, także gdy druga rola ma wolny czas.
Usunięto pieniężną wycenę niewykorzystanej pojemności: przy różnych stawkach
w tej samej roli wymagałaby dodatkowego założenia o podziale pracy między
osobami. Niewykorzystane godziny i pełne wynagrodzenia pozostają widoczne.

Rentowność kontraktu jest potwierdzana dopiero po dojrzałym okresie.
Potrzeba pełnych 12 miesięcy po najdłuższej aktywnej ścieżce i opóźnieniu
płatności. Każdy miesiąc musi uzgodnić pracę obu ról, brak backlogu,
oczekiwane zakończenia każdego typu, przychód, stały stan aktywnych spraw,
podstawę opłat i pełne koszty. Krótki rozruch daje status niepotwierdzonej
rentowności. Ujemna marża Panelu 1 nie przesądza o wyniku Panelu 2 i odwrotnie.

Pierwsze odzyskanie deficytu pozostaje osobnym finansowym break-even.
Trwały break-even wymaga ponadto braku późniejszego zejścia poniżej zera
w badanym horyzoncie, wystarczającej pojemności obu ról i potwierdzonego
dodatniego wyniku dojrzałego po kosztach aktywnych spraw. Deficyt rozruchowy,
strata strukturalna i niedobór mocy są oddzielnymi diagnozami.

## Przykłady liczbowe

**Panel 1.** Przy pozostałych wartościach referencyjnych oraz ilustracyjnych
10 minutach sekretariatu i 50 zł/h:

```text
sekretariat / sprawę = 10 / 60 × 50 = 8,333333333 zł
sekretariat 600 spraw = 5000 zł
przychód / sprawę = 753,27209 zł
koszt / sprawę = 935,420030769 + 8,333333333 = 943,753364103 zł
wynik / sprawę = −190,481274103 zł
wynik kohorty = −114 288,764461538 zł
marża = −25,287180639% (podatek 0%)
```

**Panel 2.** Ilustracyjna jawna obsada: 3 osoby EH po 20 zł/h i 1 osoba ugód
po 30 zł/h, każda z przydziałem 100%. Kwoty aktywności: 43 zł i 7 zł.
Pozostałe założenia pozostają referencyjne.

```text
wynagrodzenia = 3 × 167 × 20 + 167 × 30 = 15 030 zł/mies.
pierwszy miesiąc: 50 aktywnych spraw
narzut = 50 × 43 = 2150 zł
sekretariat = 50 × 7 = 350 zł
koszt = 17 530 zł; przychód = 0 zł; wynik = −17 530 zł
```

W dojrzałym miesiącu: 563,75 spraw nalicza koszt, 50 kończy się, a 513,75
pozostaje na koniec. Koszty to 15 030 zł wynagrodzeń + 24 241,25 zł narzutu
+ 3946,25 zł sekretariatu = 43 217,50 zł. Przychód wynosi 37 663,6045 zł,
wynik −5553,8955 zł. Obie role mają wystarczającą pojemność, lecz kontrakt
jest nierentowny i nie ma trwałego break-even. Kwoty przykładu nie zostały
użyte jako nowe wartości domyślne.

## Walidacja

Przed edycją: **176 testów, wszystkie poprawne**.
Po aktualizacji wykonano wymagane polecenia przy użyciu interpretera `.venv/bin/python`:

| Polecenie | Liczba | Wynik |
| --- | ---: | --- |
| `python -m unittest test_model -v` | 58 | OK |
| `python -m unittest test_analysis -v` | 37 | OK |
| `python -m unittest test_timeline -v` | 83 | OK |
| `python -m unittest test_app -v` | 11 | OK |
| `python -m unittest test_ui_timeline -v` | 4 | OK |
| `python -m unittest` | 193 | OK |

Testy dawnych kosztów wspólnej puli, pojedynczego minimum FTE i statusu
zależnego od marży lifecycle zastąpiono testami nowych reguł. Zachowano
testy sześciu ścieżek, czasu pracy, nominalnych bramek, ułamkowego wykonania,
FIFO, kolejności segmentów, podatku i przepływów.

| Wymagania | Pokrycie |
| --- | --- |
| A–B, D–E, W | Niezależność rachunków i klasyfikacji w obu kierunkach |
| C | Dokładny jednorazowy sekretariat, segmenty, mnożnik dzienny, progi i wrażliwość |
| F–J | Opłaty od wpływu do zakończenia, natychmiastowe zakończenie, opóźnienie płatności |
| K–N | Wynagrodzenia, 60% i 0%, mieszane stawki, trwałość ustawień także w AppTest |
| O–T | Brak zastępstw, brak jednej roli, blokady etapów, II instancja i bramka przychodu |
| U–V | Bilans obu kolejek oraz całej pracy, roczny przepływ i długie terminy |
| X–Y | Suma kosztów i brak ponownego naliczania pracy, narzutu i sekretariatu |
| Z | Indywidualne kontrolki, dwa widoki, przełączanie i zachowanie parametrów |

Dodatkowo: zero osób, zero wpływu, zero kosztów aktywności, wyczerpanie
całego dnia przez jedną rolę, brak mocy w jednej puli, rosnący backlog,
krótki rozruch i niewystarczający horyzont.

`python audit_checks.py` sprawdza niezależnymi wzorami 30 deterministycznych
scenariuszy: wynagrodzenia, podstawę opłat, wynik skumulowany, stany spraw,
limity obu ról oraz sumę pracy wykonanej, zaległej i przyszłej. Wynik: OK.
Kontrola nie korzysta z funkcji obliczających pojemność ani wykonujących kolejki.

Uruchomiono rzeczywisty serwer Streamlit oraz Chrome headless z oddzielnym
profilem w `/tmp`. Obejrzano oba widoki, sprawdzono polskie etykiety,
układ, nowe koszty, statusy i brak wyjątków. Zrzuty robocze:
`/tmp/eh-case.png`, `/tmp/eh-timeline.png`. Uzupełnia to AppTests.
`git diff --check`: OK.

## Pozostałe ograniczenia i gotowość

Brak znanych blokad wdrożenia w uzgodnionym zakresie. Wymagany jest niezależny
audyt przed merge. Zmieniono interfejs klasyfikatora i porównań obsady oraz
niektóre pola raportu API zgodnie z nową semantyką; nie zachowano pól
sugerujących matematycznie błędne minimum zespołu lub uzgodnienie kosztów paneli.

Ustawienia trwają w sesji Streamlit; nie dodano trwałego magazynu między
sesjami. Zachowano model stałego oczekiwanego wpływu, stałych stawek i
nominalnych miesięcy kalendarzowych. Nie dodano sezonowości, inflacji,
urlopów ani harmonogramu zapłaty podatku. Wynik kontraktu jest przed podatkiem.

**Implementacja jest gotowa do niezależnego audytu przed scaleniem.**
