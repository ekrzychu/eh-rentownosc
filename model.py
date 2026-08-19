"""Deterministyczny model rentowności portfela spraw."""

from math import floor

LICZBA_SPRAW = 600
PROG_WPS = 10_000
NISKI_WPS = 2_500
WYSOKI_WPS = 25_000
KOSZT_STALY_NA_GODZINE = 81.17
WYNAGRODZENIE_PRACOWNIKA_NA_GODZINE = 59.88
KOSZT_GODZINY = KOSZT_STALY_NA_GODZINE + WYNAGRODZENIE_PRACOWNIKA_NA_GODZINE

PODSTAWOWE_CZYNNOSCI = {
    "Analiza sprawy i kompletowanie załącznika": 30,
    "Wniosek o wideo": 10,
    "Duplika": 90,
    "Pytania do świadków": 60,
    "Rozprawa": 60,
    "Notatka z rozprawy": 10,
    "Wyrok": 20,
    "Oferta ugody": 15,
    "Projekt ugody": 20,
    "Podpisanie ugody": 20,
    "Obsługa skrzynki ugody EH": 30,
    "Komunikacja z EH i zlecanie opłat w SOSS": 30,
    "Umieszczanie dokumentów w SOSS": 30,
}
PODSTAWOWE_MINUTY = sum(PODSTAWOWE_CZYNNOSCI.values())

DODATKOWE_MINUTY = {"P1": 120, "P2": 180, "P3": 240}
P1_PERCENT = 25.0
P2_PERCENT = 58.0
P3_PERCENT = 17.0
HIGH_WPS_PERCENT = 80.0
LOW_WPS_PERCENT = 100.0 - HIGH_WPS_PERCENT

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
        "podstawowe_czynnosci": PODSTAWOWE_CZYNNOSCI.copy(),
        "dodatkowe_minuty": DODATKOWE_MINUTY.copy(),
        "udzialy_rodzajow": {"P1": P1_PERCENT, "P2": P2_PERCENT, "P3": P3_PERCENT},
        "wysoki_wps_procent": HIGH_WPS_PERCENT,
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


def oblicz_wynagrodzenie(wps: float, prog_wps: float) -> float:
    """Oblicza wynagrodzenie kancelarii dla jednej sprawy."""
    fin = wps / 2
    if wps < prog_wps:
        return 250 + min(0.20 * (wps - fin), 2000)
    return 500 + min(0.08 * (wps - fin), 5000)


def oblicz_koszt(
    rodzaj_sprawy: str,
    podstawowe_czynnosci: dict[str, float],
    dodatkowe_minuty: dict[str, float],
    koszt_godziny: float,
) -> float:
    """Oblicza koszt jednej sprawy danego rodzaju."""
    podstawowe_minuty = sum(podstawowe_czynnosci.values())
    laczne_minuty = podstawowe_minuty + dodatkowe_minuty[rodzaj_sprawy]
    return koszt_godziny * (laczne_minuty / 60)


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
    rodzaj: str, grupa_wps: str, liczba: int, wps: float, parametry: dict
) -> dict:
    """Oblicza wynik dla jednej z sześciu deterministycznych grup."""
    koszt_godziny = (
        parametry["koszt_staly_na_godzine"]
        + parametry["wynagrodzenie_pracownika_na_godzine"]
    )
    wynagrodzenie = oblicz_wynagrodzenie(wps, parametry["prog_wps"])
    koszt = oblicz_koszt(
        rodzaj,
        parametry["podstawowe_czynnosci"],
        parametry["dodatkowe_minuty"],
        koszt_godziny,
    )
    laczne_minuty = sum(parametry["podstawowe_czynnosci"].values()) + parametry["dodatkowe_minuty"][rodzaj]
    wynik_jednostkowy = wynagrodzenie - koszt
    return {
        "rodzaj": rodzaj,
        "grupa_wps": grupa_wps,
        "wps": wps,
        "liczba": liczba,
        "wynagrodzenie": wynagrodzenie,
        "koszt": koszt,
        "wynik_jednostkowy": wynik_jednostkowy,
        "laczne_minuty": laczne_minuty,
        "laczny_przychod": liczba * wynagrodzenie,
        "laczny_koszt": liczba * koszt,
        "laczny_wynik": liczba * wynik_jednostkowy,
    }


def oblicz_model(parametry: dict | None = None) -> dict:
    """Zwraca pełne wyniki modelu dla przekazanych lub domyślnych parametrów."""
    if parametry is None:
        parametry = domyslne_parametry()

    podzial_spraw = oblicz_podzial_spraw(
        parametry["liczba_spraw"], parametry["udzialy_rodzajow"], parametry["wysoki_wps_procent"]
    )
    grupy = []
    for rodzaj, podzial in podzial_spraw.items():
        for grupa_wps, liczba in podzial.items():
            wps = parametry["wysoki_wps"] if grupa_wps == "wysoki_wps" else parametry["niski_wps"]
            grupy.append(oblicz_grupe(rodzaj, grupa_wps, liczba, wps, parametry))

    wedlug_wps = {
        "niski_wps": podsumuj_grupy([g for g in grupy if g["grupa_wps"] == "niski_wps"]),
        "wysoki_wps": podsumuj_grupy([g for g in grupy if g["grupa_wps"] == "wysoki_wps"]),
    }
    rodzaje = {
        rodzaj: podsumuj_grupy([g for g in grupy if g["rodzaj"] == rodzaj])
        for rodzaj in podzial_spraw
    }
    podstawowe_minuty = sum(parametry["podstawowe_czynnosci"].values())
    koszt_godziny = parametry["koszt_staly_na_godzine"] + parametry["wynagrodzenie_pracownika_na_godzine"]
    return {
        "ogolem": podsumuj_grupy(grupy),
        "wps_niski": wedlug_wps["niski_wps"],
        "wps_wysoki": wedlug_wps["wysoki_wps"],
        "rodzaje": rodzaje,
        "grupy": grupy,
        "podzial_spraw": podzial_spraw,
        "podstawowe_minuty": podstawowe_minuty,
        "koszt_godziny": koszt_godziny,
        "koszty_jednostkowe": {
            rodzaj: oblicz_koszt(rodzaj, parametry["podstawowe_czynnosci"], parametry["dodatkowe_minuty"], koszt_godziny)
            for rodzaj in parametry["dodatkowe_minuty"]
        },
    }
