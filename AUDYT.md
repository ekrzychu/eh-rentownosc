# Audyt wspólnej obsady i rekonsyliacji kosztów

Data: 19 października 2026.
Gałąź: `feature/role-based-timeline-costs`. Punkt wyjścia: `3a8fddc`.
Katalog roboczy przed zmianami był czysty. Przed edycją uruchomiono pełne
193 testy; wszystkie przeszły. Przeczytano modele, analizy, konfigurację,
interfejsy i dotychczasowe testy. Nie wykonano merge ani push.

## Potwierdzone problemy

1. Panel 1 pobierał wynagrodzenie z niezależnego wejścia, podczas gdy Panel 2
   pobierał je z indywidualnej obsady. Zmiana osoby nie aktualizowała Panelu 1.
2. Panel 1 mnożył całą pracę przez `480/390`, mimo że EH ma 60 minut dziennych,
   a ugody 30. Zawyżało to godziny zasobu i koszty.
3. Stare założenia były powielone w porównaniach ugód, wycenie oszczędności
   i progach wynagrodzenia. Część testów utrwalała ten niewłaściwy rachunek.
4. Kontrakt miał poprawne miesięczne naliczanie aktywności, ale brakowało
   dostępnego w interfejsie pełnego uzgodnienia kosztów całego horyzontu.

Przed zmianą modeli uruchomiono niezależne zsumowanie scenariuszy A–G.
Już wtedy zachodziły niezmienność przepływów po zmianie narzutu oraz równość
różnicy wyniku z `−43 × sprawomiesiące`. Nie znaleziono w tych scenariuszach
podwójnych pensji, narzutu ani sekretariatu. Wyniki kontraktu po naprawie
lifecycle pozostały takie same i są zabezpieczone regresją.

## Jedno źródło stawek

`parametry["pracownicy"]` jest wspólną obsadą obu paneli. Stare wejście
„Wynagrodzenie pracownika / h” usunięto. Stara nazwa parametru jest odrzucana
z czytelnym komunikatem migracyjnym zamiast tworzyć drugi sposób wyceny.
Wartość 59,88 zł/h występuje w konfiguracji wyłącznie jako
`obsada.stawka_poczatkowa`, używana przy inicjalizacji nowej osoby.

Panel 1 liczy **średnią arytmetyczną** stawek osób danej roli mających
przydział większy od zera. Procent nie waży średniej. EH 50 i 70 zł/h daje
60 zł/h również przy przydziałach 100% oraz 1%. Przydział 0% wyłącza osobę
ze średniej. Przydział dodatni nie skaluje czasu lifecycle i nie wprowadza
limitu 167 h. Brak stawki wymaganej roli daje brak wyceny i wyraźny komunikat,
a Kontrakt w czasie pozostaje dostępny. Rola o zerowej pracy nie wymaga stawki.
W pustym segmencie hipotetycznie wymagającym brakującej stawki koszt
jednostkowy jest niedostępny, a udział w sumach wynosi zero.

Panel 2 nadal używa każdej stawki indywidualnie. Jego opcjonalny argument
`pracownicy` służy jawnemu podaniu składu scenariusza; interfejs przekazuje
wspólną listę, tę samą co Panelowi 1. Nie służy do tworzenia alternatywnej stawki.

## Wzory i ścieżka każdego kosztu

Dla Panelu 1:

```text
H_EH = minuty bezpośrednie EH / 60 × 480 / (480 − dzienne minuty EH)
H_UGODY = minuty bezpośrednie ugód / 60 × 480 / (480 − dzienne minuty ugód)
pensje lifecycle = H_EH × średnia stawka EH + H_UGODY × średnia stawka UGODY
narzut lifecycle = (H_EH + H_UGODY) × godzinowy narzut Panelu 1
sekretariat lifecycle = liczba spraw × minuty sekretariatu / 60 × stawka sekretariatu
koszt = pensje + narzut + sekretariat
wynik = przychód − koszt
```

