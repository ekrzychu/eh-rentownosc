"""Ekonomika pełnego lifecycle kohorty, niezależna od obsady i kalendarza.

Pojemność, kolejka, opóźnienia przychodu i koszt utrzymywanej obsady należą
do timeline.py. Ten model wycenia wyłącznie zasób zużyty przez kohortę.
"""

from math import isfinite

from config import parametry_modelu, wczytaj_defaults


MINUTY_DNIA_PRACY = wczytaj_defaults()["organizacja"]["minuty_dnia_pracy"]

KATEGORIE_SPRAW = {
    "P1": "Koszty naprawy, uprzednie uzgodnienie kosztów",
    "P2": "Koszty najmu pojazdu zastępczego, zadośćuczynienie, nieruchomości",
    "P3": "Pozostałe sprawy",
}

SCIEZKI_UGODOWE = ("automatyczne_ramy_ugoda", "zawarte_poza_ramami")
SCIEZKI_BEZ_UGODY = (
    "kategoryczna_odmowa",
    "automatyczne_ramy_brak_ugody",
    "brak_szans",
    "brak_ugody_poza_ramami",
)
SCIEZKI_UGODOWE_LISCIE = SCIEZKI_UGODOWE + SCIEZKI_BEZ_UGODY


def domyslne_parametry() -> dict:
    """Zwraca kopię wszystkich edytowalnych parametrów modelu."""
    return parametry_modelu()


