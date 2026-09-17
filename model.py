"""Deterministyczny model rentowności portfela spraw."""

from math import floor, isfinite


LICZBA_SPRAW = 600
PROG_WPS = 10_000
NISKI_WPS = 3_110
WYSOKI_WPS = 37_631
KOSZT_STALY_NA_GODZINE = 36.00
WYNAGRODZENIE_PRACOWNIKA_NA_GODZINE = 59.88

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
HIGH_WPS_PERCENT = 79.0
LOW_WPS_PERCENT = 100.0 - HIGH_WPS_PERCENT
SREDNIA_KWOTA_UGODY_PERCENT = 70.0
SREDNIA_KWOTA_WYROKU_PERCENT = 95.0
PODATEK_DOCHODOWY_PERCENT = 0.0

KATEGORYCZNA_ODMOWA_PERCENT = 15.0
AUTOMATYCZNE_RAMY_PERCENT = 30.0
SZANSA_NA_UGODE_PERCENT = 50.0
ZAWARTE_UGODY_PERCENT = 50.0
UDZIAL_II_INSTANCJI_PERCENT = 20.0
OBSLUGA_II_INSTANCJI_MINUTY = 210
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
        "srednia_kwota_ugody_percent": SREDNIA_KWOTA_UGODY_PERCENT,
        "srednia_kwota_wyroku_percent": SREDNIA_KWOTA_WYROKU_PERCENT,
        "podatek_dochodowy_percent": PODATEK_DOCHODOWY_PERCENT,
        "kategoryczna_odmowa_percent": KATEGORYCZNA_ODMOWA_PERCENT,
        "automatyczne_ramy_percent": AUTOMATYCZNE_RAMY_PERCENT,
        "szansa_na_ugode_percent": SZANSA_NA_UGODE_PERCENT,
        "zawarte_ugody_percent": ZAWARTE_UGODY_PERCENT,
        "udzial_ii_instancji_percent": UDZIAL_II_INSTANCJI_PERCENT,
        "obsluga_ii_instancji_minuty": OBSLUGA_II_INSTANCJI_MINUTY,
        "liczba_pracownikow": LICZBA_PRACOWNIKOW,
        "liczba_dni_pracy_w_roku": LICZBA_DNI_PRACY_W_ROKU,
    }


