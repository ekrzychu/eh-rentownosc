# EH Rentowność

A local Streamlit application for analysing the profitability of EH cases.

## Requirements

- Python 3.11+
- `pip`
- A terminal / shell
- The project files, including `app.py` and `requirements.txt`

---

## Windows

### First-time setup

Open PowerShell in the project directory:

```powershell
cd H:\Projects\eh-rentownosc
```

Create a virtual environment:

```powershell
py -m venv .venv
```

Install the dependencies from `requirements.txt`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the application:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Using `python.exe -m streamlit` is the most reliable approach on Windows because it does not depend on `streamlit.exe` being available in the global `PATH`.

### Future runs

You do **not** need to reinstall the dependencies every time.

Open PowerShell and run:

```powershell
cd H:\Projects\eh-rentownosc
.\.venv\Scripts\python.exe -m streamlit run app.py
```

---

## Linux — Arch Linux

### First-time setup

Open a terminal and go to the project directory:

```bash
cd ~/path/to/eh-rentownosc
```

If Python is not installed:

```bash
sudo pacman -S python
```

Create a virtual environment:

```bash
python -m venv .venv
```

Install the dependencies:

```bash
./.venv/bin/python -m pip install -r requirements.txt
```

Start the application:

```bash
./.venv/bin/python -m streamlit run app.py
```

### Future runs

You do **not** need to reinstall the dependencies every time.

Run:

```bash
cd ~/path/to/eh-rentownosc
./.venv/bin/python -m streamlit run app.py
```

---

## macOS

### First-time setup

Open Terminal and go to the project directory:

```bash
cd ~/path/to/eh-rentownosc
```

Check that Python 3 is available:

```bash
python3 --version
```

Create a virtual environment:

```bash
python3 -m venv .venv
```

Install the dependencies:

```bash
./.venv/bin/python -m pip install -r requirements.txt
```

Start the application:

```bash
./.venv/bin/python -m streamlit run app.py
```

### Future runs

You do **not** need to reinstall the dependencies every time.

Run:

```bash
cd ~/path/to/eh-rentownosc
./.venv/bin/python -m streamlit run app.py
```

---

## Opening the application

After Streamlit starts, it will normally open the application automatically in your default browser.

If it does not, open the local address shown in the terminal, usually:

```text
http://localhost:8501
```

To stop the application, return to the terminal and press:

```text
Ctrl+C
```

---