def waliduj_parametry(parametry: dict) -> None:
    """Waliduje wspólne założenia przed uruchomieniem któregokolwiek modelu."""
    calkowite = ("liczba_spraw", "liczba_pracownikow")
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
        "skutecznosc_automatycznych_ram_percent",
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
    if sum(parametry["codzienne_czynnosci"].values()) > MINUTY_DNIA_PRACY:
        raise ValueError(f"Czynności dzienne nie mogą przekraczać {MINUTY_DNIA_PRACY} minut dziennie.")
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
    skutecznosc_automatycznych_ram_percent: float,
    szansa_na_ugode_percent: float,
    zawarte_ugody_percent: float | None = None,
) -> dict[str, float]:
    """Oblicza sześć rozłącznych wyników drzewa ugodowego."""
    if zawarte_ugody_percent is None:
        zawarte_ugody_percent = domyslne_parametry()["zawarte_ugody_percent"]
    wartosci = (
        kategoryczna_odmowa_percent,
        automatyczne_ramy_percent,
        skutecznosc_automatycznych_ram_percent,
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
    automatyczne_ramy_ugoda = (
        automatyczne_ramy_percent * skutecznosc_automatycznych_ram_percent / 100
    )
    automatyczne_ramy_brak_ugody = (
        automatyczne_ramy_percent - automatyczne_ramy_ugoda
    )
    szansa_poza_ramami = pozostale * szansa_na_ugode_percent / 100
    brak_szans = pozostale * (100.0 - szansa_na_ugode_percent) / 100
    zawarte_poza_ramami = szansa_poza_ramami * zawarte_ugody_percent / 100
    brak_ugody_poza_ramami = szansa_poza_ramami * (100.0 - zawarte_ugody_percent) / 100
    zakonczone_ugoda = automatyczne_ramy_ugoda + zawarte_poza_ramami
    bez_ugody = 100.0 - zakonczone_ugoda
    wynik = {
        "kategoryczna_odmowa": kategoryczna_odmowa_percent,
        "automatyczne_ramy": automatyczne_ramy_percent,
        "automatyczne_ramy_ugoda": automatyczne_ramy_ugoda,
        "automatyczne_ramy_brak_ugody": automatyczne_ramy_brak_ugody,
        "pozostale_sprawy": pozostale,
        "szansa_poza_ramami": szansa_poza_ramami,
        "zawarte_poza_ramami": zawarte_poza_ramami,
        "brak_ugody_poza_ramami": brak_ugody_poza_ramami,
        "brak_szans": brak_szans,
        "zakonczone_ugoda": zakonczone_ugoda,
        "bez_ugody": bez_ugody,
    }
    if any(wynik[nazwa] < -1e-9 for nazwa in SCIEZKI_UGODOWE_LISCIE):
        raise RuntimeError("Wyliczono ujemny udział ścieżki ugodowej.")
    if abs(sum(wynik[nazwa] for nazwa in SCIEZKI_UGODOWE_LISCIE) - 100) > 1e-8:
        raise RuntimeError("Udziały ścieżek ugodowych nie sumują się do 100%.")
    if abs(wynik["zakonczone_ugoda"] + wynik["bez_ugody"] - 100) > 1e-8:
        raise RuntimeError("Udziały zakończeń ugodowych nie sumują się do 100%.")
    for nazwa in SCIEZKI_UGODOWE_LISCIE:
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
        "automatyczne_ramy_ugoda": wspolne + ugodowe,
        "automatyczne_ramy_brak_ugody": (
            wspolne + przygotowanie_ugody + procesowe
        ),
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
    oczekiwany_czas = udzial_ii_instancji_percent / 100 * obsluga_ii_instancji_minuty
    czasy_ii_instancji = {
        nazwa: oczekiwany_czas if nazwa in SCIEZKI_BEZ_UGODY else 0.0
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
    return sum(
        udzialy_ugod[nazwa] / 100 * czasy_sciezek[nazwa]
        for nazwa in SCIEZKI_UGODOWE_LISCIE
    )


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


def oblicz_oczekiwany_podzial_spraw(
    liczba_spraw: int,
    udzialy_rodzajow: dict[str, float],
    wysoki_wps_procent: float,
) -> dict[str, dict[str, float]]:
    """Dzieli ekonomię portfela na oczekiwane, niezaokrąglone liczby spraw."""
    if liczba_spraw < 0:
        raise ValueError("Liczba spraw nie może być ujemna.")
    if abs(sum(udzialy_rodzajow.values()) - 100) > 1e-9:
        raise ValueError("Udziały rodzajów spraw muszą sumować się do 100%.")
    if not 0 <= wysoki_wps_procent <= 100:
        raise ValueError("Udział wysokiego WPS musi mieścić się w zakresie 0–100%.")
    wysoki = wysoki_wps_procent / 100
    return {
        rodzaj: {
            "wysoki_wps": liczba_spraw * udzial / 100 * wysoki,
            "niski_wps": liczba_spraw * udzial / 100 * (1 - wysoki),
        }
        for rodzaj, udzial in udzialy_rodzajow.items()
    }


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


def podsumuj_grupy(grupy: list[dict]) -> dict:
    """Agreguje dowolny zestaw grup spraw."""
    liczba_spraw = sum(grupa["liczba"] for grupa in grupy)
    przychod = sum(grupa["laczny_przychod"] for grupa in grupy)
    koszt_wynagrodzen = sum(grupa["laczny_koszt_wynagrodzenia"] for grupa in grupy)
    koszt_narzutu = sum(grupa["laczny_koszt_narzutu_ogolnego"] for grupa in grupy)
    koszt = koszt_wynagrodzen + koszt_narzutu
    wynik_przed_podatkiem = przychod - koszt
    przychod_ugody = sum(grupa["laczny_przychod_ugody"] for grupa in grupy)
    przychod_wyroki = sum(grupa["laczny_przychod_wyroki"] for grupa in grupy)
    return {
        "liczba_spraw": liczba_spraw,
        "przychod": przychod,
        "koszt_narzutu_ogolnego": koszt_narzutu,
        "koszt_wynagrodzenia": koszt_wynagrodzen,
        "koszt_calkowity": koszt,
        "wynik_przed_podatkiem": wynik_przed_podatkiem,
        "marza_przed_podatkiem": (
            wynik_przed_podatkiem / przychod * 100 if przychod else 0.0
        ),
        "przychod_ugody": przychod_ugody,
        "przychod_wyroki": przychod_wyroki,
        "sredni_przychod": przychod / liczba_spraw if liczba_spraw else 0.0,
        "sredni_koszt": koszt / liczba_spraw if liczba_spraw else 0.0,
        "sredni_wynik_przed_podatkiem": (
            wynik_przed_podatkiem / liczba_spraw if liczba_spraw else 0.0
        ),
    }


def oblicz_grupe(
    rodzaj: str,
    grupa_wps: str,
    liczba: float,
    wps: float,
    parametry: dict,
    srednie_minuty_sciezki: float,
    mnoznik_zasobu_lifecycle: float,
    udzial_ugod: float,
    udzial_wyrokow: float,
) -> dict:
    """Oblicza segment według zużytych płatnych godzin zasobu."""
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
    koszt_wynagrodzenia = (
        minuty_zasobu / 60 * parametry["wynagrodzenie_pracownika_na_godzine"]
    )
    koszt_narzutu_ogolnego = (
        minuty_zasobu / 60 * parametry["koszt_staly_na_godzine"]
    )
    koszt_bezposredni = bezposrednie_minuty / 60 * (
        parametry["wynagrodzenie_pracownika_na_godzine"]
        + parametry["koszt_staly_na_godzine"]
    )
    narzut_dzienny_na_sprawe = (
        koszt_wynagrodzenia + koszt_narzutu_ogolnego - koszt_bezposredni
    )
    koszt_calkowity = koszt_wynagrodzenia + koszt_narzutu_ogolnego
    wynik_jednostkowy = wynagrodzenie - koszt_calkowity
    return {
        "rodzaj": rodzaj,
        "grupa_wps": grupa_wps,
        "wps": wps,
        "liczba": liczba,
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
        "koszt_narzutu_ogolnego": koszt_narzutu_ogolnego,
        "koszt_wynagrodzenia": koszt_wynagrodzenia,
        "koszt_calkowity": koszt_calkowity,
        "wynik_jednostkowy_przed_podatkiem": wynik_jednostkowy,
        "bezposrednie_minuty_na_sprawe": bezposrednie_minuty,
        "laczny_przychod": liczba * wynagrodzenie,
        "laczny_przychod_ugody": liczba * oczekiwany_przychod_ugody,
        "laczny_przychod_wyroki": liczba * oczekiwany_przychod_wyroki,
        "laczny_koszt_narzutu_ogolnego": liczba * koszt_narzutu_ogolnego,
        "laczny_koszt_wynagrodzenia": liczba * koszt_wynagrodzenia,
        "laczny_koszt_calkowity": liczba * koszt_calkowity,
        "laczny_wynik_przed_podatkiem": liczba * wynik_jednostkowy,
    }


def oblicz_model(parametry: dict | None = None) -> dict:
    """Zwraca pełne wyniki nowego modelu czasu, kosztu i pojemności."""
    if parametry is None:
        parametry = domyslne_parametry()
    waliduj_parametry(parametry)

    udzialy_ugod = oblicz_udzialy_ugod(
        kategoryczna_odmowa_percent=parametry["kategoryczna_odmowa_percent"],
        automatyczne_ramy_percent=parametry["automatyczne_ramy_percent"],
        skutecznosc_automatycznych_ram_percent=parametry[
            "skutecznosc_automatycznych_ram_percent"
        ],
        szansa_na_ugode_percent=parametry["szansa_na_ugode_percent"],
        zawarte_ugody_percent=parametry["zawarte_ugody_percent"],
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
    podzial_spraw = oblicz_oczekiwany_podzial_spraw(
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
    narzut_ogolny_godzinowy = parametry["koszt_staly_na_godzine"]
    koszt_zasobu_na_godzine = narzut_ogolny_godzinowy + wynagrodzenie_godzinowe
    godziny_zasobu_lifecycle = metryki_lifecycle["laczne_godziny_zasobu_lifecycle"]
    koszt_narzutu_ogolnego_lifecycle = (
        godziny_zasobu_lifecycle * narzut_ogolny_godzinowy
    )
    koszt_wynagrodzen_lifecycle = godziny_zasobu_lifecycle * wynagrodzenie_godzinowe
    koszt_lifecycle_razem = (
        koszt_narzutu_ogolnego_lifecycle + koszt_wynagrodzen_lifecycle
    )
    czynnosci_dzienne_lifecycle_koszt = (
        czynnosci_dzienne_lifecycle_minuty / 60 * koszt_zasobu_na_godzine
    )
    narzut_dzienny_na_sprawe = (
        czynnosci_dzienne_lifecycle_koszt / liczba_spraw if liczba_spraw else 0.0
    )
    produktywne_minuty = metryki_lifecycle["produktywne_minuty_na_osobodzien"]
    mnoznik_zasobu_lifecycle = (
        MINUTY_DNIA_PRACY / produktywne_minuty
        if produktywne_minuty > 0
        else 0.0
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
                    mnoznik_zasobu_lifecycle,
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
    ogolem = podsumuj_grupy(grupy)
    rozliczenie_podatku = oblicz_podatek_dochodowy(
        ogolem["przychod"],
        ogolem["koszt_calkowity"],
        parametry["podatek_dochodowy_percent"],
    )
    ogolem.update(rozliczenie_podatku)
    ogolem["sredni_wynik_po_podatku"] = (
        ogolem["wynik_po_podatku"] / liczba_spraw if liczba_spraw else 0.0
    )

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
        "narzut_kosztow_ogolnych_na_godzine": narzut_ogolny_godzinowy,
        "wynagrodzenie_pracownika_na_godzine": wynagrodzenie_godzinowe,
        "koszt_zasobu_na_godzine": koszt_zasobu_na_godzine,
        "koszt_narzutu_ogolnego_lifecycle": koszt_narzutu_ogolnego_lifecycle,
        "koszt_wynagrodzen_lifecycle": koszt_wynagrodzen_lifecycle,
        "koszt_lifecycle_razem": koszt_lifecycle_razem,
        "bezposrednie_minuty_spraw": bezposrednie_minuty_spraw,
        **metryki_lifecycle,
        "czynnosci_dzienne_lifecycle_koszt": czynnosci_dzienne_lifecycle_koszt,
        "narzut_dzienny_na_sprawe": narzut_dzienny_na_sprawe,
        "koszty_jednostkowe": {
            rodzaj: (
                koszt_zasobu_na_godzine
                * (srednie_minuty_sciezki + parametry["dodatkowe_minuty"][rodzaj])
                * mnoznik_zasobu_lifecycle
                / 60
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
    """Maksymalny narzut ogólny na godzinę zasobu przy wyniku równym zero."""
    wyniki = oblicz_model(parametry)
    obecny = parametry["koszt_staly_na_godzine"]
    godziny_zasobu = wyniki["laczne_godziny_zasobu_lifecycle"]
    if godziny_zasobu <= 0:
        return {"mozliwe": False, "obecnie": obecny}
    prog = (
        wyniki["ogolem"]["przychod"]
        - wyniki["koszt_wynagrodzen_lifecycle"]
    ) / godziny_zasobu
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
        wyniki["ogolem"]["przychod"]
        - wyniki["koszt_narzutu_ogolnego_lifecycle"]
    ) / godziny_zasobu
    if prog < 0:
        return {"mozliwe": False, "obecnie": obecny}
    return {
        "mozliwe": True,
        "obecnie": obecny,
        "prog": prog,
        "wymagana_redukcja": max(0.0, obecny - prog),
    }
