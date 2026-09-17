"""Deterministyczne analizy decyzyjne oparte wyłącznie na ``oblicz_model``."""

from math import ceil, floor

from model import oblicz_model


KOPIOWANE_SLOWNIKI = (
    "wspolne_czynnosci",
    "procesowe_czynnosci",
    "ugodowe_czynnosci",
    "codzienne_czynnosci",
    "dodatkowe_minuty",
    "udzialy_rodzajow",
)

# Jedno źródło prawdy dla analiz zarządczych. Prefiksy obejmują wszystkie
# edytowalne czasy czynności, także czasy dzienne i dodatkowe P1/P2/P3.
PARAMETRY_STEROWALNE = frozenset({
    "srednia_kwota_ugody",
    "koszt_staly",
    "wynagrodzenie",
    "szansa_na_ugode",
    "zawarte_ugody",
    "czas_ii_instancji",
    "analiza_ugody",
})
STEROWALNE_PREFIKSY = (
    "wspolne:",
    "procesowe:",
    "ugodowe:",
    "codzienne:",
    "dodatkowe:",
)


def czy_parametr_sterowalny(identyfikator: str) -> bool:
    """Określa sterowalność na podstawie stabilnego identyfikatora parametru."""
    return identyfikator in PARAMETRY_STEROWALNE or identyfikator.startswith(
        STEROWALNE_PREFIKSY
    )


def kopiuj_parametry(parametry: dict) -> dict:
    kopia = dict(parametry)
    for nazwa in KOPIOWANE_SLOWNIKI:
        kopia[nazwa] = parametry[nazwa].copy()
    return kopia


def sredni_bezposredni_czas_na_sprawe(parametry: dict) -> float:
    """Zwraca średni bezpośredni czas obsługi jednej sprawy w minutach."""
    wyniki = oblicz_model(parametry)
    liczba_spraw = wyniki["ogolem"]["liczba_spraw"]
    return wyniki["bezposrednie_minuty_spraw"] / liczba_spraw if liczba_spraw else 0.0


def ustaw_sredni_bezposredni_czas(parametry: dict, minuty_na_sprawe: float) -> dict:
    """Skaluje proporcjonalnie wszystkie bezpośrednie czasy przypisane do spraw."""
    obecny_czas = sredni_bezposredni_czas_na_sprawe(parametry)
    if obecny_czas <= 0:
        if abs(minuty_na_sprawe) <= 1e-12:
            return kopiuj_parametry(parametry)
        raise ValueError("Nie można skalować zerowego bezpośredniego czasu spraw.")
    skala = minuty_na_sprawe / obecny_czas
    if skala < 0:
        raise ValueError("Średni bezpośredni czas spraw nie może być ujemny.")
    wynik = kopiuj_parametry(parametry)
    for klucz in ("wspolne_czynnosci", "procesowe_czynnosci", "ugodowe_czynnosci", "dodatkowe_minuty"):
        wynik[klucz] = {nazwa: wartosc * skala for nazwa, wartosc in parametry[klucz].items()}
    wynik["analiza_mozliwosci_ugody"] = parametry["analiza_mozliwosci_ugody"] * skala
    wynik["obsluga_ii_instancji_minuty"] = parametry["obsluga_ii_instancji_minuty"] * skala
    return wynik


def definicja_sredniego_czasu(parametry: dict) -> dict:
    obecnie = sredni_bezposredni_czas_na_sprawe(parametry)
    return {
        "id": "sredni_czas_bezposredni",
        "nazwa": "Średni bezpośredni czas na sprawę",
        "kategoria": "Operacyjne",
        "jednostka": "min",
        "typ": "czas",
        "min": 0.0,
        "max": max(1440.0, obecnie * 5),
        "krok": 10.0,
    }


def przelicz_udzial_rodzaju(udzialy: dict[str, float], rodzaj: str, nowy_udzial: float) -> dict[str, float]:
    """Zmienia jeden udział P, zachowując proporcję dwóch pozostałych."""
    wynik = udzialy.copy()
    pozostale = [nazwa for nazwa in wynik if nazwa != rodzaj]
    reszta = 100.0 - nowy_udzial
    suma_pozostalych = sum(udzialy[nazwa] for nazwa in pozostale)
    wynik[rodzaj] = nowy_udzial
    if suma_pozostalych:
        for nazwa in pozostale:
            wynik[nazwa] = reszta * udzialy[nazwa] / suma_pozostalych
    else:
        for nazwa in pozostale:
            wynik[nazwa] = reszta / len(pozostale)
    return wynik


