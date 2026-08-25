"""Deterministyczny model rentowności portfela spraw."""

from math import floor


LICZBA_SPRAW = 600
PROG_WPS = 10_000
NISKI_WPS = 2_500
WYSOKI_WPS = 25_000
KOSZT_STALY_NA_GODZINE = 36.00
WYNAGRODZENIE_PRACOWNIKA_NA_GODZINE = 59.88
KOSZT_GODZINY = KOSZT_STALY_NA_GODZINE + WYNAGRODZENIE_PRACOWNIKA_NA_GODZINE

WSPOLNE_CZYNNOSCI = {
    "Analiza sprawy i kompletowanie załącznika": 30,
}
PROCESOWE_CZYNNOSCI = {
    "Wniosek o wideo": 10,
    "Duplika": 90,
    "Pytania do świadków": 60,
    "Rozprawa": 60,
    "Notatka z rozprawy": 10,
    "Wyrok": 20,
}
UGODOWE_CZYNNOSCI = {
    "Oferta ugody": 15,
    "Projekt ugody": 20,
    "Podpisanie ugody": 20,
}
ANALIZA_MOZLIWOSCI_UGODY = 30
CODZIENNE_CZYNNOSCI = {
    "Obsługa skrzynki ugody EH": 30,
    "Komunikacja z EH i zlecanie opłat w SOSS": 30,
    "Umieszczanie dokumentów w SOSS": 30,
}

# Zachowana nazwa eksportu dla zgodności z dotychczasowymi integracjami. Słownik
# obejmuje wyłącznie czynności dotyczące spraw, bez czynności dziennych.
PODSTAWOWE_CZYNNOSCI = {
    **WSPOLNE_CZYNNOSCI,
    **PROCESOWE_CZYNNOSCI,
    **UGODOWE_CZYNNOSCI,
    "Analiza możliwości ugody": ANALIZA_MOZLIWOSCI_UGODY,
}

DODATKOWE_MINUTY = {"P1": 90, "P2": 150, "P3": 240}
P1_PERCENT = 25.0
P2_PERCENT = 58.0
P3_PERCENT = 17.0
HIGH_WPS_PERCENT = 80.0
LOW_WPS_PERCENT = 100.0 - HIGH_WPS_PERCENT
FIN_PERCENT = 50.0

KATEGORYCZNA_ODMOWA_PERCENT = 15.0
AUTOMATYCZNE_RAMY_PERCENT = 30.0
SZANSA_NA_UGODE_PERCENT = 50.0
ZAWARTE_UGODY_PERCENT = 50.0
UDZIAL_II_INSTANCJI_PERCENT = 20.0
OBSLUGA_II_INSTANCJI_MINUTY = 180
LICZBA_PRACOWNIKOW = 2
LICZBA_DNI_PRACY_W_ROKU = 251
MINUTY_DNIA_PRACY = 480

KATEGORIE_SPRAW = {
    "P1": "Koszty naprawy, uprzednie uzgodnienie kosztów",
    "P2": "Koszty najmu pojazdu zastępczego, zadośćuczynienie, nieruchomości",
    "P3": "Pozostałe sprawy",
}


def domyslne_parametry() -> dict:
    """Zwraca kopię wszystkich edytowalnych parametrów modelu."""
    return {
        "liczba_spraw": LICZBA_SPRAW,
        "prog_wps": PROG_WPS,
        "niski_wps": NISKI_WPS,
        "wysoki_wps": WYSOKI_WPS,
        "koszt_staly_na_godzine": KOSZT_STALY_NA_GODZINE,
        "wynagrodzenie_pracownika_na_godzine": WYNAGRODZENIE_PRACOWNIKA_NA_GODZINE,
        "wspolne_czynnosci": WSPOLNE_CZYNNOSCI.copy(),
        "procesowe_czynnosci": PROCESOWE_CZYNNOSCI.copy(),
        "ugodowe_czynnosci": UGODOWE_CZYNNOSCI.copy(),
        "analiza_mozliwosci_ugody": ANALIZA_MOZLIWOSCI_UGODY,
        "codzienne_czynnosci": CODZIENNE_CZYNNOSCI.copy(),
        "dodatkowe_minuty": DODATKOWE_MINUTY.copy(),
        "udzialy_rodzajow": {"P1": P1_PERCENT, "P2": P2_PERCENT, "P3": P3_PERCENT},
        "wysoki_wps_procent": HIGH_WPS_PERCENT,
        "fin_percent": FIN_PERCENT,
        "kategoryczna_odmowa_percent": KATEGORYCZNA_ODMOWA_PERCENT,
        "automatyczne_ramy_percent": AUTOMATYCZNE_RAMY_PERCENT,
        "szansa_na_ugode_percent": SZANSA_NA_UGODE_PERCENT,
        "zawarte_ugody_percent": ZAWARTE_UGODY_PERCENT,
        "udzial_ii_instancji_percent": UDZIAL_II_INSTANCJI_PERCENT,
        "obsluga_ii_instancji_minuty": OBSLUGA_II_INSTANCJI_MINUTY,
        "liczba_pracownikow": LICZBA_PRACOWNIKOW,
        "liczba_dni_pracy_w_roku": LICZBA_DNI_PRACY_W_ROKU,
    }