Dla Panelu 2, osoby `i` z przydziałem `u_i` w procentach i stawką `w_i`:

```text
H_i = 167 × u_i / 100
pensja_i = H_i × w_i
czynności dzienne_i = H_i / 8 × dzienne minuty roli / 60
pojemność_i = max(H_i − czynności dzienne_i, 0)
podstawa opłat_m = aktywne na otwarciu_m + nowy wpływ_m
narzut_m = podstawa opłat_m × kwota ogólna na aktywną sprawę/mies.
sekretariat_m = podstawa opłat_m × kwota sekretariatu na aktywną sprawę/mies.
koszt_m = suma pensji_i + narzut_m + sekretariat_m
wynik_m = płatności z ugód i wyroków_m − koszt_m
```

| Wejście | Panel 1 | Panel 2 |
| --- | --- | --- |
| Stawki i przydziały obsady | Średnie osób z dodatnim przydziałem → godziny roli → pensje lifecycle | Indywidualne stawki × przydzielone godziny → pensje miesięczne |
| Godzinowy narzut Panelu 1 | Godziny obu ról × stawka → narzut lifecycle | Nie jest używany |
| Minuty i stawka sekretariatu Panelu 1 | Jednorazowy koszt każdej sprawy | Nie są używane |
| Narzut aktywności Panelu 2 | Nie jest używany | Sprawomiesiące × kwota miesięczna |
| Sekretariat aktywności Panelu 2 | Nie jest używany | Sprawomiesiące × kwota miesięczna |

W obu panelach sumy grup lub miesięcy trafiają do pełnego kosztu i wyniku.
Panel 1 zachowuje podatek od dodatniego wyniku. Panel 2 raportuje wynik przed
podatkiem. Nie dolicza kosztu wykonanej pracy do już opłaconych godzin ani
nie dodaje kosztów jednego panelu do drugiego. Sekretariat lifecycle nie
podlega mnożnikom prawników. Sekretariat i narzut aktywności pozostają miesięczne.

## Niezależne uzgodnienie godzin

Sześć udziałów i formuły przychodu nie zostały zmienione. Udział ugód to
0,2875, nieudanych prób z ofertą/projektem 0,2875, a analizy poza ramami 0,55.

```text
EH / sprawę = 30 + 0,7125 × 250 + 150,3 + 0,7125 × 0,5 × 210
            = 433,2375 min
UGODY / sprawę = 0,55 × 30 + 0,2875 × 55 + 0,2875 × 35
               = 42,375 min
```

| Wielkość | EH | UGODY | Razem |
| --- | ---: | ---: | ---: |
| Bezpośrednie minuty na 600 spraw | 259 942,5 | 25 425 | 285 367,5 |
| Godziny bezpośrednie rocznie | 4332,375 | 423,75 | 4756,125 |
| Mnożnik dzienny | 480/420 | 480/450 | Nie ma wspólnego mnożnika |
| Godziny zasobu rocznie | 4951,285714286 | 452 | 5403,285714286 |
| Godziny zasobu / sprawę | 8,252142857 | 0,753333333 | 9,005476190 |
| Miesięczny popyt bezpośredni | 361,03125 h | 35,3125 h | 396,34375 h |
| Pojemność jednej osoby 100% | 146,125 h | 156,5625 h | Pojemność nie jest zamienna |

Przy obu stawkach 59,88 zł/h i narzucie 36 zł/h: pensje lifecycle wynoszą
323 548,748571 zł, narzut 194 518,285714 zł, koszt 518 067,034286 zł,
przychód 451 963,254 zł i wynik −66 103,780286 zł (sekretariat i podatek 0).
Poprzedni koszt 561 252,018462 zł wynikał z błędnego wspólnego mnożnika,
nie ze zmiany minut ani przychodu.

## Scenariusze A–G i wynik po 60 miesiącach

