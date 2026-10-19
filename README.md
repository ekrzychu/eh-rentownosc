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

Model czasowy ma **niezależny rachunek kosztów**. Nie pobiera godzinowego
narzutu ani referencyjnej stawki pracy z Ekonomiki sprawy.

### Sekretariat w Ekonomice sprawy

Jednorazowy koszt to `minuty sekretariatu / 60 × stawka sekretariatu`.
Dotyczy każdej sprawy w kohorcie i wszystkich segmentów P1/P2/P3 oraz WPS.
Nie zwiększa minut pracy prawnika i nie podlega mnożnikowi czynności dziennych.
Wynagrodzenia prawników, godzinowy narzut i sekretariat są wykazane osobno.
Wrażliwość, podatek i progi rentowności uwzględniają cały ten koszt.

Przykład ilustracyjny przy pozostałych założeniach referencyjnych:
10 min × 50 zł/h / 60 = 8,333333 zł na sprawę, czyli 5000 zł dla 600 spraw.
Koszt sprawy rośnie z 935,42 do 943,75 zł. Przy przychodzie 753,27 zł wynik
na sprawę wynosi −190,48 zł, a wynik kohorty −114 288,76 zł (podatek 0%).

### Obsada i pojemność kontraktu

Dla każdego pracownika określa się rolę, stawkę godzinową i procent przydziału:

```text
godziny projektu = 167 × wykorzystanie / 100
wynagrodzenie projektu = godziny projektu × indywidualna stawka zł/h
ekwiwalent dni = godziny projektu / 8
czynności dzienne = ekwiwalent dni × minuty dzienne roli / 60
pojemność na sprawy = max(godziny projektu − czynności dzienne, 0)
```

Przykład: 60% przydziału i 60 zł/h to 100,2 płatnej godziny oraz 6012 zł/mies.
Prawnik EH z referencyjnymi 60 minutami czynności dziennych ma wtedy
87,675 h na sprawy. Przydział 0% daje zerowy koszt i zerową pojemność.
Niewykorzystany czas przydzielony do projektu pozostaje opłacony; wykonanie
pracy i czynności dziennych nie dodaje drugiego wynagrodzenia.

Role nie zastępują się:

- **EH**: przyjęcie, proces, dodatkowa praca P1/P2/P3, II instancja;
  czynności dzienne: komunikacja z EH i zlecanie opłat w SOSS oraz
  umieszczanie dokumentów w SOSS.
- **Ugody**: analiza możliwości ugody, oferta, projekt, podpisanie oraz
  nieudane próby; czynność dzienna: obsługa skrzynki ugody EH.

Obie kolejki zachowują FIFO między miesiącami wymagalności i proporcjonalny
przydział w tej samej dacie. Zwykła praca jest wymagalna przy wpływie.
Praca II instancji jest planowana od terminu wyroku I instancji, ale dostępna
wyłącznie dla tej oczekiwanej części grupy, która wykonała wszystkie etapy
I instancji obu ról. Odblokowana część trafia do FIFO z datą faktycznego odblokowania.
Zablokowana praca II instancji nie zatrzymuje pracy
potrzebnej do jej odblokowania. Cały pakiet II instancji nie jest rozkładany
na miesiące oczekiwania. Zakończenie wymaga wszystkich etapów i terminu
nominalnego, a dopiero rzeczywiste zakończenie uruchamia płatność.
Przy wyroku I instancji sprawa skierowana do II instancji nie otrzymuje przychodu.

Początkowe dwie osoby (EH i ugody, stawka z `defaults.toml`, przydział 100%)
to **edytowalny przykład**, nie opis rzeczywistej kancelarii. Nowy wiersz
pracownika jest inicjalizowany jako EH; rolę, stawkę i procent należy ustawić
jawnie. Zmniejszenie i ponowne zwiększenie liczby osób zachowuje ich ustawienia
w bieżącej sesji. Nie ma automatycznego doboru hipotetycznych etatów.
API porównań `porownaj_obsade(..., scenariusze={nazwa: lista_pracownikow})`
wymaga jawnego składu każdego wariantu.

### Koszty aktywnych spraw

Niezależne miesięczne kwoty w Kontrakcie w czasie:

```text
koszty ogólne = sprawy naliczające koszt × koszt ogólny / aktywną sprawę
sekretariat = sprawy naliczające koszt × koszt sekretariatu / aktywną sprawę
łączny koszt = wynagrodzenia EH + wynagrodzenia ugód + koszty ogólne + sekretariat
wynik miesięczny = płatności z zakończonych spraw − łączny koszt
```

Sprawa nalicza koszt w miesiącu wpływu, rzeczywistego zakończenia i we
wszystkich miesiącach pomiędzy, także przy natychmiastowym zakończeniu.
Miesięczna podstawa to stan otwarcia + nowy wpływ. Zakończenia pomniejszają
stan zamknięcia, a nie podstawę kosztu bieżącego miesiąca. Opóźnienie płatności
nie przedłuża aktywności. Oba stany są osobno oznaczone w interfejsie.
Dłuższe oczekiwanie może zwiększyć koszty aktywnych spraw bez dodawania pracy.

Przykład ilustracyjny kontraktu: 3 prawników EH po 20 zł/h i 1 prawnik ugód
po 30 zł/h, wszyscy z przydziałem 100%. Wynagrodzenia wynoszą
`3 × 167 × 20 + 167 × 30 = 15 030 zł/mies.`. Przy 50 aktywnych sprawach
oraz kwotach 43 zł i 7 zł koszt miesiąca to
`15 030 + 50 × 43 + 50 × 7 = 17 530 zł`.
Przy pozostałych założeniach referencyjnych dojrzały przepływ ma 563,75
spraw naliczających koszt w miesiącu i 513,75 spraw na koniec miesiąca.
Koszt wynosi wtedy 43 217,50 zł/mies., przychód 37 663,60 zł/mies.,
a wynik −5553,90 zł/mies. Zespół jest operacyjnie stabilny, ale kontrakt
jest nierentowny. Te przykładowe stawki nie są wartościami domyślnymi.

### Status, dojrzałość i break-even

Status zależy wyłącznie od kosztów i przepływów kontraktu. Ujemny wynik
Ekonomiki sprawy nie przesądza o stracie kontraktu; dodatni jej wynik
nie dowodzi rentowności indywidualnej obsady.

Stabilność wymaga wystarczającej pojemności **obu** ról. Diagnostyka pokazuje
wymaganą i dostępną pojemność oraz niedobór osobno dla EH i ugód.
Pojedyncza „minimalna obsada” i automatyczne warianty liczby etatów zostały
zastąpione, bo nie określały ról, stawek ani procentów przydziału.

Dojrzałość wymaga pełnych 12 miesięcy po najdłuższej aktywnej ścieżce i
opóźnieniu płatności. W tym okresie muszą uzgadniać się oczekiwane zakończenia
ugodowe, po I i II instancji, przychód, wykonanie pracy obu ról, zerowy backlog,
stabilne stany spraw i miesięczne koszty. Roczny przepływ spraw, pracy i
przychodu jest uzgadniany z kohortą lifecycle. Koszty paneli nie są ze sobą
uzgadniane, ponieważ stosują różne rachunki.

**Break-even finansowy** to pierwszy powrót wyniku skumulowanego z deficytu
do zera. **Trwały break-even** dodatkowo wymaga, by wynik nie spadł ponownie
poniżej zera w badanym horyzoncie, obie role miały moc, a potwierdzony
dojrzały wynik był dodatni po wszystkich kosztach aktywnych spraw.
Krótki rozruch nie potwierdza dojrzałej rentowności. Rosnący backlog wyklucza
trwały break-even. Deficyt rozruchowy jest raportowany oddzielnie od straty
strukturalnej i stabilności operacyjnej.

Model nie odwzorowuje terminów zapłaty podatku, podwyżek, inflacji,
sezonowości, historycznych rozkładów czasu, świąt ani zmiennej długości miesięcy.
Rachunek miesięczny i status kontraktu są przed podatkiem dochodowym.

## Założenia referencyjne i walidacja

`defaults.toml` pozostaje źródłem wartości referencyjnych. Nowe koszty mają
wartości zerowe, a przykładowy skład jest wyraźnie oddzielony od danych
referencyjnych. Wzory pozostają w Pythonie. Konfiguracja, parametry kosztów,
role, stawki i przydziały są walidowane jawnie.

Pełny raport aktualizacji, przykłady i zakres testów: [AUDYT.md](AUDYT.md).