def oblicz_udzialy_ugod(
    kategoryczna_odmowa_percent: float,
    automatyczne_ramy_percent: float,
    szansa_na_ugode_percent: float,
    zawarte_ugody_percent: float = ZAWARTE_UGODY_PERCENT,
) -> dict[str, float]:
    """Oblicza efektywne udziały pięciu ścieżek ugodowych w portfelu."""
    wartosci = (
        kategoryczna_odmowa_percent,
        automatyczne_ramy_percent,
        szansa_na_ugode_percent,
        zawarte_ugody_percent,
    )
    if any(wartosc < 0 or wartosc > 100 for wartosc in wartosci):
        raise ValueError("Udziały ugodowe muszą mieścić się w zakresie od 0% do 100%.")
    if kategoryczna_odmowa_percent + automatyczne_ramy_percent > 100 + 1e-9:
        raise ValueError("Suma kategorycznej odmowy i automatycznych ram nie może przekraczać 100%.")

    pozostale = 100.0 - kategoryczna_odmowa_percent - automatyczne_ramy_percent
    szansa_poza_ramami = pozostale * szansa_na_ugode_percent / 100
    brak_szans = pozostale * (100.0 - szansa_na_ugode_percent) / 100
    zawarte_poza_ramami = szansa_poza_ramami * zawarte_ugody_percent / 100
    brak_ugody_poza_ramami = szansa_poza_ramami * (100.0 - zawarte_ugody_percent) / 100
    zakonczone_ugoda = automatyczne_ramy_percent + zawarte_poza_ramami
    bez_ugody = 100.0 - zakonczone_ugoda
    return {
        "kategoryczna_odmowa": kategoryczna_odmowa_percent,
        "automatyczne_ramy": automatyczne_ramy_percent,
        "pozostale_sprawy": pozostale,
        "szansa_poza_ramami": szansa_poza_ramami,
        "zawarte_poza_ramami": zawarte_poza_ramami,
        "brak_ugody_poza_ramami": brak_ugody_poza_ramami,
        "brak_szans": brak_szans,
        "zakonczone_ugoda": zakonczone_ugoda,
        "bez_ugody": bez_ugody,
    }


def oblicz_czasy_sciezek_ugod(
    wspolne_czynnosci: dict[str, float],
    procesowe_czynnosci: dict[str, float],
    ugodowe_czynnosci: dict[str, float],
    analiza_mozliwosci_ugody: float,
) -> dict[str, float]:
    """Oblicza bezpośredni czas jednej sprawy w każdej ścieżce ugodowej."""
    wspolne = sum(wspolne_czynnosci.values())
    procesowe = sum(procesowe_czynnosci.values())
    ugodowe = sum(ugodowe_czynnosci.values())
    przygotowanie_ugody = (
        ugodowe_czynnosci.get("Oferta ugody", 0)
        + ugodowe_czynnosci.get("Projekt ugody", 0)
    )
    return {
        "kategoryczna_odmowa": wspolne + procesowe,
        "automatyczne_ramy": wspolne + ugodowe,
        "brak_szans": wspolne + procesowe + analiza_mozliwosci_ugody,
        "zawarte_poza_ramami": wspolne + analiza_mozliwosci_ugody + ugodowe,
        "brak_ugody_poza_ramami": (
            wspolne + analiza_mozliwosci_ugody + przygotowanie_ugody + procesowe
        ),
    }