W każdym scenariuszu wpływa 600 spraw/rok, łącznie 3000. Wszystkie osoby mają
przydział 100%, stawkę 59,88 zł/h i sekretariat aktywności 0, poza opisanymi
zmianami F/G. Terminy pozostają referencyjne. F/G są kontrolowanymi próbami
zmiany jednej stawki o +10 zł/h, nie nowymi domyślnymi wartościami.

| Scenariusz | Skład i narzut |
| --- | --- |
| A | 1 EH + 1 UGODY, narzut 0 |
| B | 1 EH + 1 UGODY, narzut 43 zł/sprawę/mies. |
| C | 3 EH + 1 UGODY, narzut 43 |
| D | Jak C, narzut 0 |
| E | 4 EH + 1 UGODY, narzut 43 |
| F | Jak C; pierwsza osoba EH ma 69,88 zł/h |
| G | Jak C; osoba UGODY ma 69,88 zł/h |

Wartości finansowe w poniższej tabeli są prezentowane do grosza; dane źródłowe
JSON i CSV zachowują pełną precyzję obliczeń. Sekretariat we wszystkich A–G = 0.

| Scenariusz | Przychód | Pensje EH | Pensje ugód | Narzut | Koszt całkowity | Wynik |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 861 416,45 | 599 997,60 | 599 997,60 | 0,00 | 1 199 995,20 | -338 578,75 |
| B | 861 416,45 | 599 997,60 | 599 997,60 | 2 633 649,70 | 3 833 644,90 | -2 972 228,46 |
| C | 1 911 367,66 | 1 799 992,80 | 599 997,60 | 1 315 114,69 | 3 715 105,09 | -1 803 737,43 |
| D | 1 911 367,66 | 1 799 992,80 | 599 997,60 | 0,00 | 2 399 990,40 | -488 622,74 |
| E | 1 911 367,66 | 2 399 990,40 | 599 997,60 | 1 315 114,69 | 4 315 102,69 | -2 403 735,03 |
| F | 1 911 367,66 | 1 900 192,80 | 599 997,60 | 1 315 114,69 | 3 815 305,09 | -1 903 937,43 |
| G | 1 911 367,66 | 1 799 992,80 | 700 197,60 | 1 315 114,69 | 3 815 305,09 | -1 903 937,43 |

| Scenariusz | Zakończenia | Aktywne na koniec | Sprawomiesiące | Backlog EH (h) | Backlog ugód (h) | Praca przyszła/zablokowana (h) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 1 082,249544 | 1 917,750456 | 61 247,667469 | 10 822,548095 | 0,000000 | 2 071,826905 |
| B | 1 082,249544 | 1 917,750456 | 61 247,667469 | 10 822,548095 | 0,000000 | 2 071,826905 |
| C | 2 486,250000 | 513,750000 | 30 584,062500 | 0,000000 | 0,000000 | 561,093750 |
| D | 2 486,250000 | 513,750000 | 30 584,062500 | 0,000000 | 0,000000 | 561,093750 |
| E | 2 486,250000 | 513,750000 | 30 584,062500 | 0,000000 | 0,000000 | 561,093750 |
| F | 2 486,250000 | 513,750000 | 30 584,062500 | 0,000000 | 0,000000 | 561,093750 |
| G | 2 486,250000 | 513,750000 | 30 584,062500 | 0,000000 | 0,000000 | 561,093750 |

W A/B z przyszłej pracy 1510,733155 h jest zablokowane pracą I instancji;
w pozostałych wariantach zablokowana część wynosi 0, a 561,09375 h to przyszła
II instancja ostatnich kohort. Te godziny nie są utracone ani wykonywane
przedwcześnie. Praca przyszła jest odrębna od backlogu pracy wymagalnej.

Punkty kontrolne **1, 6, 10, 16, 24, 36 i 60** dla każdego scenariusza,
z kompletem powyższych wielkości, są zapisane w:
[JSON](audit_results/rekonsyliacja.json) i [CSV](audit_results/rekonsyliacja.csv).

