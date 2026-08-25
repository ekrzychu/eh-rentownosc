"""Deterministyczne analizy decyzyjne oparte wyłącznie na ``oblicz_model``."""

from model import oblicz_model


KOPIOWANE_SLOWNIKI = (
    "wspolne_czynnosci",
    "procesowe_czynnosci",
    "ugodowe_czynnosci",
    "codzienne_czynnosci",
    "dodatkowe_minuty",
    "udzialy_rodzajow",
)


def kopiuj_parametry(parametry: dict) -> dict:
    kopia = dict(parametry)
    for nazwa in KOPIOWANE_SLOWNIKI:
        kopia[nazwa] = parametry[nazwa].copy()
    return kopia


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
        {"id": "wynagrodzenie", "nazwa": "Wynagrodzenie / h", "kategoria": "Kosztowe", "jednostka": "zł/h", "typ": "liczba", "min": 0.0, "max": max(1000.0, parametry["wynagrodzenie_pracownika_na_godzine"] * 10 + 100), "krok": 10.0},
        {"id": "fin", "nazwa": "FIN", "kategoria": "Warunki ekonomiczne", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0, "krok": 5.0},
        {"id": "niski_wps", "nazwa": "Średni niski WPS", "kategoria": "Warunki ekonomiczne", "jednostka": "zł", "typ": "liczba", "min": 0.0, "max": max(0.0, parametry["prog_wps"] - 0.001), "krok": 1000.0},
        {"id": "wysoki_wps", "nazwa": "Średni wysoki WPS", "kategoria": "Warunki ekonomiczne", "jednostka": "zł", "typ": "liczba", "min": parametry["prog_wps"], "max": max(parametry["wysoki_wps"] * 4, parametry["prog_wps"] + 100_000), "krok": 1000.0},
        {"id": "kategoryczna_odmowa", "nazwa": "Kategoryczna odmowa", "kategoria": "Ugody", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0 - parametry["automatyczne_ramy_percent"], "krok": 5.0},
        {"id": "automatyczne_ramy", "nazwa": "Automatyczne ramy", "kategoria": "Ugody", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0 - parametry["kategoryczna_odmowa_percent"], "krok": 5.0},
        {"id": "szansa_na_ugode", "nazwa": "Szansa na ugodę poza ramami", "kategoria": "Ugody", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0, "krok": 5.0},
        {"id": "zawarte_ugody", "nazwa": "Zawarte ugody", "kategoria": "Ugody", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0, "krok": 5.0},
        {"id": "wysoki_wps_procent", "nazwa": "Udział wysokiego WPS", "kategoria": "Struktura portfela", "jednostka": "p.p.", "typ": "procent", "min": 0.0, "max": 100.0, "krok": 5.0},
        {"id": "liczba_spraw", "nazwa": "Liczba spraw", "kategoria": "Struktura portfela", "jednostka": "spraw", "typ": "cal-kowita", "min": 0, "max": max(1000, parametry["liczba_spraw"] * 3 + 500), "krok": 50},
        {"id": "liczba_pracownikow", "nazwa": "Liczba pracowników", "kategoria": "Operacyjne", "jednostka": "osób", "typ": "cal-kowita", "min": 0, "max": max(50, parametry["liczba_pracownikow"] * 4 + 10), "krok": 1},
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