def oblicz_czasy_sciezek_z_ii_instancja(
    czasy_podstawowe: dict[str, float],
    udzial_ii_instancji_percent: float,
    obsluga_ii_instancji_minuty: float,
) -> tuple[dict[str, float], dict[str, float]]:
    """Dodaje oczekiwany czas II instancji wyłącznie do ścieżek bez ugody."""
    if not 0 <= udzial_ii_instancji_percent <= 100:
        raise ValueError("Udział spraw w II instancji musi mieścić się w zakresie od 0% do 100%.")
    if obsluga_ii_instancji_minuty < 0:
        raise ValueError("Czas obsługi sprawy w II instancji nie może być ujemny.")
    sciezki_bez_ugody = {
        "kategoryczna_odmowa",
        "brak_szans",
        "brak_ugody_poza_ramami",
    }
    oczekiwany_czas = udzial_ii_instancji_percent / 100 * obsluga_ii_instancji_minuty
    czasy_ii_instancji = {
        nazwa: oczekiwany_czas if nazwa in sciezki_bez_ugody else 0.0
        for nazwa in czasy_podstawowe
    }
    czasy_laczne = {
        nazwa: czas + czasy_ii_instancji[nazwa]
        for nazwa, czas in czasy_podstawowe.items()
    }
    return czasy_laczne, czasy_ii_instancji


def oblicz_wskazniki_ii_instancji(
    liczba_spraw: int,
    udzialy_ugod: dict[str, float],
    udzial_ii_instancji_percent: float,
    obsluga_ii_instancji_minuty: float,
) -> dict[str, float]:
    """Oblicza oczekiwany udział, liczbę i czas II instancji w całym portfelu."""
    if not 0 <= udzial_ii_instancji_percent <= 100:
        raise ValueError("Udział spraw w II instancji musi mieścić się w zakresie od 0% do 100%.")
    if obsluga_ii_instancji_minuty < 0:
        raise ValueError("Czas obsługi sprawy w II instancji nie może być ujemny.")
    udzial_w_portfelu = udzialy_ugod["bez_ugody"] * udzial_ii_instancji_percent / 100
    oczekiwana_liczba = liczba_spraw * udzial_w_portfelu / 100
    minuty_na_sprawe = udzial_w_portfelu / 100 * obsluga_ii_instancji_minuty
    minuty_lacznie = liczba_spraw * minuty_na_sprawe
    return {
        "udzial_ii_instancji_percent": udzial_ii_instancji_percent,
        "udzial_ii_instancji_w_portfelu": udzial_w_portfelu,
        "oczekiwana_liczba_spraw_ii_instancji": oczekiwana_liczba,
        "ii_instancja_minuty_na_sprawe_portfela": minuty_na_sprawe,
        "ii_instancja_minuty_lacznie": minuty_lacznie,
        "ii_instancja_godziny_lacznie": minuty_lacznie / 60,
    }


def oblicz_sredni_czas_sciezki_ugody(
    udzialy_ugod: dict[str, float], czasy_sciezek: dict[str, float]
) -> float:
    """Zwraca ważony oczekiwany czas ścieżki ugodowej dla jednej sprawy."""
    nazwy_sciezek = (
        "kategoryczna_odmowa",
        "automatyczne_ramy",
        "brak_szans",
        "zawarte_poza_ramami",
        "brak_ugody_poza_ramami",
    )
    return sum(
        udzialy_ugod[nazwa] / 100 * czasy_sciezek[nazwa]
        for nazwa in nazwy_sciezek
    )


def oblicz_czas_czynnosci_dziennych(
    liczba_pracownikow: int,
    liczba_dni_pracy_w_roku: int,
    codzienne_czynnosci: dict[str, float],
) -> float:
    """Oblicza roczny czas czynności dziennych całego zespołu w minutach."""
    if liczba_pracownikow < 0 or liczba_dni_pracy_w_roku < 0:
        raise ValueError("Liczba pracowników i dni pracy nie może być ujemna.")
    return liczba_pracownikow * liczba_dni_pracy_w_roku * sum(codzienne_czynnosci.values())