## Dowody niezmienności i pochodzenie dużej straty

B i A mają identyczne wszystkie miesięczne przepływy operacyjne, moce,
wykonanie obu ról, zakończenia i płatności. To samo dotyczy C i D.

```text
wynik B − wynik A = −2 633 649,7011739975 zł
                  = −43 × 61 247,66746916273 sprawomiesiąca
wynik C − wynik D = −1 315 114,6875 zł
                  = −43 × 30 584,0625 sprawomiesiąca
```

Zmiana stawki w F albo G nie zmienia pracy, zakończeń, aktywności ani
przychodów. Dodaje dokładnie `60 × 167 × 10 = 100 200 zł` pensji i obniża
wynik o tę kwotę. Średnie Panelu 1 nie zastępują indywidualnych pensji.

W B niedobór EH wynosi 214,90625 h/mies. Ugody nie mogą go pokryć. Po
60 miesiącach zakończono tylko 1082,249544 z 3000 spraw, a 1917,750456
pozostaje aktywnych. Koszt naliczono za 61 247,667469 sprawomiesiąca.
To powoduje duży narzut przy obniżonym i opóźnionym przychodzie.
Nawet w wystarczającej obsadzie formalnie otwarte sprawy bez backlogu
pozostają płatne: w C dojrzały miesiąc ma 563,75 spraw naliczających koszt
i 513,75 na koniec. Tak stanowi uzgodniona reguła aktywności.

**Podane ustawienia nie odtwarzają straty −4 mln zł.** Odtwarzają wynik
−2 972 228,46 zł oraz całkowity koszt 3 833 644,90 zł. Nie ma zapisu ustawień
historycznej obserwacji −4 mln zł, więc nie można uczciwie stwierdzić,
że dokładnie ta kwota była błędem albo wskazać jej pełnego pochodzenia.
Nie dopasowywano do niej parametrów i nie ograniczano straty.

Porównanie samych jednostek wyjaśnia, dlaczego 36 i 43 nie są porównywalnymi
stawkami: przy dwóch pełnych osobach `36 × 334 h × 60 = 721 440 zł` narzutu
 godzinowego, podczas gdy aktywność B daje 2 633 649,70 zł. To różnica
1 912 209,70 zł przy tym samym obserwowanym przepływie. Jest to porównanie
mechanizmów kosztu, a nie odtworzenie starego symulatora ze wspólną pulą.

Wniosek z dostępnych danych: **potwierdzone błędy były w wycenie Panelu 1;
zweryfikowana wielomilionowa strata kontraktu jest prawidłową konsekwencją
miesięcznej aktywności, niedoboru EH i opóźnionego przychodu.** Dokładna
historyczna obserwacja −4 mln zł pozostaje nieodtworzona.

## Walidacja i zakres niezależności

`diagnostic_costs.py` nie używa funkcji podsumowującej finanse, wyliczającej
pojemność ani wykonującej kolejki. Koszty odtwarza z indywidualnych wejść,
stan spraw z wpływu i zakończeń, a pracę z niezależnego rozwinięcia sześciu
ścieżek. Nie jest drugim niezależnym symulatorem harmonogramu: przyjmuje
zaobserwowane miesięczne zakończenia i przychody, których bramki, FIFO,
proporcje i zachowanie minut badają osobne testy regresyjne.

Oprócz A–G `audit_checks.py` sprawdza 30 deterministycznych konfiguracji
obsady, przydziałów, stawek, wpływu i terminów. Oba audyty: OK.

Przed edycją: 193/193 testów. Końcowe polecenia używają `.venv/bin/python`
zamiast niedostępnego globalnego `python`:

| Zestaw | Liczba testów | Wynik |
| --- | ---: | --- |
| `python -m unittest test_model -v` | 1 | OK |
| `python -m unittest test_analysis -v` | 1 | OK |
| `python -m unittest test_timeline -v` | 1 | OK |
| `python -m unittest test_app -v` | 1 | OK |
| `python -m unittest test_ui_timeline -v` | 1 | OK |
| `python -m unittest test_reconciliation -v` | 1 | OK |
| `python -m unittest` | 6 | OK |

