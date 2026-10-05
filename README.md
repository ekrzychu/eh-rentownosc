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

Parametr `koszt_staly_na_godzine` oznacza **narzut
kosztów ogólnych przypisany do jednej płatnej godziny pracownika**. Nie jest to
jeden globalny koszt operacji. Narzut nie zawiera wynagrodzenia, które jest
liczone osobno. Koszt płatnej godziny zasobu wynosi więc:

```text
36,00 zł/h narzutu + 59,88 zł/h wynagrodzenia = 95,88 zł/h
```

W cyklu życia koszt skaluje się z wymaganymi godzinami zasobu. Przykładowo:

```text
2 000 h × 95,88 zł/h = 191 760,00 zł
```

Wynik jest taki sam niezależnie od tego, czy pracę rozdzielono teoretycznie na
1, 2 czy 10 pracowników. Model używa oczekiwanych, niezaokrąglonych liczebności
P1/P2/P3 i grup WPS, dlatego identyczny miks spraw zachowuje ten sam koszt,
przychód i marżę na sprawę przy zmianie wolumenu.

Model czasowy wycenia natomiast pełną utrzymywaną obsadę. Jedynym źródłem
pojemności i kosztu etatu jest dokładnie **167 płatnych godzin miesięcznie na
FTE**. Przykładowo:

```text
1 FTE × 167 h × 95,88 zł/h = 16 011,96 zł/miesiąc
```

Pełny koszt powstaje także wtedy, gdy pracownik jest niedociążony. Czynności
dzienne mieszczą się wewnątrz 167 godzin: dla `D` minut dziennie ich miesięczny
czas to `(167 / 8) × D / 60`, a pozostała część jest pojemnością na sprawy.
Bezpośrednia praca trafia do kolejki FIFO. Jeżeli pojemność jest za mała,
backlog narasta, zakończenia spraw się opóźniają, a przychód czeka na wykonanie
wymaganej pracy. Niewykorzystane płatne godziny są wyceniane pełną stawką
narzutu i wynagrodzenia.

Oba widoki stosują tę samą fizyczną definicję dnia pracy: pracownik ma 480
płatnych minut, w których mieszczą się zarówno czynności dzienne, jak i praca
nad sprawami. Jeśli czynności dzienne zajmują `D` minut, jedna osobodniówka
dostarcza `480 - D` minut pracy nad sprawami. Koszt zasobu przypisany do kohorty
jest więc oparty na czasie `bezpośrednie minuty × 480 / (480 - D)`. Model
czasowy zachowuje tę samą proporcję w ramach dokładnie 167 godzin miesięcznie
i nalicza pełny koszt utrzymywanej obsady, także jej niewykorzystanego czasu.

Widok **Kontrakt w czasie** rozdziela nową pracę przypadającą na miesiąc, pracę już
oczekującą, pracę wykonaną oraz backlog na koniec. Osobno pokazuje deficyt
rozruchowy, koszt niewykorzystanej pojemności i strukturalny niedobór obsady.
Dlatego dodatnia marża cyklu życia kohorty może współistnieć ze stratą czasową:
kohorta zużywa tylko potrzebny zasób, natomiast całkowita obsada może dostarczać
więcej płatnych godzin niż potrzeba. Różnica kosztów jest wtedy równa bilansowi
godzin razy pełna stawka 95,88 zł/h. Zbyt mała obsada powoduje z kolei rosnący
backlog i opóźnienie przychodu.

KPI **Break-even finansowy** pokazuje pierwszy powrót wyniku skumulowanego z
deficytu do co najmniej zera. Nie znika, gdy pojemność jest niewystarczająca.
Osobny, jawnie wyjaśniony **status kontraktu** najpierw ocenia ekonomię pełnego
cyklu życia sprawy, a następnie sprawdza koszt minimalnej stabilnej obsady i
pełny koszt bieżącej obsady. Zbyt mały zespół nie jest więc uznawany za
rentowny tylko dlatego, że jego bieżący koszt jest niski. Trwałość break-even
pozostaje dostępna w diagnostyce. Status „Na granicy” jest wykonalny, ale
oznacza brak bufora pojemności.

Obecna wersja nie modeluje terminów płatności podatku, podwyżek wynagrodzeń i
inflacji, sezonowości napływu, rzeczywistych historycznych rozkładów czasu,
świąt ani zmiennej długości miesięcy oraz zróżnicowanych ról pracowników.

## Założenia referencyjne

`defaults.toml` jest jedynym źródłem aktualnych empirycznych i organizacyjnych
założeń referencyjnych, w tym terminów modelu czasowego. Wzory pozostają w Pythonie.
Zmiana wartości domyślnej nie wymaga zmiany kodu modelu. Założenia należy
aktualizować świadomie, gdy dostępne są lepsze dane rzeczywiste.