def oblicz_pojemnosc_zespolu(
    liczba_pracownikow: int,
    liczba_dni_pracy_w_roku: int,
    codzienne_czynnosci: dict[str, float],
    bezposrednie_minuty_spraw: float,
) -> dict[str, float | bool]:
    """Porównuje bezpośrednią pracę nad sprawami z roczną pojemnością zespołu."""
    dzienne_na_pracownika = sum(codzienne_czynnosci.values())
    pojemnosc_brutto = liczba_pracownikow * liczba_dni_pracy_w_roku * MINUTY_DNIA_PRACY
    czynnosci_dzienne = oblicz_czas_czynnosci_dziennych(
        liczba_pracownikow, liczba_dni_pracy_w_roku, codzienne_czynnosci
    )
    pojemnosc_spraw = pojemnosc_brutto - czynnosci_dzienne
    return {
        "pojemnosc_brutto_minuty": pojemnosc_brutto,
        "czynnosci_dzienne_minuty": czynnosci_dzienne,
        "pojemnosc_spraw_minuty": pojemnosc_spraw,
        "bezposrednie_minuty_spraw": bezposrednie_minuty_spraw,
        "przekroczona": bezposrednie_minuty_spraw > pojemnosc_spraw + 1e-9,
        "brak_czasu_na_sprawy": dzienne_na_pracownika >= MINUTY_DNIA_PRACY,
    }


def alokuj_liczby_z_procentow(liczba_spraw: int, udzialy: dict[str, float]) -> dict[str, int]:
    """Alokuje całkowitą liczbę spraw metodą największych reszt."""
    if liczba_spraw < 0:
        raise ValueError("Liczba spraw nie może być ujemna.")
    if abs(sum(udzialy.values()) - 100) > 1e-9:
        raise ValueError("Udziały rodzajów spraw muszą sumować się do 100%.")

    wartosci_dokladne = {nazwa: liczba_spraw * udzial / 100 for nazwa, udzial in udzialy.items()}
    alokacja = {nazwa: floor(wartosc) for nazwa, wartosc in wartosci_dokladne.items()}
    pozostale = liczba_spraw - sum(alokacja.values())
    kolejnosc = sorted(udzialy, key=lambda nazwa: -(wartosci_dokladne[nazwa] - alokacja[nazwa]))
    for nazwa in kolejnosc[:pozostale]:
        alokacja[nazwa] += 1
    return alokacja


def zaokraglij_polowki_w_gore(wartosc: float) -> int:
    """Zaokrągla dodatnią wartość według zwyczajowej zasady .5 w górę."""
    return floor(wartosc + 0.5)


def oblicz_podzial_spraw(
    liczba_spraw: int, udzialy_rodzajow: dict[str, float], wysoki_wps_procent: float
) -> dict[str, dict[str, int]]:
    """Dzieli portfel na P1/P2/P3, a następnie na niski i wysoki WPS."""
    liczby_rodzajow = alokuj_liczby_z_procentow(liczba_spraw, udzialy_rodzajow)
    podzial = {}
    for rodzaj, liczba in liczby_rodzajow.items():
        wysoki = zaokraglij_polowki_w_gore(liczba * wysoki_wps_procent / 100)
        podzial[rodzaj] = {"wysoki_wps": wysoki, "niski_wps": liczba - wysoki}
    return podzial


def oblicz_wynagrodzenie(wps: float, prog_wps: float, fin_percent: float) -> float:
    """Oblicza wynagrodzenie kancelarii dla jednej sprawy."""
    fin = wps * (fin_percent / 100)
    if wps < prog_wps:
        return 250 + min(0.20 * (wps - fin), 2000)
    return 500 + min(0.08 * (wps - fin), 5000)


def podsumuj_grupy(grupy: list[dict]) -> dict:
    """Agreguje dowolny zestaw grup spraw."""
    liczba_spraw = sum(grupa["liczba"] for grupa in grupy)
    przychod = sum(grupa["laczny_przychod"] for grupa in grupy)
    koszt = sum(grupa["laczny_koszt"] for grupa in grupy)
    wynik = przychod - koszt
    return {
        "liczba_spraw": liczba_spraw,
        "przychod": przychod,
        "koszt": koszt,
        "wynik": wynik,
        "marza": wynik / przychod * 100 if przychod else 0.0,
        "sredni_przychod": przychod / liczba_spraw if liczba_spraw else 0.0,
        "sredni_koszt": koszt / liczba_spraw if liczba_spraw else 0.0,
        "sredni_wynik": wynik / liczba_spraw if liczba_spraw else 0.0,
    }