def definicje_parametrow(parametry: dict) -> list[dict]:
    """Buduje katalog dźwigni z aktualnych, a nie historycznych parametrów."""
    definicje = [
        {"id": "koszt_staly", "nazwa": "Koszt stały / h", "kategoria": "Kosztowe", "jednostka": "zł/h", "typ": "liczba", "min": 0.0, "max": max(1000.0, parametry["koszt_staly_na_godzine"] * 10 + 100), "krok": 10.0},
        {"id": "wynagrodzenie", "nazwa": "Wynagrodzenie pracownika / h", "kategoria": "Kosztowe", "jednostka": "zł/h", "typ": "liczba", "min": 0.0, "max": max(1000.0, parametry["wynagrodzenie_pracownika_na_godzine"] * 10 + 100), "krok": 10.0},
        {"id": "srednia_kwota_ugody", "nazwa": "Średnia kwota ugody", "kategoria": "Warunki ekonomiczne", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0, "krok": 5.0},
        {"id": "srednia_kwota_wyroku", "nazwa": "Średnia kwota wyroku", "kategoria": "Warunki ekonomiczne", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0, "krok": 5.0},
        {"id": "podatek_dochodowy", "nazwa": "Podatek dochodowy", "kategoria": "Warunki ekonomiczne", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0, "krok": 5.0},
        {"id": "niski_wps", "nazwa": "Średni WPS poniżej progu", "kategoria": "Warunki ekonomiczne", "jednostka": "zł", "typ": "liczba", "min": 0.0, "max": max(0.0, parametry["prog_wps"] - 0.001), "krok": 1000.0},
        {"id": "wysoki_wps", "nazwa": "Średni WPS od progu wzwyż", "kategoria": "Warunki ekonomiczne", "jednostka": "zł", "typ": "liczba", "min": parametry["prog_wps"], "max": max(parametry["wysoki_wps"] * 4, parametry["prog_wps"] + 100_000), "krok": 1000.0},
        {"id": "kategoryczna_odmowa", "nazwa": "Kategoryczna odmowa", "kategoria": "Ugody", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0 - parametry["automatyczne_ramy_percent"], "krok": 5.0},
        {"id": "automatyczne_ramy", "nazwa": "Automatyczne ramy", "kategoria": "Ugody", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0 - parametry["kategoryczna_odmowa_percent"], "krok": 5.0},
        {"id": "szansa_na_ugode", "nazwa": "Szansa na ugodę poza ramami", "kategoria": "Ugody", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0, "krok": 5.0},
        {"id": "zawarte_ugody", "nazwa": "Zawarte ugody", "kategoria": "Ugody", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0, "krok": 5.0},
        {"id": "udzial_ii_instancji", "nazwa": "Udział spraw w II instancji", "kategoria": "Operacyjne", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0, "krok": 5.0},
        {"id": "czas_ii_instancji", "nazwa": "Obsługa sprawy w II instancji", "kategoria": "Operacyjne", "podkategoria": "II instancja", "jednostka": "min", "typ": "czas", "min": 0.0, "max": max(1440.0, parametry["obsluga_ii_instancji_minuty"] + 1440), "krok": 10.0},
        {"id": "wysoki_wps_procent", "nazwa": "Udział wysokiego WPS", "kategoria": "Struktura portfela", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0, "krok": 5.0},
        {"id": "liczba_spraw", "nazwa": "Liczba spraw", "kategoria": "Struktura portfela", "jednostka": "spraw", "typ": "calkowita", "min": 0, "max": max(1000, parametry["liczba_spraw"] * 3 + 500), "krok": 50},
    ]
    for rodzaj in parametry["udzialy_rodzajow"]:
        definicje.append({"id": f"udzial:{rodzaj}", "nazwa": f"Udział {rodzaj}", "kategoria": "Struktura portfela", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0, "krok": 5.0})
    grupy_czasu = (
        ("wspolne", "wspolne_czynnosci", "Czynności wspólne"),
        ("procesowe", "procesowe_czynnosci", "Czynności procesowe"),
        ("ugodowe", "ugodowe_czynnosci", "Czynności ugodowe"),
        ("codzienne", "codzienne_czynnosci", "Czynności dzienne"),
        ("dodatkowe", "dodatkowe_minuty", "Dodatkowy czas P1/P2/P3"),
    )
    for prefiks, klucz, podkategoria in grupy_czasu:
        for nazwa, wartosc in parametry[klucz].items():
            definicje.append({"id": f"{prefiks}:{nazwa}", "nazwa": nazwa if prefiks != "dodatkowe" else f"Dodatkowy czas {nazwa}", "kategoria": "Operacyjne", "podkategoria": podkategoria, "jednostka": "min", "typ": "czas", "min": 0.0, "max": max(1440.0, wartosc + 1440), "krok": 10.0})
    definicje.append({"id": "analiza_ugody", "nazwa": "Analiza możliwości ugody", "kategoria": "Operacyjne", "podkategoria": "Czynności ugodowe", "jednostka": "min", "typ": "czas", "min": 0.0, "max": max(1440.0, parametry["analiza_mozliwosci_ugody"] + 1440), "krok": 10.0})
    return definicje


def sterowalne_definicje_parametrow(parametry: dict) -> list[dict]:
    """Zwraca wyłącznie parametry, którymi kancelaria może realnie zarządzać."""
    return [
        definicja for definicja in definicje_parametrow(parametry)
        if czy_parametr_sterowalny(definicja["id"])
    ]


