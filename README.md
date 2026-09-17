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
  kohorty spraw: przychód, pracę zużytą przez sprawy, koszt i wynik całego
  cyklu;
- sekcja **W czasie** symuluje ciągłe działanie firmy przy stałym napływie.
  Wartość „Roczny napływ spraw” jest dzielona przez 12 i taka oczekiwana
  kohorta pojawia się w każdym miesiącu horyzontu.

Model czasowy nalicza co miesiąc pełny koszt dostarczonej obsady. Liczba
pracowników wyznacza pojemność brutto, a czynności dzienne zużywają jej część
bez tworzenia drugiego kosztu. Bezpośrednia praca nad sprawami trafia do kolejki
FIFO. Jeżeli pojemność jest za mała, backlog narasta, zakończenia spraw się
opóźniają, a przychód czeka na wykonanie wymaganej pracy. Niewykorzystana
pojemność jest pokazywana zarządczo, ale jej koszt nadal pozostaje częścią
pełnego kosztu zespołu.

Break-even skumulowany oznacza pierwszy miesiąc po początkowym deficycie, w
którym skumulowany wynik przed podatkiem wraca do co najmniej zera. Przecięcie
nie jest oznaczane jako trwałe, jeżeli pojemność jest niewystarczająca albo
dojrzały wynik miesięczny pozostaje ujemny.

Obecna wersja nie modeluje terminów płatności podatku, podwyżek wynagrodzeń i
inflacji, sezonowości napływu, rzeczywistych historycznych rozkładów czasu,
świąt ani zmiennej długości miesięcy oraz zróżnicowanych ról pracowników.