def oblicz_grupe(
    rodzaj: str,
    grupa_wps: str,
    liczba: int,
    wps: float,
    parametry: dict,
    srednie_minuty_sciezki: float,
    narzut_dzienny_na_sprawe: float,
) -> dict:
    """Oblicza wynik jednej grupy P/WPS z księgową alokacją narzutu dziennego."""
    koszt_godziny = (
        parametry["koszt_staly_na_godzine"]
        + parametry["wynagrodzenie_pracownika_na_godzine"]
    )
    wynagrodzenie = oblicz_wynagrodzenie(wps, parametry["prog_wps"], parametry["fin_percent"])
    bezposrednie_minuty = srednie_minuty_sciezki + parametry["dodatkowe_minuty"][rodzaj]
    koszt_bezposredni = koszt_godziny * bezposrednie_minuty / 60
    koszt = koszt_bezposredni + narzut_dzienny_na_sprawe
    wynik_jednostkowy = wynagrodzenie - koszt
    return {
        "rodzaj": rodzaj,
        "grupa_wps": grupa_wps,
        "wps": wps,
        "liczba": liczba,
        "wynagrodzenie": wynagrodzenie,
        "koszt_bezposredni": koszt_bezposredni,
        "narzut_dzienny_na_sprawe": narzut_dzienny_na_sprawe,
        "koszt": koszt,
        "wynik_jednostkowy": wynik_jednostkowy,
        "laczne_minuty": bezposrednie_minuty,
        "laczny_przychod": liczba * wynagrodzenie,
        "laczny_koszt": liczba * koszt,
        "laczny_wynik": liczba * wynik_jednostkowy,
    }