def wartosc_parametru(parametry: dict, identyfikator: str) -> float:
    if identyfikator == "sredni_czas_bezposredni":
        return sredni_bezposredni_czas_na_sprawe(parametry)
    proste = {
        "koszt_staly": "koszt_staly_na_godzine", "wynagrodzenie": "wynagrodzenie_pracownika_na_godzine",
        "srednia_kwota_ugody": "srednia_kwota_ugody_percent",
        "srednia_kwota_wyroku": "srednia_kwota_wyroku_percent",
        "podatek_dochodowy": "podatek_dochodowy_percent",
        "niski_wps": "niski_wps", "wysoki_wps": "wysoki_wps",
        "kategoryczna_odmowa": "kategoryczna_odmowa_percent", "automatyczne_ramy": "automatyczne_ramy_percent",
        "szansa_na_ugode": "szansa_na_ugode_percent", "zawarte_ugody": "zawarte_ugody_percent",
        "udzial_ii_instancji": "udzial_ii_instancji_percent", "czas_ii_instancji": "obsluga_ii_instancji_minuty",
        "wysoki_wps_procent": "wysoki_wps_procent", "liczba_spraw": "liczba_spraw",
        "liczba_pracownikow": "liczba_pracownikow", "analiza_ugody": "analiza_mozliwosci_ugody",
    }
    if identyfikator in proste:
        return parametry[proste[identyfikator]]
    prefiks, nazwa = identyfikator.split(":", 1)
    if prefiks == "udzial":
        return parametry["udzialy_rodzajow"][nazwa]
    klucze = {"wspolne": "wspolne_czynnosci", "procesowe": "procesowe_czynnosci", "ugodowe": "ugodowe_czynnosci", "codzienne": "codzienne_czynnosci", "dodatkowe": "dodatkowe_minuty"}
    return parametry[klucze[prefiks]][nazwa]


def ustaw_parametr(parametry: dict, identyfikator: str, wartosc: float) -> dict:
    """Zmienia dokładnie jedną dźwignię, zachowując semantykę modelu."""
    if identyfikator == "sredni_czas_bezposredni":
        return ustaw_sredni_bezposredni_czas(parametry, wartosc)
    wynik = kopiuj_parametry(parametry)
    proste = {
        "koszt_staly": "koszt_staly_na_godzine", "wynagrodzenie": "wynagrodzenie_pracownika_na_godzine",
        "srednia_kwota_ugody": "srednia_kwota_ugody_percent",
        "srednia_kwota_wyroku": "srednia_kwota_wyroku_percent",
        "podatek_dochodowy": "podatek_dochodowy_percent",
        "niski_wps": "niski_wps", "wysoki_wps": "wysoki_wps",
        "kategoryczna_odmowa": "kategoryczna_odmowa_percent", "automatyczne_ramy": "automatyczne_ramy_percent",
        "szansa_na_ugode": "szansa_na_ugode_percent", "zawarte_ugody": "zawarte_ugody_percent",
        "udzial_ii_instancji": "udzial_ii_instancji_percent", "czas_ii_instancji": "obsluga_ii_instancji_minuty",
        "wysoki_wps_procent": "wysoki_wps_procent", "liczba_spraw": "liczba_spraw",
        "liczba_pracownikow": "liczba_pracownikow", "analiza_ugody": "analiza_mozliwosci_ugody",
    }
    if identyfikator in ("liczba_spraw", "liczba_pracownikow"):
        wartosc = int(round(wartosc))
    if identyfikator in proste:
        wynik[proste[identyfikator]] = wartosc
        return wynik
    prefiks, nazwa = identyfikator.split(":", 1)
    if prefiks == "udzial":
        wynik["udzialy_rodzajow"] = przelicz_udzial_rodzaju(parametry["udzialy_rodzajow"], nazwa, wartosc)
        return wynik
    klucze = {"wspolne": "wspolne_czynnosci", "procesowe": "procesowe_czynnosci", "ugodowe": "ugodowe_czynnosci", "codzienne": "codzienne_czynnosci", "dodatkowe": "dodatkowe_minuty"}
    wynik[klucze[prefiks]][nazwa] = wartosc
    return wynik


def spelnia_cel(wyniki: dict, docelowa_marza: float) -> bool:
    ogolem = wyniki["ogolem"]
    if docelowa_marza <= 0:
        return ogolem["wynik"] >= -1e-7
    return ogolem["przychod"] > 0 and ogolem["marza"] >= docelowa_marza - 1e-7


def wykorzystanie_pojemnosci(wyniki: dict) -> float | None:
    dostepne = wyniki["pojemnosc"]["pojemnosc_spraw_minuty"]
    if dostepne <= 0:
        return None
    return wyniki["bezposrednie_minuty_spraw"] / dostepne * 100


def status_operacyjny(wyniki: dict) -> dict:
    return {
        "wykonalne": not wyniki["pojemnosc"]["przekroczona"],
        "wykorzystanie": wykorzystanie_pojemnosci(wyniki),
    }


def _wynik_dla(parametry: dict, identyfikator: str, wartosc: float) -> dict | None:
    try:
        return oblicz_model(ustaw_parametr(parametry, identyfikator, wartosc))
    except ValueError:
        return None


def _spelnia_dla(parametry: dict, identyfikator: str, wartosc: float, cel: float) -> bool:
    wyniki = _wynik_dla(parametry, identyfikator, wartosc)
    return wyniki is not None and spelnia_cel(wyniki, cel)


def _granica_ciagla(parametry: dict, identyfikator: str, bezpieczna: float, niebezpieczna: float, cel: float) -> float:
    for _ in range(48):
        srodek = (bezpieczna + niebezpieczna) / 2
        if _spelnia_dla(parametry, identyfikator, srodek, cel):
            bezpieczna = srodek
        else:
            niebezpieczna = srodek
    return bezpieczna


