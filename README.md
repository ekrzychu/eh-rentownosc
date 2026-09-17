# EH Rentowność

A local Streamlit application for analysing the profitability of EH cases.

## Requirements

- Python 3
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

## Ekonomia kohorty i model „W czasie”

Aplikacja pokazuje dwa powiązane, ale odrębne ujęcia ekonomiczne:

- główny model cyklu życia wycenia pełną ekonomię referencyjnej rocznej
  kohorty spraw jako koszt zużytego zasobu pracowników oraz jeden roczny koszt
  stały całej operacji;
- sekcja **W czasie** symuluje ciągłe działanie firmy przy stałym napływie.
  Wartość „Roczny napływ spraw” jest dzielona przez 12 i taka oczekiwana
  kohorta pojawia się w każdym miesiącu horyzontu.

Stawka `koszt_staly_na_godzine` oznacza koszt całej operacji w godzinie jej
działania. Nie jest kosztem pracownika ani kosztem godziny pracy nad sprawą.
Rocznie jest naliczana raz jako `stawka × dni pracy × 8 godzin`, także przy
zerowym napływie lub zerowej obsadzie. Koszt pracy kohorty to wymagane godziny
zasobu pracowników pomnożone wyłącznie przez stawkę wynagrodzenia. Przy
dodatnim napływie koszt stały jest rozdzielany równo na sprawy tylko na potrzeby
raportowania segmentów; nie staje się przez to kosztem zależnym od aktywności.

Model czasowy nalicza w każdym miesiącu jeden koszt stały operacji oraz payroll
utrzymywanej obsady. Liczba pracowników mnoży wyłącznie płatne godziny
pracowników, nigdy koszt stały. Czynności dzienne zużywają część pojemności bez
tworzenia drugiego kosztu. Bezpośrednia praca nad sprawami trafia do kolejki
FIFO. Jeżeli pojemność jest za mała, backlog narasta, zakończenia spraw się
opóźniają, a przychód czeka na wykonanie wymaganej pracy. Koszt
niewykorzystanej pojemności oznacza wyłącznie płatny, niewykorzystany czas
pracowników i jest wyceniany stawką wynagrodzenia.

Oba widoki stosują tę samą fizyczną definicję dnia pracy: pracownik ma 480
płatnych minut, w których mieszczą się zarówno czynności dzienne, jak i praca
nad sprawami. Jeśli czynności dzienne zajmują `D` minut, jedna osobodniówka
dostarcza `480 - D` minut pracy nad sprawami. Koszt zasobu przypisany do kohorty
jest więc oparty na czasie `bezpośrednie minuty × 480 / (480 - D)`. Model
czasowy stosuje tę samą relację przy wyznaczaniu pojemności, lecz nalicza pełny
koszt faktycznie utrzymywanej obsady, także jej niewykorzystanego czasu.

Widok **W czasie** rozdziela nową pracę przypadającą na miesiąc, pracę już
oczekującą, pracę wykonaną oraz backlog na koniec. Osobno pokazuje deficyt
rozruchowy, koszt niewykorzystanej pojemności i strukturalny niedobór obsady.
Dlatego dodatnia marża kohorty lifecycle może współistnieć ze stratą czasową:
kohorta zużywa tylko potrzebny zasób, natomiast najmniejsza wykonalna całkowita
obsada może dostarczać więcej płatnych godzin niż potrzeba. Różnica rocznych
kosztów modeli jest wtedy równa niewykorzystanym godzinom pracowników razy ich
stawka. Zbyt mała obsada powoduje z kolei rosnący backlog i opóźnienie przychodu.

Główny KPI break-even pokazuje wyłącznie trwały break-even: wynik skumulowany
wrócił do co najmniej zera, nie spadł później pod zero, pojemność jest wykonalna,
a dojrzały wynik miesięczny jest dodatni. Pierwsze surowe przecięcie zera jest
osobną diagnostyką i może być nietrwałe. Status „Na granicy” jest wykonalny,
ale oznacza brak bufora pojemności.

Obecna wersja nie modeluje terminów płatności podatku, podwyżek wynagrodzeń i
inflacji, sezonowości napływu, rzeczywistych historycznych rozkładów czasu,
świąt ani zmiennej długości miesięcy oraz zróżnicowanych ról pracowników.