def oblicz_model(parametry: dict | None = None) -> dict:
    """Zwraca pełne wyniki nowego modelu czasu, kosztu i pojemności."""
    if parametry is None:
        parametry = domyslne_parametry()

    udzialy_ugod = oblicz_udzialy_ugod(
        parametry["kategoryczna_odmowa_percent"],
        parametry["automatyczne_ramy_percent"],
        parametry["szansa_na_ugode_percent"],
        parametry.get("zawarte_ugody_percent", ZAWARTE_UGODY_PERCENT),
    )
    czasy_sciezek = oblicz_czasy_sciezek_ugod(
        parametry["wspolne_czynnosci"],
        parametry["procesowe_czynnosci"],
        parametry["ugodowe_czynnosci"],
        parametry["analiza_mozliwosci_ugody"],
    )
    czasy_sciezek_z_ii_instancja, czasy_ii_instancji_sciezek = oblicz_czasy_sciezek_z_ii_instancja(
        czasy_sciezek,
        parametry["udzial_ii_instancji_percent"],
        parametry["obsluga_ii_instancji_minuty"],
    )
    srednie_minuty_podstawowej_sciezki = oblicz_sredni_czas_sciezki_ugody(
        udzialy_ugod, czasy_sciezek
    )
    srednie_minuty_sciezki = oblicz_sredni_czas_sciezki_ugody(
        udzialy_ugod, czasy_sciezek_z_ii_instancja
    )
    koszt_godziny = (
        parametry["koszt_staly_na_godzine"]
        + parametry["wynagrodzenie_pracownika_na_godzine"]
    )
    czynnosci_dzienne_minuty = oblicz_czas_czynnosci_dziennych(
        parametry["liczba_pracownikow"],
        parametry["liczba_dni_pracy_w_roku"],
        parametry["codzienne_czynnosci"],
    )
    czynnosci_dzienne_koszt = czynnosci_dzienne_minuty / 60 * koszt_godziny
    liczba_spraw = parametry["liczba_spraw"]
    wskazniki_ii_instancji = oblicz_wskazniki_ii_instancji(
        liczba_spraw,
        udzialy_ugod,
        parametry["udzial_ii_instancji_percent"],
        parametry["obsluga_ii_instancji_minuty"],
    )
    narzut_dzienny_na_sprawe = czynnosci_dzienne_koszt / liczba_spraw if liczba_spraw else 0.0

    podzial_spraw = oblicz_podzial_spraw(
        liczba_spraw, parametry["udzialy_rodzajow"], parametry["wysoki_wps_procent"]
    )
    grupy = []
    for rodzaj, podzial in podzial_spraw.items():
        for grupa_wps, liczba in podzial.items():
            wps = parametry["wysoki_wps"] if grupa_wps == "wysoki_wps" else parametry["niski_wps"]
            grupy.append(
                oblicz_grupe(
                    rodzaj,
                    grupa_wps,
                    liczba,
                    wps,
                    parametry,
                    srednie_minuty_sciezki,
                    narzut_dzienny_na_sprawe,
                )
            )

    wedlug_wps = {
        "niski_wps": podsumuj_grupy([g for g in grupy if g["grupa_wps"] == "niski_wps"]),
        "wysoki_wps": podsumuj_grupy([g for g in grupy if g["grupa_wps"] == "wysoki_wps"]),
    }
    rodzaje = {
        rodzaj: podsumuj_grupy([g for g in grupy if g["rodzaj"] == rodzaj])
        for rodzaj in podzial_spraw
    }
    bezposrednie_minuty_spraw = sum(
        grupa["liczba"] * grupa["laczne_minuty"] for grupa in grupy
    )
    laczne_minuty = bezposrednie_minuty_spraw + czynnosci_dzienne_minuty
    ogolem = podsumuj_grupy(grupy)
    if not liczba_spraw and czynnosci_dzienne_koszt:
        ogolem["koszt"] = czynnosci_dzienne_koszt
        ogolem["wynik"] = -czynnosci_dzienne_koszt
        ogolem["marza"] = 0.0

    return {
        "ogolem": ogolem,
        "wps_niski": wedlug_wps["niski_wps"],
        "wps_wysoki": wedlug_wps["wysoki_wps"],
        "rodzaje": rodzaje,
        "grupy": grupy,
        "podzial_spraw": podzial_spraw,
        "udzialy_ugod": udzialy_ugod,
        "czasy_sciezek_ugod": czasy_sciezek,
        "czasy_ii_instancji_sciezek": czasy_ii_instancji_sciezek,
        "czasy_sciezek_z_ii_instancja": czasy_sciezek_z_ii_instancja,
        "srednie_minuty_podstawowej_sciezki_ugody": srednie_minuty_podstawowej_sciezki,
        "srednie_minuty_sciezki_ugody": srednie_minuty_sciezki,
        **wskazniki_ii_instancji,
        "obsluga_ii_instancji_minuty": parametry["obsluga_ii_instancji_minuty"],
        "koszt_godziny": koszt_godziny,
        "bezposrednie_minuty_spraw": bezposrednie_minuty_spraw,
        "czynnosci_dzienne_minuty": czynnosci_dzienne_minuty,
        "czynnosci_dzienne_koszt": czynnosci_dzienne_koszt,
        "narzut_dzienny_na_sprawe": narzut_dzienny_na_sprawe,
        "laczne_minuty": laczne_minuty,
        "laczne_godziny": laczne_minuty / 60,
        "pojemnosc": oblicz_pojemnosc_zespolu(
            parametry["liczba_pracownikow"],
            parametry["liczba_dni_pracy_w_roku"],
            parametry["codzienne_czynnosci"],
            bezposrednie_minuty_spraw,
        ),
        "koszty_jednostkowe": {
            rodzaj: koszt_godziny
            * (srednie_minuty_sciezki + parametry["dodatkowe_minuty"][rodzaj])
            / 60
            + narzut_dzienny_na_sprawe
            for rodzaj in parametry["dodatkowe_minuty"]
        },
    }


def _parametry_z_zmiana(parametry: dict, **zmiany) -> dict:
    """Tworzy bezpieczną kopię parametrów z podmienionymi wartościami."""
    kopia = {
        **parametry,
        "wspolne_czynnosci": parametry["wspolne_czynnosci"].copy(),
        "procesowe_czynnosci": parametry["procesowe_czynnosci"].copy(),
        "ugodowe_czynnosci": parametry["ugodowe_czynnosci"].copy(),
        "codzienne_czynnosci": parametry["codzienne_czynnosci"].copy(),
        "dodatkowe_minuty": parametry["dodatkowe_minuty"].copy(),
        "udzialy_rodzajow": parametry["udzialy_rodzajow"].copy(),
    }
    kopia.update(zmiany)
    return kopia