def _granica_calkowita(parametry: dict, identyfikator: str, bezpieczna: float, niebezpieczna: float, cel: float) -> int:
    bezpieczna = int(round(bezpieczna))
    niebezpieczna = int(round(niebezpieczna))
    while abs(bezpieczna - niebezpieczna) > 1:
        srodek = (bezpieczna + niebezpieczna) // 2
        if _spelnia_dla(parametry, identyfikator, srodek, cel):
            bezpieczna = srodek
        else:
            niebezpieczna = srodek
    return bezpieczna


def _punkty(koniec: float, poczatek: float, calkowity: bool) -> list[float]:
    odleglosc = koniec - poczatek
    if not odleglosc:
        return []
    if calkowity:
        if abs(odleglosc) <= 250:
            krok = 1 if odleglosc > 0 else -1
            return list(range(int(round(poczatek)) + krok, int(round(koniec)) + krok, krok))
        punkty = [int(round(poczatek + odleglosc * i / 64)) for i in range(1, 65)]
        return list(dict.fromkeys(punkty))
    return [poczatek + odleglosc * i / 64 for i in range(1, 65)]


def znajdz_granice(parametry: dict, definicja: dict, docelowa_marza: float) -> dict:
    """Znajduje najbliższą granicę metodą skanowania i bisekcji."""
    identyfikator = definicja["id"]
    obecnie = float(wartosc_parametru(parametry, identyfikator))
    obecnie_spelnia = _spelnia_dla(parametry, identyfikator, obecnie, docelowa_marza)
    calkowity = definicja["typ"] == "calkowita"
    kandydaci = []
    for koniec in (float(definicja["min"]), float(definicja["max"])):
        poprzednia_wartosc = obecnie
        poprzedni_stan = obecnie_spelnia
        for punkt in _punkty(koniec, obecnie, calkowity):
            stan = _spelnia_dla(parametry, identyfikator, punkt, docelowa_marza)
            if stan != poprzedni_stan:
                if obecnie_spelnia:
                    bezpieczna, niebezpieczna = poprzednia_wartosc, punkt
                else:
                    bezpieczna, niebezpieczna = punkt, poprzednia_wartosc
                granica = (
                    _granica_calkowita(parametry, identyfikator, bezpieczna, niebezpieczna, docelowa_marza)
                    if calkowity
                    else _granica_ciagla(parametry, identyfikator, bezpieczna, niebezpieczna, docelowa_marza)
                )
                kandydaci.append(granica)
                break
            poprzednia_wartosc, poprzedni_stan = punkt, stan
    if not kandydaci:
        return {"parametr": definicja["nazwa"], "id": identyfikator, "kategoria": definicja["kategoria"], "jednostka": definicja["jednostka"], "obecnie": obecnie, "typ": "bufor" if obecnie_spelnia else "wymagana_zmiana", "osiagalne": False, "granica": None, "zmiana": None}
    granica = min(kandydaci, key=lambda x: abs(x - obecnie))
    return {"parametr": definicja["nazwa"], "id": identyfikator, "kategoria": definicja["kategoria"], "jednostka": definicja["jednostka"], "obecnie": obecnie, "typ": "bufor" if obecnie_spelnia else "wymagana_zmiana", "osiagalne": True, "granica": granica, "zmiana": granica - obecnie}


def analizuj_progi(parametry: dict, docelowa_marza: float) -> dict:
    wyniki = oblicz_model(parametry)
    definicje = definicje_parametrow(parametry)
    return {"cel_spelniony": spelnia_cel(wyniki, docelowa_marza), "docelowa_marza": docelowa_marza, "pozycje": [znajdz_granice(parametry, definicja, docelowa_marza) for definicja in definicje]}


def kluczowe_progi(parametry: dict, docelowa_marza: float, analiza_progow: dict | None = None) -> dict:
    """Buduje podsumowanie z tych samych progów, które trafiają do pełnej tabeli."""
    if analiza_progow is None:
        analiza_progow = analizuj_progi(parametry, docelowa_marza)
    po_id = {pozycja["id"]: pozycja for pozycja in analiza_progow["pozycje"]}
    return {
        "cel_spelniony": analiza_progow["cel_spelniony"],
        "docelowa_marza": docelowa_marza,
        "sredni_czas_bezposredni": znajdz_granice(
            parametry, definicja_sredniego_czasu(parametry), docelowa_marza
        ),
        "koszt_staly": po_id["koszt_staly"],
        "wynagrodzenie": po_id["wynagrodzenie"],
        "srednia_kwota_ugody": po_id["srednia_kwota_ugody"],
        "srednia_kwota_wyroku": po_id["srednia_kwota_wyroku"],
        "podatek_dochodowy": po_id["podatek_dochodowy"],
        "zawarte_ugody": po_id["zawarte_ugody"],
    }