## Running tests

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m unittest
```

Linux and macOS:

```bash
./.venv/bin/python -m unittest
```

---

## Dwa widoki modelu

Aplikacja odpowiada na dwa powiązane, ale odrębne pytania:

- **Ekonomika sprawy** pokazuje przychód, koszt i wynik oczekiwanej sprawy,
  strukturę ekonomiki oraz sterowalne dźwignie. Wartości całej referencyjnej
  kohorty i analizy zaawansowane pozostają dostępne jako szczegóły;
- **Kontrakt w czasie** symuluje ciągłe działanie firmy przy stałym napływie,
  pełnym koszcie obsady, kolejce pracy i terminach przychodów.
  Wartość „Roczny napływ spraw” jest dzielona przez 12 i taka oczekiwana
  kohorta pojawia się w każdym miesiącu horyzontu.

„Automatyczne ramy” oznaczają udział wszystkich spraw, w których ugodę można
obsłużyć bez dodatkowej analizy możliwości ugody. Nie przesądzają one wyniku:
osobny parametr określa, jaka część tych spraw faktycznie kończy się ugodą.
Domyślne drzewo sześciu rozłącznych wyników to:

```text
Kategoryczna odmowa                 15,00%
Automatyczne ramy → ugoda           15,00%
Automatyczne ramy → brak ugody      15,00%
Brak szans na ugodę                 27,50%
Poza ramami → zawarta ugoda         13,75%
Poza ramami → brak ugody            13,75%
```

Łącznie 28,75% spraw kończy się ugodą, a 71,25% bez ugody. Domyślnie 50%
spraw bez ugody przechodzi do II instancji; nie dotyczy to żadnej ścieżki
zakończonej ugodą.

## Wspólna obsada i dwie perspektywy kosztów

Jedynym źródłem stawek prawników jest **Obsada kontraktu**, wspólna dla obu
paneli. Każda osoba ma rolę EH albo UGODY, stawkę zł/h i procent przydziału
do projektu. `defaults.toml` zawiera 59,88 zł/h wyłącznie jako stawkę
początkową nowej osoby. Nie ma dodatkowego wejścia referencyjnej płacy.
Ustawienia osób są zachowywane przy zmianie ich liczby i przełączaniu widoków
w obrębie sesji Streamlit. Początkowe EH + UGODY to edytowalny przykład.

### Ekonomika sprawy

Stawka roli jest **średnią arytmetyczną stawek osób z dodatnim przydziałem**.
Przydział 1% i 100% ma taką samą wagę w tej średniej. Przydział 0% wyłącza
osobę ze średniej. Nie skaluje się godzin lifecycle procentem przydziału
ani limitem miesięcznych godzin.

Przykład: EH 50 i 70 zł/h oznacza średnią 60 zł/h; odrębna osoba UGODY
45 zł/h oznacza stawkę ugód 45 zł/h. Koszty każdej roli są liczone osobno.
Brak pracownika z dodatnim przydziałem wymaganej roli daje komunikat o braku
stawki; nie zastępuje się jej zerem. Kontrakt w czasie pozostaje dostępny.
Brak stawki roli o zerowym obciążeniu nie blokuje wyceny portfela.

```text
mnożnik EH = 480 / (480 − 60)
mnożnik ugód = 480 / (480 − 30)
godziny roli = bezpośrednie minuty roli × jej mnożnik / 60
wynagrodzenia = godziny EH × średnia EH + godziny ugód × średnia ugód
narzut = (godziny EH + godziny ugód) × godzinowy narzut Panelu 1
sekretariat = liczba spraw × minuty sekretariatu / 60 × stawka sekretariatu
koszt całkowity = wynagrodzenia + narzut + sekretariat
```

Referencyjna praca wynosi rocznie 259 942,5 min EH i 25 425 min ugód.
Razem 285 367,5 min, czyli 475,6125 min bezpośrednich na sprawę.
Po osobnych obciążeniach dziennych potrzeba 9,00547619 h zasobu na sprawę.
Przy obu stawkach 59,88 zł/h i narzucie 36 zł/h koszt to 863,44505714 zł
na sprawę. Przychód pozostaje 753,27209 zł na sprawę, wynik −110,17296714 zł.

Sekretariat jest jednorazowy i osobny: przykładowe 10 min × 50 zł/h / 60 to
8,333333 zł na sprawę, czyli 5000 zł dla 600 spraw. Nie zużywa pojemności
prawników i nie podlega ich mnożnikom. Kwoty nowych kosztów domyślnie wynoszą zero.

Sześć ścieżek, grupy P1/P2/P3, WPS, II instancja i drzewo przychodu pozostają
bez zmian. Analizy czasu, ugód i progów używają stawek i obciążeń właściwej
roli. Analiza stawki zmienia wynagrodzenie konkretnej osoby z obsady;
nie tworzy dodatkowego niezależnego parametru płacy. Pusty segment wymagający
brakującej stawki ma niedostępną wycenę jednostkową i zerowy udział w sumie.

### Kontrakt w czasie

Kontrakt nadal płaci indywidualne stawki za przydzielone godziny:

```text
godziny osoby = 167 × przydział / 100
pensja osoby = godziny osoby × jej indywidualna stawka
czynności dzienne osoby = godziny osoby / 8 × dzienne minuty jej roli / 60
pojemność na sprawy = max(godziny osoby − czynności dzienne osoby, 0)
```

Przykład: 60 zł/h i przydział 60% dają 100,2 h i 6012 zł/mies. Wykonanie
spraw nie powoduje ponownego naliczenia pensji. Niewykorzystane przydzielone
godziny pozostają płatne. Przydział 0% daje zerową pensję i pojemność.
Średnie stawek z Ekonomiki sprawy nie służą naliczaniu tych pensji.

EH obsługuje przyjęcie, proces, P1/P2/P3 i II instancję. Ugody obsługują
analizę, ofertę, projekt, podpisanie i nieudane próby. Dziennie EH obciąża
komunikacja i opłaty SOSS oraz umieszczanie dokumentów, a ugody — skrzynka.
Obie kolejki zachowują rozłączne zasoby, FIFO i proporcjonalny przydział.
Zwykła praca jest wymagalna od wpływu. II instancja wymaga terminu wyroku I
i wykonania wcześniejszych etapów obu ról. Kalendarzowe oczekiwanie nie
zwiększa pracy. Wszystkie etapy i nominalny termin blokują zakończenie,
a rzeczywiste zakończenie uruchamia płatność. II instancja nie zarabia przy wyroku I.

Narzut i sekretariat kontraktu mają niezależne kwoty miesięczne na aktywną
sprawę. Koszty i wyniki obu paneli są alternatywnymi perspektywami;
nie sumuje się ich ze sobą.

```text
podstawa opłat = stan aktywny na początku + nowy wpływ
stan aktywny na koniec = wpływ skumulowany − zakończenia skumulowane
koszt miesiąca = pensje EH + pensje ugód
                + podstawa × narzut kontraktu
                + podstawa × sekretariat kontraktu