def oblicz_prog_czasu(parametry: dict) -> dict:
    """Wyznacza wymagane skrócenie wyłącznie bezpośredniego czasu spraw."""
    wyniki = oblicz_model(parametry)
    liczba_spraw = wyniki["ogolem"]["liczba_spraw"]
    bezposrednie_minuty = wyniki["bezposrednie_minuty_spraw"]
    dzienne_minuty = wyniki["czynnosci_dzienne_minuty"]
    koszt_godziny = wyniki["koszt_godziny"]
    strata = max(0.0, -wyniki["ogolem"]["wynik"])
    obecny_sredni_czas = bezposrednie_minuty / 60 / liczba_spraw if liczba_spraw else 0.0
    wynik_podstawowy = {
        "obecny_sredni_czas": obecny_sredni_czas,
        "czynnosci_dzienne_minuty": dzienne_minuty,
    }
    if strata == 0:
        return {
            **wynik_podstawowy,
            "mozliwe": True,
            "juz_rentowny": True,
            "redukcja_minut_na_sprawe": 0.0,
            "docelowy_sredni_czas": obecny_sredni_czas,
            "docelowy_udzial_czasu": 1.0,
        }
    if not liczba_spraw or koszt_godziny <= 0:
        return {**wynik_podstawowy, "mozliwe": False, "juz_rentowny": False}

    koszt_czynnosci_dziennych = dzienne_minuty / 60 * koszt_godziny
    if koszt_czynnosci_dziennych > wyniki["ogolem"]["przychod"] + 1e-9:
        return {**wynik_podstawowy, "mozliwe": False, "juz_rentowny": False}

    redukcja_minut = strata / koszt_godziny * 60
    if redukcja_minut > bezposrednie_minuty + 1e-9:
        return {**wynik_podstawowy, "mozliwe": False, "juz_rentowny": False}
    docelowe_minuty = max(0.0, bezposrednie_minuty - redukcja_minut)
    redukcja_na_sprawe = redukcja_minut / liczba_spraw
    return {
        **wynik_podstawowy,
        "mozliwe": True,
        "juz_rentowny": False,
        "redukcja_minut_na_sprawe": redukcja_na_sprawe,
        "docelowy_sredni_czas": docelowe_minuty / 60 / liczba_spraw,
        "docelowy_udzial_czasu": docelowe_minuty / bezposrednie_minuty if bezposrednie_minuty else 0.0,
    }


def _oblicz_prog_kosztu(parametry: dict, zmieniany_koszt: str, drugi_koszt: str) -> dict:
    wyniki = oblicz_model(parametry)
    godziny = wyniki["laczne_godziny"]
    obecny = parametry[zmieniany_koszt]
    if godziny <= 0:
        return {"mozliwe": False, "obecnie": obecny}
    prog = wyniki["ogolem"]["przychod"] / godziny - parametry[drugi_koszt]
    if prog < 0:
        return {"mozliwe": False, "obecnie": obecny}
    return {
        "mozliwe": True,
        "obecnie": obecny,
        "prog": prog,
        "wymagana_redukcja": max(0.0, obecny - prog),
    }


def oblicz_prog_kosztu_stalego(parametry: dict) -> dict:
    return _oblicz_prog_kosztu(
        parametry, "koszt_staly_na_godzine", "wynagrodzenie_pracownika_na_godzine"
    )


def oblicz_prog_wynagrodzenia_pracownika(parametry: dict) -> dict:
    return _oblicz_prog_kosztu(
        parametry, "wynagrodzenie_pracownika_na_godzine", "koszt_staly_na_godzine"
    )


def oblicz_prog_fin(parametry: dict, tolerancja: float = 0.0001) -> dict:
    """Wyznacza maksymalny FIN (% WPS) zapewniający wynik nie mniejszy od zera."""

    def wynik_dla(fin_percent: float) -> float:
        return oblicz_model(_parametry_z_zmiana(parametry, fin_percent=fin_percent))["ogolem"]["wynik"]

    wynik_0 = wynik_dla(0.0)
    wynik_100 = wynik_dla(100.0)
    if wynik_0 < 0:
        return {"mozliwe": False, "rentowny_w_calym_zakresie": False}
    if wynik_100 >= 0:
        return {"mozliwe": True, "rentowny_w_calym_zakresie": True, "prog": 100.0}

    dol, gora = 0.0, 100.0
    while gora - dol > tolerancja:
        srodek = (dol + gora) / 2
        if wynik_dla(srodek) >= 0:
            dol = srodek
        else:
            gora = srodek
    return {"mozliwe": True, "rentowny_w_calym_zakresie": False, "prog": dol}