def analiza_wrazliwosci(parametry: dict, zmiana_percent: float = 10.0) -> list[dict]:
    """Bada względną zmianę wyłącznie sterowalnych parametrów, po jednym naraz."""
    if zmiana_percent <= 0:
        raise ValueError("Zmiana analizowanego parametru musi być dodatnia.")
    bazowe = oblicz_model(parametry)
    bazowy_wynik = bazowe["ogolem"]["wynik"]
    bazowa_marza = bazowe["ogolem"]["marza"]
    wiersze = []
    for definicja in sterowalne_definicje_parametrow(parametry):
        identyfikator = definicja["id"]
        obecnie = float(wartosc_parametru(parametry, identyfikator))
        if abs(obecnie) <= 1e-12:
            continue
        scenariusze = []
        for znak in (-1, 1):
            nowa = obecnie * (1 + znak * zmiana_percent / 100)
            if definicja["typ"] == "calkowita":
                nowa = floor(nowa) if znak < 0 else ceil(nowa)
            nowa = min(
                float(definicja["max"]),
                max(float(definicja["min"]), nowa),
            )
            zmienione = ustaw_parametr(parametry, identyfikator, nowa)
            rzeczywista = float(wartosc_parametru(zmienione, identyfikator))
            if rzeczywista == obecnie:
                continue
            wyniki = oblicz_model(zmienione)
            wynik = wyniki["ogolem"]["wynik"]
            marza = wyniki["ogolem"]["marza"]
            scenariusze.append({
                "wartosc": rzeczywista,
                "zmiana": rzeczywista - obecnie,
                "wynik": wynik,
                "wplyw": wynik - bazowy_wynik,
                "marza": marza,
                "wplyw_marza": marza - bazowa_marza,
                "zmiana_percent": (rzeczywista / obecnie - 1) * 100,
            })
        if not scenariusze:
            continue
        korzystny = max(scenariusze, key=lambda x: x["wplyw"])
        niekorzystny = min(scenariusze, key=lambda x: x["wplyw"])
        wiersze.append({
            "Parametr": definicja["nazwa"], "Id": identyfikator,
            "Kategoria": definicja["kategoria"], "Obecnie": obecnie,
            "Jednostka": definicja["jednostka"],
            "Zmiana analizowana (%)": zmiana_percent,
            "Zmiana porównawcza": korzystny["zmiana"],
            "Wartość po zmianie": korzystny["wartosc"],
            "Wynik bazowy": bazowy_wynik, "Wynik po zmianie": korzystny["wynik"],
            "Wpływ na wynik": korzystny["wplyw"],
            "Marża bazowa": bazowa_marza, "Marża po zmianie": korzystny["marza"],
            "Wpływ na marżę": korzystny["wplyw_marza"],
            "Kierunek poprawy": "wzrost" if korzystny["zmiana"] > 0 else "spadek",
            "Korzystna zmiana": korzystny["zmiana"],
            "Korzystna zmiana (%)": korzystny["zmiana_percent"],
            "Wartość po korzystnej zmianie": korzystny["wartosc"],
            "Wpływ korzystny": korzystny["wplyw"],
            "Marża po korzystnej zmianie": korzystny["marza"],
            "Wpływ korzystny na marżę": korzystny["wplyw_marza"],
            "Niekorzystna zmiana": niekorzystny["zmiana"],
            "Niekorzystna zmiana (%)": niekorzystny["zmiana_percent"],
            "Wartość po niekorzystnej zmianie": niekorzystny["wartosc"],
            "Wpływ niekorzystny": niekorzystny["wplyw"],
            "Wynik po niekorzystnej zmianie": niekorzystny["wynik"],
            "Marża po niekorzystnej zmianie": niekorzystny["marza"],
            "Wpływ niekorzystny na marżę": niekorzystny["wplyw_marza"],
            # Aliasy utrzymują zgodność dotychczasowego API analitycznego.
            "Wynik obecny": bazowy_wynik, "Marża obecna": bazowa_marza,
            "Zmiana testowa": korzystny["zmiana"],
            "Wartość po poprawie": korzystny["wartosc"],
            "Wpływ na wynik roczny": korzystny["wplyw"],
            "Wynik po poprawie": korzystny["wynik"],
            "Marża po poprawie": korzystny["marza"],
            "Wynik po pogorszeniu": niekorzystny["wynik"],
            "Marża po pogorszeniu": niekorzystny["marza"],
        })
    return sorted(
        wiersze,
        key=lambda x: abs(x["Wpływ korzystny"]),
        reverse=True,
    )


def analiza_wplywu_wzglednego(
    parametry: dict, zmiana_wzgledna: float = 0.10
) -> list[dict]:
    """Zgodnościowy interfejs wspólnego silnika; 0,10 oznacza zmianę o 10%."""
    return analiza_wrazliwosci(parametry, zmiana_percent=zmiana_wzgledna * 100)


def wartosc_skrocenia_czynnosci(parametry: dict) -> list[dict]:
    bazowy = oblicz_model(parametry)["ogolem"]["wynik"]
    wiersze = []
    for definicja in sterowalne_definicje_parametrow(parametry):
        if definicja["typ"] != "czas":
            continue
        obecnie = float(wartosc_parametru(parametry, definicja["id"]))
        wartosci = {}
        for minuty in (1, 10):
            nowa = max(0.0, obecnie - minuty)
            wartosci[minuty] = oblicz_model(ustaw_parametr(parametry, definicja["id"], nowa))["ogolem"]["wynik"] - bazowy
        wiersze.append({"Czynność": definicja["nazwa"], "Kategoria": definicja.get("podkategoria", definicja["kategoria"]), "Wpływ skrócenia o 1 min": wartosci[1], "Wpływ skrócenia o 10 min": wartosci[10]})
    return sorted(wiersze, key=lambda x: x["Wpływ skrócenia o 10 min"], reverse=True)