def wartosc_parametru(parametry: dict, identyfikator: str) -> float:
    proste = {
        "koszt_staly": "koszt_staly_na_godzine", "wynagrodzenie": "wynagrodzenie_pracownika_na_godzine",
        "fin": "fin_percent", "niski_wps": "niski_wps", "wysoki_wps": "wysoki_wps",
        "kategoryczna_odmowa": "kategoryczna_odmowa_percent", "automatyczne_ramy": "automatyczne_ramy_percent",
        "szansa_na_ugode": "szansa_na_ugode_percent", "zawarte_ugody": "zawarte_ugody_percent",
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
    wynik = kopiuj_parametry(parametry)
    proste = {
        "koszt_staly": "koszt_staly_na_godzine", "wynagrodzenie": "wynagrodzenie_pracownika_na_godzine",
        "fin": "fin_percent", "niski_wps": "niski_wps", "wysoki_wps": "wysoki_wps",
        "kategoryczna_odmowa": "kategoryczna_odmowa_percent", "automatyczne_ramy": "automatyczne_ramy_percent",
        "szansa_na_ugode": "szansa_na_ugode_percent", "zawarte_ugody": "zawarte_ugody_percent",
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


def _spelnia_dla(parametry: dict, identyfikator: str, wartosc: float, cel: float) -> bool:
    try:
        return spelnia_cel(oblicz_model(ustaw_parametr(parametry, identyfikator, wartosc)), cel)
    except ValueError:
        return False


def _granica_ciagla(parametry: dict, identyfikator: str, bezpieczna: float, niebezpieczna: float, cel: float) -> float:
    for _ in range(48):
        srodek = (bezpieczna + niebezpieczna) / 2
        if _spelnia_dla(parametry, identyfikator, srodek, cel):
            bezpieczna = srodek
        else:
            niebezpieczna = srodek
    return bezpieczna


def _punkty(koniec: float, poczatek: float, calkowity: bool) -> list[float]:
    odleglosc = koniec - poczatek
    if not odleglosc:
        return []
    if calkowity and abs(odleglosc) <= 250:
        krok = 1 if odleglosc > 0 else -1
        return list(range(int(poczatek) + krok, int(koniec) + krok, krok))
    return [poczatek + odleglosc * i / 64 for i in range(1, 65)]


def znajdz_granice(parametry: dict, definicja: dict, docelowa_marza: float) -> dict:
    """Znajduje najbliższą granicę metodą skanowania i bisekcji."""
    identyfikator = definicja["id"]
    obecnie = float(wartosc_parametru(parametry, identyfikator))
    obecnie_spelnia = _spelnia_dla(parametry, identyfikator, obecnie, docelowa_marza)
    calkowity = definicja["typ"] == "cal-kowita"
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
                granica = bezpieczna if calkowity else _granica_ciagla(parametry, identyfikator, bezpieczna, niebezpieczna, docelowa_marza)
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


def analiza_wrazliwosci(parametry: dict) -> list[dict]:
    bazowy = oblicz_model(parametry)["ogolem"]["wynik"]
    wiersze = []
    for definicja in definicje_parametrow(parametry):
        obecnie = float(wartosc_parametru(parametry, definicja["id"]))
        scenariusze = []
        for znak in (-1, 1):
            nowa = min(float(definicja["max"]), max(float(definicja["min"]), obecnie + znak * definicja["krok"]))
            if nowa == obecnie:
                continue
            wynik = oblicz_model(ustaw_parametr(parametry, definicja["id"], nowa))["ogolem"]["wynik"]
            scenariusze.append((wynik - bazowy, nowa))
        if not scenariusze:
            continue
        korzystny = max(scenariusze)
        niekorzystny = min(scenariusze)
        wiersze.append({"Parametr": definicja["nazwa"], "Id": definicja["id"], "Kategoria": definicja["kategoria"], "Wynik obecny": bazowy, "Zmiana testowa": korzystny[1] - obecnie, "Wpływ na wynik roczny": korzystny[0], "Wynik po poprawie": bazowy + korzystny[0], "Zmiana niekorzystna": niekorzystny[1] - obecnie, "Wpływ niekorzystny": niekorzystny[0], "Wynik po pogorszeniu": bazowy + niekorzystny[0], "Kierunek poprawy": "wzrost" if korzystny[1] > obecnie else "spadek", "Jednostka": definicja["jednostka"]})
    return sorted(wiersze, key=lambda x: abs(x["Wpływ na wynik roczny"]), reverse=True)


def wartosc_skrocenia_czynnosci(parametry: dict) -> list[dict]:
    bazowy = oblicz_model(parametry)["ogolem"]["wynik"]
    wiersze = []
    for definicja in definicje_parametrow(parametry):
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
    czasy = wyniki["czasy_sciezek_ugod"]
    liczba_spraw = parametry["liczba_spraw"]
    koszt_godziny = wyniki["koszt_godziny"]
    nazwy = {
        "kategoryczna_odmowa": "Kategoryczna odmowa", "automatyczne_ramy": "Automatyczne ramy",
        "brak_szans": "Brak szans na ugodę", "zawarte_poza_ramami": "Szansa poza ramami → zawarte ugody",
        "brak_ugody_poza_ramami": "Szansa poza ramami → brak ugody",
    }
    sciezki = [{"Ścieżka": etykieta, "Efektywny udział portfela": udzialy[klucz], "Czas bazowy": czasy[klucz], "Liczba spraw — oczekiwana": liczba_spraw * udzialy[klucz] / 100} for klucz, etykieta in nazwy.items()]
    porownania_def = (
        ("Automatyczne ramy a ścieżka procesowa", "automatyczne_ramy", "brak_szans", "automatyczne_ramy"),
        ("Zawarta a niezawarta ugoda poza ramami", "zawarte_poza_ramami", "brak_ugody_poza_ramami", "zawarte_poza_ramami"),
        ("Nieudana próba a brak próby ugodowej", "brak_ugody_poza_ramami", "brak_szans", "brak_ugody_poza_ramami"),
    )
    porownania = []
    for etykieta, wariant, odniesienie, udzial_klucz in porownania_def:
        oszczednosc_minut = czasy[odniesienie] - czasy[wariant]
        oszczednosc_pln = oszczednosc_minut / 60 * koszt_godziny
        porownania.append({"Porównanie": etykieta, "Różnica minut / sprawa": oszczednosc_minut, "Różnica PLN / sprawa": oszczednosc_pln, "Wpływ roczny przy obecnym udziale": oszczednosc_pln * liczba_spraw * udzialy[udzial_klucz] / 100})

    czas_sukces = czasy["zawarte_poza_ramami"]
    czas_porada = czasy["brak_ugody_poza_ramami"]
    czas_bez_proby = czasy["brak_szans"]
    if czas_porada <= czas_bez_proby:
        minimalna_skutecznosc = 0.0
    elif czas_sukces < czas_porada:
        minimalna_skutecznosc = 100 * (czas_porada - czas_bez_proby) / (czas_porada - czas_sukces)
        minimalna_skutecznosc = min(100.0, max(0.0, minimalna_skutecznosc))
    else:
        minimalna_skutecznosc = None

    bazowy_wynik = wyniki["ogolem"]["wynik"]
    wartosc_poprawy = []
    for punkty in (1, 5, 10):
        nowa = min(100.0, parametry["zawarte_ugody_percent"] + punkty)
        wynik = oblicz_model(ustaw_parametr(parametry, "zawarte_ugody", nowa))["ogolem"]["wynik"]
        wartosc_poprawy.append({"Zmiana": nowa - parametry["zawarte_ugody_percent"], "Wpływ na wynik roczny": wynik - bazowy_wynik})

    bez_prob = oblicz_model(ustaw_parametr(parametry, "szansa_na_ugode", 0.0))
    return {"sciezki": sciezki, "porownania": porownania, "minimalna_skutecznosc": minimalna_skutecznosc, "obecna_skutecznosc": parametry["zawarte_ugody_percent"], "bufor_skutecznosci": None if minimalna_skutecznosc is None else parametry["zawarte_ugody_percent"] - minimalna_skutecznosc, "wartosc_poprawy": wartosc_poprawy, "strategia_wplyw_pln": bazowy_wynik - bez_prob["ogolem"]["wynik"], "strategia_oszczednosc_godzin": bez_prob["laczne_godziny"] - wyniki["laczne_godziny"]}


def _wykorzystanie(wyniki: dict) -> float | None:
    dostepne = wyniki["pojemnosc"]["pojemnosc_spraw_minuty"]
    if dostepne <= 0:
        return None
    return wyniki["bezposrednie_minuty_spraw"] / dostepne * 100


def minimalna_liczba_pracownikow(parametry: dict, limit: int = 1000) -> int | None:
    for liczba in range(limit + 1):
        wynik = oblicz_model(ustaw_parametr(parametry, "liczba_pracownikow", liczba))
        if not wynik["pojemnosc"]["przekroczona"]:
            return liczba
    return None


def maksymalna_liczba_spraw(parametry: dict, limit: int = 1_000_000) -> int | None:
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
    punkty = {max(0, int(round(parametry["liczba_spraw"] * mnoznik))) for mnoznik in (0.5, 0.75, 1.0, 1.25, 1.5)}
    if maksimum is not None:
        punkty.add(maksimum)
    wolumeny = []
    for liczba_spraw in sorted(punkty):
        wynik = oblicz_model(ustaw_parametr(parametry, "liczba_spraw", liczba_spraw))
        wolumeny.append({"Liczba spraw": liczba_spraw, "Przychód": wynik["ogolem"]["przychod"], "Koszt": wynik["ogolem"]["koszt"], "Wynik": wynik["ogolem"]["wynik"], "Marża": wynik["ogolem"]["marza"], "Wykorzystanie pojemności": _wykorzystanie(wynik)})

    rentowne = []
    if maksimum is not None:
        krok = 1 if maksimum <= 10_000 else max(1, maksimum // 2000)
        for liczba_spraw in range(0, maksimum + 1, krok):
            if spelnia_cel(oblicz_model(ustaw_parametr(parametry, "liczba_spraw", liczba_spraw)), 0.0):
                rentowne.append(liczba_spraw)
    segmenty = []
    for grupa in wyniki["grupy"]:
        przychod = grupa["wynagrodzenie"]
        segmenty.append({"Segment": f"{grupa['rodzaj']} / {'WPS poniżej progu' if grupa['grupa_wps'] == 'niski_wps' else 'WPS od progu wzwyż'}", "Liczba spraw": grupa["liczba"], "Przychód / sprawa": przychod, "Koszt / sprawa": grupa["koszt"], "Wynik / sprawa": grupa["wynik_jednostkowy"], "Marża": grupa["wynik_jednostkowy"] / przychod * 100 if przychod else 0.0, "Łączny wynik": grupa["laczny_wynik"]})
    segmenty.sort(key=lambda x: x["Wynik / sprawa"], reverse=True)
    return {
        "liczba_pracownikow": parametry["liczba_pracownikow"], "dni_pracy": parametry["liczba_dni_pracy_w_roku"],
        "godziny_brutto": pojemnosc["pojemnosc_brutto_minuty"] / 60, "godziny_dzienne": pojemnosc["czynnosci_dzienne_minuty"] / 60,
        "godziny_na_sprawy": max(0.0, pojemnosc["pojemnosc_spraw_minuty"]) / 60, "godziny_wymagane": pojemnosc["bezposrednie_minuty_spraw"] / 60,
        "wykorzystanie": _wykorzystanie(wyniki), "wolne_godziny": max(0.0, pojemnosc["pojemnosc_spraw_minuty"] - pojemnosc["bezposrednie_minuty_spraw"]) / 60,
        "minimalni_pracownicy": minimalna_liczba_pracownikow(parametry), "maksymalne_sprawy": maksimum,
        "dodatkowe_sprawy": max(0, maksimum - parametry["liczba_spraw"]) if maksimum is not None else None,
        "wolumeny": wolumeny, "minimalny_rentowny_wolumen": min(rentowne) if rentowne else None,
        "maksymalny_rentowny_wolumen": max(rentowne) if rentowne else None, "segmenty": segmenty,
    }


def symuluj_pojedyncza_zmiane(parametry: dict, identyfikator: str, nowa_wartosc: float) -> dict:
    bazowe = oblicz_model(parametry)
    zmienione_parametry = ustaw_parametr(parametry, identyfikator, nowa_wartosc)
    scenariusz = oblicz_model(zmienione_parametry)
    def metryki(wynik: dict) -> dict:
        return {"Przychód": wynik["ogolem"]["przychod"], "Koszt": wynik["ogolem"]["koszt"], "Wynik": wynik["ogolem"]["wynik"], "Marża": wynik["ogolem"]["marza"], "Godziny pracy": wynik["laczne_godziny"], "Wykorzystanie pojemności": _wykorzystanie(wynik)}
    obecnie, po_zmianie = metryki(bazowe), metryki(scenariusz)
    roznica = {nazwa: (po_zmianie[nazwa] - obecnie[nazwa]) if po_zmianie[nazwa] is not None and obecnie[nazwa] is not None else None for nazwa in obecnie}
    return {"parametry": zmienione_parametry, "obecnie": obecnie, "scenariusz": po_zmianie, "roznica": roznica, "wyniki": scenariusz}


def rekomendacje_deterministyczne(wrazliwosc: list[dict], progi: dict, ugody: dict, pojemnosc: dict) -> dict:
    top = [wiersz for wiersz in wrazliwosc if wiersz["Wpływ na wynik roczny"] > 0][:3]
    segmenty = pojemnosc["segmenty"]
    bufory = []
    for pozycja in progi["pozycje"]:
        if pozycja["typ"] == "bufor" and pozycja["osiagalne"] and pozycja["obecnie"]:
            bufory.append({**pozycja, "bufor_wzgledny": abs(pozycja["zmiana"]) / abs(pozycja["obecnie"])})
    bufory.sort(key=lambda x: x["bufor_wzgledny"])
    return {"najwiekszy_wplyw": top, "najsilniejszy_segment": segmenty[0] if segmenty else None, "najsłabszy_segment": segmenty[-1] if segmenty else None, "ugody": ugody, "pojemnosc": pojemnosc, "najmniejsze_bufory": bufory[:3]}