def waliduj_parametry(parametry: dict) -> None:
    """Waliduje wspólne założenia przed uruchomieniem któregokolwiek modelu."""
    calkowite = ("liczba_spraw", "liczba_pracownikow", "liczba_dni_pracy_w_roku")
    for nazwa in calkowite:
        wartosc = parametry[nazwa]
        if not isinstance(wartosc, int) or isinstance(wartosc, bool) or wartosc < 0:
            raise ValueError(f"Parametr {nazwa} musi być nieujemną liczbą całkowitą.")

    nieujemne = (
        "prog_wps",
        "niski_wps",
        "wysoki_wps",
        "koszt_staly_na_godzine",
        "wynagrodzenie_pracownika_na_godzine",
        "analiza_mozliwosci_ugody",
        "obsluga_ii_instancji_minuty",
    )
    procenty = (
        "wysoki_wps_procent",
        "srednia_kwota_ugody_percent",
        "srednia_kwota_wyroku_percent",
        "podatek_dochodowy_percent",
        "kategoryczna_odmowa_percent",
        "automatyczne_ramy_percent",
        "szansa_na_ugode_percent",
        "zawarte_ugody_percent",
        "udzial_ii_instancji_percent",
    )
    for nazwa in nieujemne + procenty:
        wartosc = parametry[nazwa]
        if not isinstance(wartosc, (int, float)) or isinstance(wartosc, bool) or not isfinite(wartosc):
            raise ValueError(f"Parametr {nazwa} musi być skończoną liczbą.")
    for nazwa in nieujemne:
        if parametry[nazwa] < 0:
            raise ValueError(f"Parametr {nazwa} nie może być ujemny.")
    if parametry["prog_wps"] <= 0:
        raise ValueError("Próg WPS musi być dodatni.")
    for nazwa in procenty:
        if not 0 <= parametry[nazwa] <= 100:
            raise ValueError(f"Parametr {nazwa} musi mieścić się w zakresie 0–100%.")

    slowniki_minut = (
        "wspolne_czynnosci",
        "procesowe_czynnosci",
        "ugodowe_czynnosci",
        "codzienne_czynnosci",
        "dodatkowe_minuty",
    )
    for klucz in slowniki_minut:
        for nazwa, wartosc in parametry[klucz].items():
            if (
                not isinstance(wartosc, (int, float))
                or isinstance(wartosc, bool)
                or not isfinite(wartosc)
                or wartosc < 0
            ):
                raise ValueError(f"Czas „{nazwa}” musi być nieujemną skończoną liczbą.")
    oczekiwane_rodzaje = {"P1", "P2", "P3"}
    if set(parametry["udzialy_rodzajow"]) != oczekiwane_rodzaje:
        raise ValueError("Udziały rodzajów spraw muszą zawierać dokładnie P1, P2 i P3.")
    if set(parametry["dodatkowe_minuty"]) != oczekiwane_rodzaje:
        raise ValueError("Dodatkowe minuty muszą zawierać dokładnie P1, P2 i P3.")
    if sum(parametry["codzienne_czynnosci"].values()) >= MINUTY_DNIA_PRACY:
        raise ValueError("Czynności dzienne muszą pozostawiać czas na obsługę spraw.")
    if any(
        not isinstance(wartosc, (int, float))
        or isinstance(wartosc, bool)
        or not isfinite(wartosc)
        or not 0 <= wartosc <= 100
        for wartosc in parametry["udzialy_rodzajow"].values()
    ):
        raise ValueError("Każdy udział rodzaju spraw musi mieścić się w zakresie 0–100%.")
    if abs(sum(parametry["udzialy_rodzajow"].values()) - 100) > 1e-9:
        raise ValueError("Udziały rodzajów spraw muszą sumować się do 100%.")
    if parametry["kategoryczna_odmowa_percent"] + parametry["automatyczne_ramy_percent"] > 100 + 1e-9:
        raise ValueError("Suma kategorycznej odmowy i automatycznych ram nie może przekraczać 100%.")
    if parametry["niski_wps"] >= parametry["prog_wps"]:
        raise ValueError("Średni WPS poniżej progu musi być mniejszy od progu WPS.")
    if parametry["wysoki_wps"] < parametry["prog_wps"]:
        raise ValueError("Średni WPS od progu musi być co najmniej równy progowi WPS.")


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
    if any(
        not isinstance(wartosc, (int, float))
        or isinstance(wartosc, bool)
        or not isfinite(wartosc)
        or wartosc < 0
        or wartosc > 100
        for wartosc in wartosci
    ):
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
    wynik = {
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
    sciezki = (
        "kategoryczna_odmowa",
        "automatyczne_ramy",
        "brak_szans",
        "zawarte_poza_ramami",
        "brak_ugody_poza_ramami",
    )
    if any(wynik[nazwa] < -1e-9 for nazwa in sciezki):
        raise RuntimeError("Wyliczono ujemny udział ścieżki ugodowej.")
    if abs(sum(wynik[nazwa] for nazwa in sciezki) - 100) > 1e-8:
        raise RuntimeError("Udziały ścieżek ugodowych nie sumują się do 100%.")
    if abs(wynik["zakonczone_ugoda"] + wynik["bez_ugody"] - 100) > 1e-8:
        raise RuntimeError("Udziały zakończeń ugodowych nie sumują się do 100%.")
    for nazwa in sciezki:
        if -1e-9 < wynik[nazwa] < 0:
            wynik[nazwa] = 0.0
    return wynik


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


def oblicz_czynnosci_dzienne_lifecycle(
    bezposrednie_minuty_spraw: float,
    codzienne_czynnosci: dict[str, float],
) -> dict[str, float]:
    """Wycenia pełny płatny czas zasobu dla cyklu życia kohorty.

    Ośmiogodzinny dzień pracownika ma 480 płatnych minut. Czynności dzienne
    mieszczą się w tym limicie, więc jedna osobodniówka dostarcza na sprawy
    wyłącznie różnicę między 480 minutami a narzutem dziennym.
    """
    if bezposrednie_minuty_spraw < 0:
        raise ValueError("Bezpośredni czas spraw nie może być ujemny.")
    minuty_na_osobodzien = sum(codzienne_czynnosci.values())
    if minuty_na_osobodzien < 0:
        raise ValueError("Czas czynności dziennych nie może być ujemny.")
    produktywne_minuty = MINUTY_DNIA_PRACY - minuty_na_osobodzien
    if bezposrednie_minuty_spraw > 0 and produktywne_minuty <= 0:
        raise ValueError(
            "Czynności dzienne zużywają cały dzień pracy; "
            "nie można obsłużyć dodatniej pracy nad sprawami."
        )
    ekwiwalent_osobodni = (
        bezposrednie_minuty_spraw / produktywne_minuty
        if produktywne_minuty > 0
        else 0.0
    )
    minuty_lifecycle = ekwiwalent_osobodni * minuty_na_osobodzien
    laczne_minuty_zasobu = bezposrednie_minuty_spraw + minuty_lifecycle
    return {
        "produktywne_minuty_na_osobodzien": max(produktywne_minuty, 0.0),
        "ekwiwalent_osobodni_kohorty": ekwiwalent_osobodni,
        "czynnosci_dzienne_lifecycle_minuty": minuty_lifecycle,
        "czynnosci_dzienne_lifecycle_godziny": minuty_lifecycle / 60,
        "laczne_minuty_zasobu_lifecycle": laczne_minuty_zasobu,
        "laczne_godziny_zasobu_lifecycle": laczne_minuty_zasobu / 60,
    }


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
    pojemnosc_spraw = max(pojemnosc_brutto - czynnosci_dzienne, 0.0)
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
    """Dzieli portfel tak, by globalna liczba wysokiego WPS była zachowana."""
    if not 0 <= wysoki_wps_procent <= 100:
        raise ValueError("Udział wysokiego WPS musi mieścić się w zakresie 0–100%.")
    liczby_rodzajow = alokuj_liczby_z_procentow(liczba_spraw, udzialy_rodzajow)
    cel_wysokiego_wps = zaokraglij_polowki_w_gore(
        liczba_spraw * wysoki_wps_procent / 100
    )
    dokladne = {
        rodzaj: liczba * wysoki_wps_procent / 100
        for rodzaj, liczba in liczby_rodzajow.items()
    }
    wysokie = {rodzaj: floor(wartosc) for rodzaj, wartosc in dokladne.items()}
    pozostale = cel_wysokiego_wps - sum(wysokie.values())
    kolejnosc = sorted(
        liczby_rodzajow,
        key=lambda rodzaj: (-(dokladne[rodzaj] - wysokie[rodzaj]), rodzaj),
    )
    for rodzaj in kolejnosc:
        if pozostale <= 0:
            break
        if wysokie[rodzaj] < liczby_rodzajow[rodzaj]:
            wysokie[rodzaj] += 1
            pozostale -= 1
    podzial = {
        rodzaj: {
            "wysoki_wps": wysokie[rodzaj],
            "niski_wps": liczba - wysokie[rodzaj],
        }
        for rodzaj, liczba in liczby_rodzajow.items()
    }
    return podzial


def oblicz_wynagrodzenie(
    wps: float, prog_wps: float, kwota_koncowa_percent: float
) -> float:
    """Oblicza wynagrodzenie dla jednego sposobu zakończenia sprawy."""
    if not 0 <= kwota_koncowa_percent <= 100:
        raise ValueError("Średnia kwota końcowa musi mieścić się w zakresie 0–100% WPS.")
    kwota_koncowa = wps * kwota_koncowa_percent / 100
    if wps < prog_wps:
        return 250 + min(0.20 * (wps - kwota_koncowa), 2000)
    return 500 + min(0.08 * (wps - kwota_koncowa), 5000)


def oblicz_podatek_dochodowy(
    przychod: float, koszt: float, podatek_dochodowy_percent: float
) -> dict[str, float]:
    """Nakłada uproszczony podatek wyłącznie na dodatni wynik przed podatkiem."""
    if not 0 <= podatek_dochodowy_percent <= 100:
        raise ValueError("Podatek dochodowy musi mieścić się w zakresie 0–100%.")
    wynik_przed_podatkiem = przychod - koszt
    podatek_dochodowy = (
        max(wynik_przed_podatkiem, 0.0) * podatek_dochodowy_percent / 100
    )
    wynik_po_podatku = wynik_przed_podatkiem - podatek_dochodowy
    return {
        "wynik_przed_podatkiem": wynik_przed_podatkiem,
        "podatek_dochodowy": podatek_dochodowy,
        "wynik_po_podatku": wynik_po_podatku,
        "marza_przed_podatkiem": (
            wynik_przed_podatkiem / przychod * 100 if przychod else 0.0
        ),
        "marza_po_podatku": wynik_po_podatku / przychod * 100 if przychod else 0.0,
    }


def podsumuj_grupy(grupy: list[dict], koszt_staly_portfela: float = 0.0) -> dict:
    """Agreguje dowolny zestaw grup spraw."""
    liczba_spraw = sum(grupa["liczba"] for grupa in grupy)
    przychod = sum(grupa["laczny_przychod"] for grupa in grupy)
    koszt_pracy = sum(grupa["laczny_koszt_pracy_pracownika"] for grupa in grupy)
    alokowany_koszt_staly = sum(grupa["laczny_alokowany_koszt_staly"] for grupa in grupy)
    koszt_staly = alokowany_koszt_staly + koszt_staly_portfela
    koszt = koszt_pracy + koszt_staly
    wynik_przed_podatkiem = przychod - koszt
    przychod_ugody = sum(grupa["laczny_przychod_ugody"] for grupa in grupy)
    przychod_wyroki = sum(grupa["laczny_przychod_wyroki"] for grupa in grupy)
    return {
        "liczba_spraw": liczba_spraw,
        "przychod": przychod,
        "koszt_pracy_pracownika": koszt_pracy,
        "alokowany_koszt_staly": koszt_staly,
        "koszt_calkowity": koszt,
        "koszt": koszt,
        "wynik_przed_podatkiem": wynik_przed_podatkiem,
        "marza_przed_podatkiem": (
            wynik_przed_podatkiem / przychod * 100 if przychod else 0.0
        ),
        # Aliasy segmentowe pozostają jednoznacznie wartościami przed podatkiem.
        "wynik": wynik_przed_podatkiem,
        "marza": wynik_przed_podatkiem / przychod * 100 if przychod else 0.0,
        "przychod_ugody": przychod_ugody,
        "przychod_wyroki": przychod_wyroki,
        "sredni_przychod": przychod / liczba_spraw if liczba_spraw else 0.0,
        "sredni_koszt": koszt / liczba_spraw if liczba_spraw else 0.0,
        "sredni_wynik_przed_podatkiem": (
            wynik_przed_podatkiem / liczba_spraw if liczba_spraw else 0.0
        ),
        "sredni_wynik": wynik_przed_podatkiem / liczba_spraw if liczba_spraw else 0.0,
    }


def oblicz_grupe(
    rodzaj: str,
    grupa_wps: str,
    liczba: int,
    wps: float,
    parametry: dict,
    srednie_minuty_sciezki: float,
    mnoznik_zasobu_lifecycle: float,
    alokowany_koszt_staly_na_sprawe: float,
    udzial_ugod: float,
    udzial_wyrokow: float,
) -> dict:
    """Oblicza segment, rozdzielając koszt pracy i alokowany koszt stały."""
    wynagrodzenie_ugoda = oblicz_wynagrodzenie(
        wps, parametry["prog_wps"], parametry["srednia_kwota_ugody_percent"]
    )
    wynagrodzenie_wyrok = oblicz_wynagrodzenie(
        wps, parametry["prog_wps"], parametry["srednia_kwota_wyroku_percent"]
    )
    oczekiwany_przychod_ugody = udzial_ugod / 100 * wynagrodzenie_ugoda
    oczekiwany_przychod_wyroki = udzial_wyrokow / 100 * wynagrodzenie_wyrok
    wynagrodzenie = oczekiwany_przychod_ugody + oczekiwany_przychod_wyroki
    bezposrednie_minuty = srednie_minuty_sciezki + parametry["dodatkowe_minuty"][rodzaj]
    minuty_zasobu = bezposrednie_minuty * mnoznik_zasobu_lifecycle
    koszt_pracy = (
        minuty_zasobu / 60 * parametry["wynagrodzenie_pracownika_na_godzine"]
    )
    koszt_bezposredni = (
        bezposrednie_minuty
        / 60
        * parametry["wynagrodzenie_pracownika_na_godzine"]
    )
    narzut_dzienny_na_sprawe = koszt_pracy - koszt_bezposredni
    koszt_calkowity = koszt_pracy + alokowany_koszt_staly_na_sprawe
    wynik_jednostkowy = wynagrodzenie - koszt_calkowity
    return {
        "rodzaj": rodzaj,
        "grupa_wps": grupa_wps,
        "wps": wps,
        "liczba": liczba,
        "wynagrodzenie": wynagrodzenie,
        "wynagrodzenie_ugoda": wynagrodzenie_ugoda,
        "wynagrodzenie_wyrok": wynagrodzenie_wyrok,
        "oczekiwane_wynagrodzenie": wynagrodzenie,
        "udzial_ugod": udzial_ugod,
        "udzial_wyrokow": udzial_wyrokow,
        "oczekiwany_przychod_ugody": oczekiwany_przychod_ugody,
        "oczekiwany_przychod_wyroki": oczekiwany_przychod_wyroki,
        "koszt_bezposredni": koszt_bezposredni,
        "narzut_dzienny_na_sprawe": narzut_dzienny_na_sprawe,
        "minuty_zasobu_pracownika": minuty_zasobu,
        "godziny_zasobu_pracownika": minuty_zasobu / 60,
        "koszt_pracy_pracownika": koszt_pracy,
        "alokowany_koszt_staly": alokowany_koszt_staly_na_sprawe,
        "koszt_calkowity": koszt_calkowity,
        "koszt": koszt_calkowity,
        "wynik_jednostkowy_przed_podatkiem": wynik_jednostkowy,
        "wynik_jednostkowy": wynik_jednostkowy,
        "laczne_minuty": bezposrednie_minuty,
        "laczny_przychod": liczba * wynagrodzenie,
        "laczny_przychod_ugody": liczba * oczekiwany_przychod_ugody,
        "laczny_przychod_wyroki": liczba * oczekiwany_przychod_wyroki,
        "laczny_koszt_pracy_pracownika": liczba * koszt_pracy,
        "laczny_alokowany_koszt_staly": liczba * alokowany_koszt_staly_na_sprawe,
        "laczny_koszt_calkowity": liczba * koszt_calkowity,
        "laczny_koszt": liczba * koszt_calkowity,
        "laczny_wynik_przed_podatkiem": liczba * wynik_jednostkowy,
        "laczny_wynik": liczba * wynik_jednostkowy,
    }


def oblicz_model(parametry: dict | None = None) -> dict:
    """Zwraca pełne wyniki nowego modelu czasu, kosztu i pojemności."""
    if parametry is None:
        parametry = domyslne_parametry()
    waliduj_parametry(parametry)

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
    liczba_spraw = parametry["liczba_spraw"]
    wskazniki_ii_instancji = oblicz_wskazniki_ii_instancji(
        liczba_spraw,
        udzialy_ugod,
        parametry["udzial_ii_instancji_percent"],
        parametry["obsluga_ii_instancji_minuty"],
    )
    podzial_spraw = oblicz_podzial_spraw(
        liczba_spraw, parametry["udzialy_rodzajow"], parametry["wysoki_wps_procent"]
    )
    bezposrednie_minuty_spraw = sum(
        sum(podzial.values())
        * (srednie_minuty_sciezki + parametry["dodatkowe_minuty"][rodzaj])
        for rodzaj, podzial in podzial_spraw.items()
    )
    metryki_lifecycle = oblicz_czynnosci_dzienne_lifecycle(
        bezposrednie_minuty_spraw, parametry["codzienne_czynnosci"]
    )
    czynnosci_dzienne_lifecycle_minuty = metryki_lifecycle[
        "czynnosci_dzienne_lifecycle_minuty"
    ]
    wynagrodzenie_godzinowe = parametry["wynagrodzenie_pracownika_na_godzine"]
    koszt_staly_na_godzine = parametry["koszt_staly_na_godzine"]
    godziny_operacyjne_rocznie = parametry["liczba_dni_pracy_w_roku"] * 8
    koszt_staly_roczny = godziny_operacyjne_rocznie * koszt_staly_na_godzine
    koszt_pracy_lifecycle = (
        metryki_lifecycle["laczne_godziny_zasobu_lifecycle"]
        * wynagrodzenie_godzinowe
    )
    czynnosci_dzienne_lifecycle_koszt = (
        czynnosci_dzienne_lifecycle_minuty / 60 * wynagrodzenie_godzinowe
    )
    narzut_dzienny_na_sprawe = (
        czynnosci_dzienne_lifecycle_koszt / liczba_spraw if liczba_spraw else 0.0
    )
    alokowany_koszt_staly_na_sprawe = (
        koszt_staly_roczny / liczba_spraw if liczba_spraw else 0.0
    )
    produktywne_minuty = metryki_lifecycle["produktywne_minuty_na_osobodzien"]
    mnoznik_zasobu_lifecycle = MINUTY_DNIA_PRACY / produktywne_minuty
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
                    mnoznik_zasobu_lifecycle,
                    alokowany_koszt_staly_na_sprawe,
                    udzialy_ugod["zakonczone_ugoda"],
                    udzialy_ugod["bez_ugody"],
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
    laczne_minuty = bezposrednie_minuty_spraw + czynnosci_dzienne_lifecycle_minuty
    ogolem = podsumuj_grupy(
        grupy, koszt_staly_portfela=koszt_staly_roczny if not liczba_spraw else 0.0
    )
    rozliczenie_podatku = oblicz_podatek_dochodowy(
        ogolem["przychod"],
        ogolem["koszt_calkowity"],
        parametry["podatek_dochodowy_percent"],
    )
    ogolem.update(rozliczenie_podatku)
    # Aliasy zgodnościowe; nowe obliczenia używają wyłącznie jawnych pól podatkowych.
    ogolem["wynik"] = rozliczenie_podatku["wynik_po_podatku"]
    ogolem["marza"] = rozliczenie_podatku["marza_po_podatku"]
    ogolem["sredni_wynik_po_podatku"] = (
        ogolem["wynik_po_podatku"] / liczba_spraw if liczba_spraw else 0.0
    )
    ogolem["sredni_wynik"] = ogolem["sredni_wynik_po_podatku"]

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
        "koszt_staly_na_godzine": koszt_staly_na_godzine,
        "wynagrodzenie_pracownika_na_godzine": wynagrodzenie_godzinowe,
        "godziny_operacyjne_rocznie": godziny_operacyjne_rocznie,
        "godziny_operacji_rocznie": godziny_operacyjne_rocznie,
        "koszt_staly_roczny": koszt_staly_roczny,
        "koszt_pracy_lifecycle": koszt_pracy_lifecycle,
        "koszt_pracy_pracownika_lifecycle": koszt_pracy_lifecycle,
        "koszt_calkowity_lifecycle": koszt_pracy_lifecycle + koszt_staly_roczny,
        **rozliczenie_podatku,
        "podatek_dochodowy_percent": parametry["podatek_dochodowy_percent"],
        "bezposrednie_minuty_spraw": bezposrednie_minuty_spraw,
        **metryki_lifecycle,
        # Zachowane klucze oznaczają wyłącznie narzut lifecycle, nigdy roczny.
        "czynnosci_dzienne_minuty": czynnosci_dzienne_lifecycle_minuty,
        "czynnosci_dzienne_koszt": czynnosci_dzienne_lifecycle_koszt,
        "czynnosci_dzienne_lifecycle_koszt": czynnosci_dzienne_lifecycle_koszt,
        "narzut_dzienny_na_sprawe": narzut_dzienny_na_sprawe,
        "alokowany_koszt_staly_na_sprawe": alokowany_koszt_staly_na_sprawe,
        "laczne_minuty": laczne_minuty,
        "laczne_godziny": laczne_minuty / 60,
        "pojemnosc": oblicz_pojemnosc_zespolu(
            parametry["liczba_pracownikow"],
            parametry["liczba_dni_pracy_w_roku"],
            parametry["codzienne_czynnosci"],
            bezposrednie_minuty_spraw,
        ),
        "koszty_jednostkowe": {
            rodzaj: (
                wynagrodzenie_godzinowe
                * (srednie_minuty_sciezki + parametry["dodatkowe_minuty"][rodzaj])
                * mnoznik_zasobu_lifecycle
                / 60
                + alokowany_koszt_staly_na_sprawe
            )
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


def _skaluj_bezposrednie_czasy(parametry: dict, skala: float) -> dict:
    """Skaluje wszystkie czasy pracy nad sprawami, bez czynności dziennych."""
    wynik = _parametry_z_zmiana(parametry)
    for klucz in (
        "wspolne_czynnosci",
        "procesowe_czynnosci",
        "ugodowe_czynnosci",
        "dodatkowe_minuty",
    ):
        wynik[klucz] = {
            nazwa: minuty * skala for nazwa, minuty in parametry[klucz].items()
        }
    wynik["analiza_mozliwosci_ugody"] = parametry["analiza_mozliwosci_ugody"] * skala
    wynik["obsluga_ii_instancji_minuty"] = parametry["obsluga_ii_instancji_minuty"] * skala
    return wynik


def oblicz_prog_czasu(parametry: dict) -> dict:
    """Wyznacza numerycznie skrócenie czasu z narzutem lifecycle."""
    wyniki = oblicz_model(parametry)
    liczba_spraw = wyniki["ogolem"]["liczba_spraw"]
    bezposrednie_minuty = wyniki["bezposrednie_minuty_spraw"]
    obecny_sredni_czas = bezposrednie_minuty / 60 / liczba_spraw if liczba_spraw else 0.0
    wynik_podstawowy = {
        "obecny_sredni_czas": obecny_sredni_czas,
        "czynnosci_dzienne_minuty": wyniki["czynnosci_dzienne_lifecycle_minuty"],
    }
    if wyniki["ogolem"]["wynik_po_podatku"] >= 0:
        return {
            **wynik_podstawowy,
            "mozliwe": True,
            "juz_rentowny": True,
            "redukcja_minut_na_sprawe": 0.0,
            "docelowy_sredni_czas": obecny_sredni_czas,
            "docelowy_udzial_czasu": 1.0,
        }
    if not liczba_spraw or bezposrednie_minuty <= 0:
        return {**wynik_podstawowy, "mozliwe": False, "juz_rentowny": False}
    if oblicz_model(_skaluj_bezposrednie_czasy(parametry, 0.0))["ogolem"]["wynik_po_podatku"] < 0:
        return {**wynik_podstawowy, "mozliwe": False, "juz_rentowny": False}

    dol, gora = 0.0, 1.0
    for _ in range(48):
        srodek = (dol + gora) / 2
        if oblicz_model(_skaluj_bezposrednie_czasy(parametry, srodek))["ogolem"]["wynik_po_podatku"] >= 0:
            dol = srodek
        else:
            gora = srodek
    docelowy_udzial_czasu = dol
    docelowe_minuty = bezposrednie_minuty * docelowy_udzial_czasu
    redukcja_na_sprawe = (bezposrednie_minuty - docelowe_minuty) / liczba_spraw
    return {
        **wynik_podstawowy,
        "mozliwe": True,
        "juz_rentowny": False,
        "redukcja_minut_na_sprawe": redukcja_na_sprawe,
        "docelowy_sredni_czas": docelowe_minuty / 60 / liczba_spraw,
        "docelowy_udzial_czasu": docelowy_udzial_czasu,
    }


def oblicz_prog_kosztu_stalego(parametry: dict) -> dict:
    """Maksymalna stawka kosztu operacji przy wyniku równym zero."""
    wyniki = oblicz_model(parametry)
    obecny = parametry["koszt_staly_na_godzine"]
    godziny_operacyjne = wyniki["godziny_operacyjne_rocznie"]
    if godziny_operacyjne <= 0:
        return {"mozliwe": False, "obecnie": obecny}
    prog = (
        wyniki["ogolem"]["przychod"]
        - wyniki["koszt_pracy_pracownika_lifecycle"]
    ) / godziny_operacyjne
    if prog < 0:
        return {"mozliwe": False, "obecnie": obecny}
    return {
        "mozliwe": True,
        "obecnie": obecny,
        "prog": prog,
        "wymagana_redukcja": max(0.0, obecny - prog),
    }


def oblicz_prog_wynagrodzenia_pracownika(parametry: dict) -> dict:
    """Maksymalna stawka pracy przy wyniku równym zero."""
    wyniki = oblicz_model(parametry)
    obecny = parametry["wynagrodzenie_pracownika_na_godzine"]
    godziny_zasobu = wyniki["laczne_godziny_zasobu_lifecycle"]
    if godziny_zasobu <= 0:
        return {"mozliwe": False, "obecnie": obecny}
    prog = (
        wyniki["ogolem"]["przychod"] - wyniki["koszt_staly_roczny"]
    ) / godziny_zasobu
    if prog < 0:
        return {"mozliwe": False, "obecnie": obecny}
    return {
        "mozliwe": True,
        "obecnie": obecny,
        "prog": prog,
        "wymagana_redukcja": max(0.0, obecny - prog),
    }