def ekonomika_ugod(parametry: dict) -> dict:
    wyniki = oblicz_model(parametry)
    udzialy = wyniki["udzialy_ugod"]
    czasy_podstawowe = wyniki["czasy_sciezek_ugod"]
    czasy_ii_instancji = wyniki["czasy_ii_instancji_sciezek"]
    pelne_czasy_sciezek = wyniki["czasy_sciezek_z_ii_instancja"]
    liczba_spraw = parametry["liczba_spraw"]
    koszt_godziny = wyniki["koszt_godziny"]
    dzienne_minuty = sum(parametry["codzienne_czynnosci"].values())
    produktywne_minuty = 480 - dzienne_minuty
    if produktywne_minuty <= 0:
        raise ValueError(
            "Czynności dzienne zużywają cały dzień pracy; "
            "nie można wycenić oszczędności czasu spraw."
        )
    mnoznik_kosztu_lifecycle = 480 / produktywne_minuty
    nazwy = {
        "kategoryczna_odmowa": "Kategoryczna odmowa", "automatyczne_ramy": "Automatyczne ramy",
        "brak_szans": "Brak szans na ugodę", "zawarte_poza_ramami": "Szansa poza ramami → zawarte ugody",
        "brak_ugody_poza_ramami": "Szansa poza ramami → brak ugody",
    }
    sciezki = [{"Ścieżka": etykieta, "Efektywny udział portfela": udzialy[klucz], "Czas podstawowy ścieżki": czasy_podstawowe[klucz], "Oczekiwany czas II instancji": czasy_ii_instancji[klucz], "Łączny oczekiwany czas ścieżki": pelne_czasy_sciezek[klucz], "Oczekiwana liczba spraw": liczba_spraw * udzialy[klucz] / 100} for klucz, etykieta in nazwy.items()]
    porownania_def = (
        ("Automatyczne ramy w porównaniu z brakiem szans na ugodę", "automatyczne_ramy", "brak_szans", "automatyczne_ramy"),
        ("Zawarta ugoda poza ramami w porównaniu z brakiem ugody poza ramami", "zawarte_poza_ramami", "brak_ugody_poza_ramami", "zawarte_poza_ramami"),
        ("Brak ugody poza ramami w porównaniu z brakiem szans na ugodę", "brak_ugody_poza_ramami", "brak_szans", "brak_ugody_poza_ramami"),
    )
    porownania = []
    for etykieta, wariant, odniesienie, udzial_klucz in porownania_def:
        oszczednosc_minut = (
            pelne_czasy_sciezek[odniesienie]
            - pelne_czasy_sciezek[wariant]
        )
        oszczednosc_pln = (
            oszczednosc_minut / 60 * koszt_godziny * mnoznik_kosztu_lifecycle
        )
        porownania.append({"Porównanie": etykieta, "Różnica minut na sprawę": oszczednosc_minut, "Różnica PLN na sprawę": oszczednosc_pln, "Wpływ roczny przy obecnym udziale": oszczednosc_pln * liczba_spraw * udzialy[udzial_klucz] / 100})

    bez_prob = oblicz_model(ustaw_parametr(parametry, "szansa_na_ugode", 0.0))
    wynik_bez_prob = bez_prob["ogolem"]["wynik"]
    wynik_zero_sukcesu = oblicz_model(
        ustaw_parametr(parametry, "zawarte_ugody", 0.0)
    )["ogolem"]["wynik"]
    wynik_pelnego_sukcesu = oblicz_model(
        ustaw_parametr(parametry, "zawarte_ugody", 100.0)
    )["ogolem"]["wynik"]
    if wynik_zero_sukcesu >= wynik_bez_prob - 1e-9:
        minimalna_skutecznosc = 0.0
    elif wynik_pelnego_sukcesu >= wynik_bez_prob - 1e-9:
        dol, gora = 0.0, 100.0
        for _ in range(48):
            srodek = (dol + gora) / 2
            wynik_scenariusza = oblicz_model(
                ustaw_parametr(parametry, "zawarte_ugody", srodek)
            )["ogolem"]["wynik"]
            if wynik_scenariusza >= wynik_bez_prob:
                gora = srodek
            else:
                dol = srodek
        minimalna_skutecznosc = gora
    else:
        minimalna_skutecznosc = None

    bazowy_wynik = wyniki["ogolem"]["wynik"]
    wartosc_poprawy = []
    for punkty in (1, 5, 10):
        nowa = min(100.0, parametry["zawarte_ugody_percent"] + punkty)
        wyniki_poprawy = oblicz_model(ustaw_parametr(parametry, "zawarte_ugody", nowa))
        wartosc_poprawy.append({"Zmiana": nowa - parametry["zawarte_ugody_percent"], "Wpływ na wynik roczny": wyniki_poprawy["ogolem"]["wynik"] - bazowy_wynik})

    przychod_wedlug_zakonczenia = [
        {"Sposób zakończenia": "Sprawy zakończone ugodą", "Oczekiwany udział": udzialy["zakonczone_ugoda"], "Oczekiwana liczba spraw": liczba_spraw * udzialy["zakonczone_ugoda"] / 100, "Oczekiwany przychód": wyniki["ogolem"]["przychod_ugody"]},
        {"Sposób zakończenia": "Sprawy zakończone wyrokiem", "Oczekiwany udział": udzialy["bez_ugody"], "Oczekiwana liczba spraw": liczba_spraw * udzialy["bez_ugody"] / 100, "Oczekiwany przychód": wyniki["ogolem"]["przychod_wyroki"]},
        {"Sposób zakończenia": "Razem", "Oczekiwany udział": 100.0, "Oczekiwana liczba spraw": liczba_spraw, "Oczekiwany przychód": wyniki["ogolem"]["przychod"]},
    ]
    return {"sciezki": sciezki, "porownania": porownania, "przychod_wedlug_zakonczenia": przychod_wedlug_zakonczenia, "minimalna_skutecznosc": minimalna_skutecznosc, "obecna_skutecznosc": parametry["zawarte_ugody_percent"], "bufor_skutecznosci": None if minimalna_skutecznosc is None else parametry["zawarte_ugody_percent"] - minimalna_skutecznosc, "wartosc_poprawy": wartosc_poprawy, "strategia_wplyw_pln": bazowy_wynik - wynik_bez_prob, "strategia_wplyw_godzin": bez_prob["laczne_godziny"] - wyniki["laczne_godziny"]}