Zachowano regresje sześciu ścieżek, udziałów, WPS, II instancji, bezpośrednich
minut, przychodu, FIFO, bramek, aktywności i podatku. Zastąpiono wyłącznie
założenia o niezależnej globalnej stawce, wspólnym obciążeniu dziennym i
sterowaniu rzeczywistą obsadą przez samą liczbę bez listy osób.

Nowe testy dowodzą średnich 50/70 → 60, nieuwzględniania zerowych przydziałów,
osobnych mnożników 60/30 min, stałego przychodu, braku limitu FTE w lifecycle,
wyceny każdej roli i sześciu ścieżek, zachowania wszystkich minut i bramek,
indywidualnych pensji, braku duplikacji kosztów oraz niezależności opłat paneli.
AppTests sprawdzają usunięcie ogólnego wejścia płacy, aktualizację obu paneli
po zmianie EH i UGODY, trwałość ustawień 2→3→2→3 i dostępność kontraktu przy
brakującej stawce. Sprawdzono też zero osób, brak jednej roli, zero wpływu,
zero kosztów, różne stawki, długie terminy i rosnący backlog obu ról.

Uruchomiono Streamlit oraz Chrome headless z osobnym profilem. Sprawdzono
oba panele, brak podwójnego wejścia wynagrodzenia i rozliczenie horyzontu.
Robocze zrzuty znajdują się w `/tmp/eh-wages-case.png`,
`/tmp/eh-wages-timeline.png` i `/tmp/eh-wages-totals.png`.
`git diff --check`: OK.

## Zmienione pliki i ograniczenia

- `model.py`: wspólny przepływ bez wyceny, podział minut i kosztów ról, progi jednej osoby.
- `staff.py`: średnie arytmetyczne z dodatnich przydziałów i inicjalizacja stawki.
- `analysis.py`: wrażliwość stawek konkretnych osób, osobna wycena pracy ugód i EH.
- `timeline.py`: użycie wspólnego przepływu i obsady, pełne podsumowanie finansowe; kolejki i bramki bez zmian.
- `app.py`, `ui_case.py`, `ui_timeline.py`: jedno wejście stawek, objaśnienie średnich i pełne rozliczenie.
- `config.py`, `defaults.toml`: stawka początkowa wyłącznie w konfiguracji obsady.
- `test_model.py`, `test_analysis.py`, `test_timeline.py`, `test_app.py`, `test_reconciliation.py`: migracja zastąpionych założeń i nowe dowody matematyczne.
- `diagnostic_costs.py`, `audit_results/rekonsyliacja.json`, `audit_results/rekonsyliacja.csv`: skrypt i pełne dane A–G.
- `README.md`, `AUDYT.md`: aktualny opis reguł i ten raport.

`test_ui_timeline.py` i `audit_checks.py` uruchomiono bez zmiany. Nie zmieniono
reguł wynagrodzenia za wynik sprawy, udziałów, miksu, definicji aktywności,
harmonogramu ani przychodów. Nie wprowadzono nowych domyślnych stawek biznesowych.

Brak znanych blokad w uzgodnionym zakresie. Dokładna obserwacja −4 mln zł
wymaga historycznych ustawień; nie jest podstawą do zmiany reguł lub
wymuszenia wyniku. Wycenę lifecycle przy braku stawki celowo oznacza się jako
niedostępną. Ustawienia pozostają sesyjne. API usuwa globalny parametr płacy;
konsumenci powinni przekazywać wspólną listę `pracownicy`.
Nie dodano sezonowości, urlopów, inflacji ani modelowania terminów zapłaty podatku.

**READY FOR INDEPENDENT AUDIT — gotowe do niezależnego audytu.**