wynik miesiąca = przychód z ugód i wyroków − koszt miesiąca
```

Miesiąc wpływu i rzeczywistego zakończenia są płatne. Po zakończeniu opłaty
ustają, także gdy płatność przychodzi później. Otwarta sprawa bez zaległej
pracy może nadal naliczać opłaty, czekając na formalne zakończenie.
Przykłady: 50 × 43 = 2150 zł; 1000 × 43 = 43 000 zł w jednym miesiącu.

Początkowa obsada ma 146,125 h EH przy miesięcznym popycie 361,03125 h
oraz 156,5625 h ugód przy popycie 35,3125 h. Nadmiar ugód nie zastępuje EH.
Backlog EH opóźnia zakończenia i przychód, a aktywne sprawy nadal generują
miesięczne koszty. Dla tej obsady narzut 43 zł daje po 60 miesiącach
−2 972 228,46 zł, w tym 2 633 649,70 zł samego narzutu.

W rozwijanym rozliczeniu horyzontu widać sumę pensji obu ról, narzutu,
sekretariatu, przychodu, kosztu i wyniku oraz sprawomiesiące, zakończenia,
stan aktywny, backlog obu ról i pracę przyszłą. Suma sprawomiesięcy razy
stawka kontraktu odtwarza skumulowany narzut.

Stabilność wymaga wystarczającej mocy obu ról. Dojrzałość wymaga 12 miesięcy
zgodnego przepływu, zakończeń, przychodu, aktywności i kosztów po najdłuższej
aktywnej ścieżce. Status finansowy nie zależy od marży Panelu 1. Trwały
break-even wymaga odzyskania deficytu bez późniejszego zejścia poniżej zera
w badanym horyzoncie i dodatniego potwierdzonego dojrzałego wyniku.

## Odtworzenie audytu

```bash
.venv/bin/python -m unittest
.venv/bin/python diagnostic_costs.py --output-dir audit_results
.venv/bin/python audit_checks.py
```

Skrypt diagnostyczny niezależnie odtwarza koszty i stany z wejść i miesięcznych
przepływów, bez pomocników finansowych i pojemnościowych modelu. Bada A–G oraz
miesiące 1, 6, 10, 16, 24, 36 i 60. F zmienia pierwszą stawkę EH w C o +10 zł/h,
a G stawkę ugód w C o +10 zł/h. JSON i CSV zawierają niezaokrąglone wartości.

Pełny raport: [AUDYT.md](AUDYT.md). Dane: [JSON](audit_results/rekonsyliacja.json),
[CSV](audit_results/rekonsyliacja.csv).

Model nie uwzględnia sezonowości, inflacji, urlopów i terminów zapłaty podatku.
Wynik kontraktu jest przed podatkiem dochodowym; Panel 1 zachowuje podatek
od dodatniego wyniku. Dane historycznej obserwacji około −4 mln zł nie zostały
utrwalone, więc tej dokładnej kwoty nie da się przypisać konkretnej konfiguracji.