def minimalna_liczba_pracownikow(parametry: dict, limit: int = 1000) -> int | None:
    for liczba in range(limit + 1):
        wynik = oblicz_model(ustaw_parametr(parametry, "liczba_pracownikow", liczba))
        if not wynik["pojemnosc"]["przekroczona"]:
            return liczba
    return None


def maksymalna_liczba_spraw(parametry: dict, limit: int = 1_000_000) -> int | None:
    przy_zerowym_wolumenie = oblicz_model(ustaw_parametr(parametry, "liczba_spraw", 0))
    if przy_zerowym_wolumenie["pojemnosc"]["przekroczona"]:
        return None
    if oblicz_model(ustaw_parametr(parametry, "liczba_spraw", 1))["bezposrednie_minuty_spraw"] <= 0:
        return None
    dol, gora = 0, max(1, parametry["liczba_spraw"])
    while gora < limit and not oblicz_model(ustaw_parametr(parametry, "liczba_spraw", gora))["pojemnosc"]["przekroczona"]:
        dol, gora = gora, min(limit, gora * 2)
    if gora == limit and not oblicz_model(ustaw_parametr(parametry, "liczba_spraw", gora))["pojemnosc"]["przekroczona"]:
        return None
    while dol + 1 < gora:
        srodek = (dol + gora) // 2
        if oblicz_model(ustaw_parametr(parametry, "liczba_spraw", srodek))["pojemnosc"]["przekroczona"]:
            gora = srodek
        else:
            dol = srodek
    return dol


def analiza_pojemnosci(parametry: dict) -> dict:
    wyniki = oblicz_model(parametry)
    pojemnosc = wyniki["pojemnosc"]
    maksimum = maksymalna_liczba_spraw(parametry)
    wynik_jednej_sprawy = oblicz_model(ustaw_parametr(parametry, "liczba_spraw", 1))
    if pojemnosc["brak_czasu_na_sprawy"]:
        powod_braku_maksimum = "brak_pojemnosci"
    elif wynik_jednej_sprawy["bezposrednie_minuty_spraw"] <= 0:
        powod_braku_maksimum = "zerowy_czas_sprawy"
    elif maksimum is None:
        powod_braku_maksimum = "poza_zakresem"
    else:
        powod_braku_maksimum = None
    punkty = {max(0, int(round(parametry["liczba_spraw"] * mnoznik))) for mnoznik in (0.5, 0.75, 1.0, 1.25, 1.5)}
    if maksimum is not None:
        punkty.add(maksimum)
    wolumeny = []
    for liczba_spraw in sorted(punkty):
        wynik = oblicz_model(ustaw_parametr(parametry, "liczba_spraw", liczba_spraw))
        wolumeny.append({"Liczba spraw": liczba_spraw, "Przychód": wynik["ogolem"]["przychod"], "Koszt": wynik["ogolem"]["koszt"], "Wynik po podatku": wynik["ogolem"]["wynik"], "Marża po podatku": wynik["ogolem"]["marza"], "Wykorzystanie pojemności": wykorzystanie_pojemnosci(wynik)})

    rentowne = []
    if maksimum is not None:
        krok = 1 if maksimum <= 10_000 else max(1, maksimum // 2000)
        for liczba_spraw in range(0, maksimum + 1, krok):
            if spelnia_cel(oblicz_model(ustaw_parametr(parametry, "liczba_spraw", liczba_spraw)), 0.0):
                rentowne.append(liczba_spraw)
    segmenty = []
    for grupa in wyniki["grupy"]:
        przychod = grupa["oczekiwane_wynagrodzenie"]
        segmenty.append({"Segment": f"{grupa['rodzaj']} / {'WPS poniżej progu' if grupa['grupa_wps'] == 'niski_wps' else 'WPS od progu wzwyż'}", "Liczba spraw": grupa["liczba"], "Przychód na sprawę": przychod, "Koszt na sprawę": grupa["koszt"], "Wynik przed podatkiem na sprawę": grupa["wynik_jednostkowy"], "Marża przed podatkiem": grupa["wynik_jednostkowy"] / przychod * 100 if przychod else 0.0, "Łączny wynik przed podatkiem": grupa["laczny_wynik"]})
    segmenty.sort(key=lambda x: x["Wynik przed podatkiem na sprawę"], reverse=True)
    return {
        "liczba_pracownikow": parametry["liczba_pracownikow"], "dni_pracy": parametry["liczba_dni_pracy_w_roku"],
        "godziny_brutto": pojemnosc["pojemnosc_brutto_minuty"] / 60, "godziny_dzienne": pojemnosc["czynnosci_dzienne_minuty"] / 60,
        "godziny_na_sprawy": max(0.0, pojemnosc["pojemnosc_spraw_minuty"]) / 60, "godziny_wymagane": pojemnosc["bezposrednie_minuty_spraw"] / 60,
        "wykorzystanie": wykorzystanie_pojemnosci(wyniki), "wolne_godziny": max(0.0, pojemnosc["pojemnosc_spraw_minuty"] - pojemnosc["bezposrednie_minuty_spraw"]) / 60,
        "minimalni_pracownicy": minimalna_liczba_pracownikow(parametry), "maksymalne_sprawy": maksimum,
        "powod_braku_maksimum": powod_braku_maksimum,
        "dodatkowe_sprawy": max(0, maksimum - parametry["liczba_spraw"]) if maksimum is not None else None,
        "wolumeny": wolumeny, "minimalny_rentowny_wolumen": min(rentowne) if rentowne else None,
        "maksymalny_rentowny_wolumen": max(rentowne) if rentowne else None, "segmenty": segmenty,
    }


def symuluj_pojedyncza_zmiane(parametry: dict, identyfikator: str, nowa_wartosc: float) -> dict:
    bazowe = oblicz_model(parametry)
    zmienione_parametry = ustaw_parametr(parametry, identyfikator, nowa_wartosc)
    scenariusz = oblicz_model(zmienione_parametry)
    def metryki(wynik: dict) -> dict:
        return {
            "Przychód": wynik["ogolem"]["przychod"],
            "Koszt": wynik["ogolem"]["koszt"],
            "Wynik przed podatkiem": wynik["ogolem"]["wynik_przed_podatkiem"],
            "Podatek dochodowy": wynik["ogolem"]["podatek_dochodowy"],
            "Wynik po podatku": wynik["ogolem"]["wynik_po_podatku"],
            "Marża po podatku": wynik["ogolem"]["marza_po_podatku"],
            "Godziny pracy": wynik["laczne_godziny"],
        }
    obecnie, po_zmianie = metryki(bazowe), metryki(scenariusz)
    roznica = {nazwa: po_zmianie[nazwa] - obecnie[nazwa] for nazwa in obecnie}
    return {"parametry": zmienione_parametry, "obecnie": obecnie, "scenariusz": po_zmianie, "roznica": roznica, "wyniki": scenariusz}


def ranking_progow(
    progi: dict, typ: str, limit: int = 5, tylko_sterowalne: bool = False
) -> list[dict]:
    """Porównuje finansowe granice według najmniejszej względnej zmiany."""
    pozycje = []
    for pozycja in progi["pozycje"]:
        if (
            pozycja["typ"] != typ
            or not pozycja["osiagalne"]
            or not pozycja["obecnie"]
            or (tylko_sterowalne and not czy_parametr_sterowalny(pozycja["id"]))
        ):
            continue
        pozycje.append({
            **pozycja,
            "zmiana_wzgledna": abs(pozycja["zmiana"]) / abs(pozycja["obecnie"]),
        })
    return sorted(pozycje, key=lambda x: x["zmiana_wzgledna"])[:limit]


def rekomendacje_deterministyczne(wrazliwosc: list[dict], progi: dict, ugody: dict, pojemnosc: dict | None = None) -> dict:
    """Buduje rekomendacje wyłącznie z parametrów sterowalnych."""
    korzystne = [
        wiersz for wiersz in wrazliwosc
        if wiersz["Wpływ na wynik roczny"] > 0
        and czy_parametr_sterowalny(wiersz["Id"])
    ]
    top = sorted(
        korzystne, key=lambda x: abs(x["Wpływ na wynik roczny"]), reverse=True
    )[:5]
    segmenty = pojemnosc.get("segmenty", []) if pojemnosc else []
    bufory = ranking_progow(progi, "bufor", tylko_sterowalne=True)
    drogi_do_celu = ranking_progow(
        progi, "wymagana_zmiana", tylko_sterowalne=True
    )
    return {
        "najwiekszy_wplyw": top,
        "najsilniejszy_segment": segmenty[0] if segmenty else None,
        "najslabszy_segment": segmenty[-1] if segmenty else None,
        "ugody": ugody,
        "najmniejsze_bufory": bufory,
        "najkrotsze_drogi": drogi_do_celu,
    }
