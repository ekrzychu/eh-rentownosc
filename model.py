"""Ekonomika pełnego lifecycle kohorty, z godzinowymi stawkami wspólnej obsady, bez limitów kalendarza.

Pojemność, kolejka, opóźnienia przychodu i koszt utrzymywanej obsady należą
do timeline.py. Ten model wycenia wyłącznie zasób zużyty przez kohortę.
"""

from costs import sprawdz_stare_koszty, wspolne_stawki
from math import fsum, isfinite

from config import parametry_modelu, wczytaj_defaults
from staff import ROLE, GODZINY_ETATU_MIESIECZNIE, nowy_pracownik, minuty_dzienne_wedlug_roli, srednie_stawki_wedlug_roli
from workflow import SCIEZKI_UGODOWE, SCIEZKI_BEZ_UGODY, etapy_sprawy


MINUTY_DNIA_PRACY = wczytaj_defaults()["organizacja"]["minuty_dnia_pracy"]

KATEGORIE_SPRAW = {
    "P1": "Koszty naprawy, uprzednie uzgodnienie kosztów",
    "P2": "Koszty najmu pojazdu zastępczego, zadośćuczynienie, nieruchomości",
    "P3": "Pozostałe sprawy",
}

SCIEZKI_UGODOWE_LISCIE = SCIEZKI_UGODOWE + SCIEZKI_BEZ_UGODY


def domyslne_parametry() -> dict:
    """Zwraca kopię wszystkich edytowalnych parametrów modelu."""
    parametry = parametry_modelu()
    parametry["pracownicy"] = [nowy_pracownik(i) for i in range(parametry["liczba_pracownikow"])]
    return parametry


def waliduj_parametry(parametry: dict) -> None:
    """Waliduje wspólne założenia przed uruchomieniem któregokolwiek modelu."""
    if "wynagrodzenie_pracownika_na_godzine" in parametry:
        raise ValueError("Stawki prawników należy podawać wyłącznie w obsadzie pracowników.")
    sprawdz_stare_koszty(parametry.get("koszty_kontraktu"))
    calkowite = ("liczba_spraw",)
    for nazwa in calkowite:
        wartosc = parametry[nazwa]
        if not isinstance(wartosc, int) or isinstance(wartosc, bool) or wartosc < 0:
            raise ValueError(f"Parametr {nazwa} musi być nieujemną liczbą całkowitą.")

    nieujemne = (
        "prog_wps",
        "niski_wps",
        "wysoki_wps",
        "koszt_staly_na_godzine",
        "koszt_sekretariatu_na_godzine",
        "sekretariat_minuty_na_sprawe",
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
    if any(v > MINUTY_DNIA_PRACY for v in minuty_dzienne_wedlug_roli(parametry["codzienne_czynnosci"]).values()):
        raise ValueError(f"Czynności dzienne jednej roli nie mogą przekraczać {MINUTY_DNIA_PRACY} minut dziennie.")
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
    """Roczny stały nakład projektu; liczba godzin spraw nie zmienia kalendarza.

    Funkcja opisuje roczny kalendarz 12 × 167 / 8 dni, niezależnie od
    godzin bezpośrednich. Zerową alokację pustego portfela obsługuje oblicz_model.
    """
    if bezposrednie_minuty_spraw < 0 or any(v < 0 for v in codzienne_czynnosci.values()):
        raise ValueError("Czas pracy nie może być ujemny.")
    dni = 12 * GODZINY_ETATU_MIESIECZNIE / 8
    dzienne = dni * fsum(codzienne_czynnosci.values())
    return {
        "produktywne_minuty_na_osobodzien": MINUTY_DNIA_PRACY,
        "ekwiwalent_osobodni_kohorty": dni,
        "czynnosci_dzienne_lifecycle_minuty": dzienne,
        "czynnosci_dzienne_lifecycle_godziny": dzienne / 60,
        "laczne_minuty_zasobu_lifecycle": bezposrednie_minuty_spraw + dzienne,
        "laczne_godziny_zasobu_lifecycle": (bezposrednie_minuty_spraw + dzienne) / 60,
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
    koszt_sekretariatu = sum(grupa["laczny_koszt_sekretariatu"] for grupa in grupy)
    koszt = koszt_wynagrodzen + koszt_narzutu + koszt_sekretariatu
    wynik_przed_podatkiem = przychod - koszt
    przychod_ugody = sum(grupa["laczny_przychod_ugody"] for grupa in grupy)
    przychod_wyroki = sum(grupa["laczny_przychod_wyroki"] for grupa in grupy)
    return {
        "liczba_spraw": liczba_spraw,
        "przychod": przychod,
        "koszt_narzutu_ogolnego": koszt_narzutu,
        "koszt_wynagrodzenia": koszt_wynagrodzen,
        "koszt_sekretariatu": koszt_sekretariatu,
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


def oblicz_czasy_sciezek_wedlug_roli(parametry: dict) -> dict:
    """Sześć dotychczasowych ścieżek, bez dodatkowego czasu P i II instancji."""
    return {path: {r: fsum(e.minuty for e in etapy_sprawy(parametry, path) if e.rola == r)
                   for r in ROLE} for path in SCIEZKI_UGODOWE_LISCIE}


def _koszty_pracy(minuty: dict, stawki: dict, narzut: float) -> dict:
    godziny = {r: minuty[r] / 60 for r in ROLE}
    if any(godziny[r] > 0 and stawki[r] is None for r in ROLE):
        raise ValueError("Brak stawki wymaganej do wyceny pracy roli.")
    place = {r: godziny[r] * stawki[r] if godziny[r] > 0 else 0.0 for r in ROLE}
    return {"godziny": godziny, "place": place,
            "narzut": fsum(godziny.values()) * narzut}


def oblicz_grupe(grupa: dict, parametry: dict, minuty: dict, stawki: dict, dzienne_h: float) -> dict:
    """Wycena minut każdej roli; przychód i liczebność pochodzą ze wspólnego przepływu."""
    niedostepny = any(minuty[r] > 0 and stawki[r] is None for r in ROLE)
    if grupa["liczba"] == 0 and niedostepny:
        # Pusty segment nie wymaga stawki. Jego hipotetycznej wyceny nie zastępuje zero.
        return {**grupa, "bezposrednie_minuty_wedlug_roli": dict(minuty),
            "bezposrednie_minuty_na_sprawe": fsum(minuty.values()),
            **{k: None for k in ("koszt_calkowity", "koszt_bezposredni", "narzut_dzienny_na_sprawe",
                "koszt_wynagrodzenia", "koszt_narzutu_ogolnego", "koszt_sekretariatu",
                "wynik_jednostkowy_przed_podatkiem", "minuty_zasobu_pracownika", "godziny_zasobu_pracownika")},
            **{k: 0.0 for k in ("laczny_koszt_narzutu_ogolnego", "laczny_koszt_wynagrodzenia",
                "laczny_koszt_sekretariatu", "laczny_koszt_calkowity", "laczny_wynik_przed_podatkiem")}}
    koszt = _koszty_pracy(minuty, stawki, parametry["koszt_staly_na_godzine"])
    place_dzienne = dzienne_h * (stawki["EH"] or 0)
    narzut_dzienny = dzienne_h * parametry["koszt_staly_na_godzine"]
    place = fsum(koszt["place"].values()) + place_dzienne
    narzut = koszt["narzut"] + narzut_dzienny
    bezposredni = fsum(minuty[r] / 60 * ((stawki[r] or 0) + parametry["koszt_staly_na_godzine"]) for r in ROLE)
    sekretariat = wspolne_stawki(parametry)["secretariat_cost_per_case"]
    razem = place + narzut + sekretariat
    liczba = grupa["liczba"]
    przychod = grupa["oczekiwane_wynagrodzenie"]
    return {**grupa,
            "bezposrednie_minuty_wedlug_roli": dict(minuty),
            "godziny_zasobu_wedlug_roli": {**koszt["godziny"], "EH": koszt["godziny"]["EH"] + dzienne_h},
            "koszt_wynagrodzenia_wedlug_roli": {**koszt["place"], "EH": koszt["place"]["EH"] + place_dzienne},
            "koszt_dziennych_plac": place_dzienne, "koszt_dziennych_narzutu": narzut_dzienny,
            "koszt_bezposredni": bezposredni,
            "narzut_dzienny_na_sprawe": place_dzienne + narzut_dzienny,
            "minuty_zasobu_pracownika": (fsum(koszt["godziny"].values()) + dzienne_h) * 60,
            "godziny_zasobu_pracownika": fsum(koszt["godziny"].values()) + dzienne_h,
            "koszt_narzutu_ogolnego": narzut, "koszt_wynagrodzenia": place,
            "koszt_sekretariatu": sekretariat, "koszt_calkowity": razem,
            "wynik_jednostkowy_przed_podatkiem": przychod - razem,
            "bezposrednie_minuty_na_sprawe": fsum(minuty.values()),
            "laczny_koszt_narzutu_ogolnego": liczba * narzut,
            "laczny_koszt_wynagrodzenia": liczba * place,
            "laczny_koszt_sekretariatu": liczba * sekretariat,
            "laczny_koszt_calkowity": liczba * razem,
            "laczny_wynik_przed_podatkiem": liczba * (przychod - razem)}


def oblicz_przeplyw(parametry: dict | None = None) -> dict:
    """Wspólne oczekiwania pracy i przychodu; nie wymaga wyceny ani dostępnej obsady."""
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
    sciezki_role = oblicz_czasy_sciezek_wedlug_roli(parametry)
    sciezki_role_ii = {path: {**minuty, "EH": minuty["EH"] + czasy_ii_instancji_sciezek[path]}
                       for path, minuty in sciezki_role.items()}
    srednie_role = {r: fsum(udzialy_ugod[path] / 100 * minuty[r]
                            for path, minuty in sciezki_role_ii.items()) for r in ROLE}
    minuty_rodzaje = {rodzaj: {"EH": srednie_role["EH"] + parametry["dodatkowe_minuty"][rodzaj],
                              "UGODY": srednie_role["UGODY"]} for rodzaj in podzial_spraw}
    roczne_role = {r: fsum(sum(podzial.values()) * minuty_rodzaje[rodzaj][r]
                           for rodzaj, podzial in podzial_spraw.items()) for r in ROLE}
    grupy = []
    for rodzaj, podzial in podzial_spraw.items():
        for grupa_wps, liczba in podzial.items():
            wps = parametry["wysoki_wps"] if grupa_wps == "wysoki_wps" else parametry["niski_wps"]
            ugoda = oblicz_wynagrodzenie(wps, parametry["prog_wps"], parametry["srednia_kwota_ugody_percent"])
            wyrok = oblicz_wynagrodzenie(wps, parametry["prog_wps"], parametry["srednia_kwota_wyroku_percent"])
            przychod_ugody = udzialy_ugod["zakonczone_ugoda"] / 100 * ugoda
            przychod_wyroki = udzialy_ugod["bez_ugody"] / 100 * wyrok
            grupy.append({"rodzaj": rodzaj, "grupa_wps": grupa_wps, "wps": wps, "liczba": liczba,
                "wynagrodzenie_ugoda": ugoda, "wynagrodzenie_wyrok": wyrok,
                "oczekiwane_wynagrodzenie": przychod_ugody + przychod_wyroki,
                "oczekiwany_przychod_ugody": przychod_ugody, "oczekiwany_przychod_wyroki": przychod_wyroki,
                "udzial_ugod": udzialy_ugod["zakonczone_ugoda"], "udzial_wyrokow": udzialy_ugod["bez_ugody"],
                "laczny_przychod": liczba * (przychod_ugody + przychod_wyroki),
                "laczny_przychod_ugody": liczba * przychod_ugody, "laczny_przychod_wyroki": liczba * przychod_wyroki})
    return {"grupy": grupy, "podzial_spraw": podzial_spraw, "udzialy_ugod": udzialy_ugod,
        "czasy_sciezek_ugod": czasy_sciezek, "czasy_ii_instancji_sciezek": czasy_ii_instancji_sciezek,
        "czasy_sciezek_z_ii_instancja": czasy_sciezek_z_ii_instancja,
        "czasy_sciezek_wedlug_roli": sciezki_role, "czasy_sciezek_z_ii_wedlug_roli": sciezki_role_ii,
        "srednie_minuty_podstawowej_sciezki_ugody": srednie_minuty_podstawowej_sciezki,
        "srednie_minuty_sciezki_ugody": srednie_minuty_sciezki,
        "minuty_rodzajow_wedlug_roli": minuty_rodzaje, "roczne_minuty_wedlug_roli": roczne_role,
        "bezposrednie_minuty_spraw": bezposrednie_minuty_spraw,
        **wskazniki_ii_instancji, "obsluga_ii_instancji_minuty": parametry["obsluga_ii_instancji_minuty"],
        "ogolem": {"liczba_spraw": liczba_spraw, "przychod": fsum(g["laczny_przychod"] for g in grupy),
                   "przychod_ugody": fsum(g["laczny_przychod_ugody"] for g in grupy),
                   "przychod_wyroki": fsum(g["laczny_przychod_wyroki"] for g in grupy)}}


def oblicz_model(parametry: dict | None = None) -> dict:
    """Wycena całego cyklu: bezpośrednia praca ról i stała roczna alokacja dziennych."""
    if parametry is None:
        parametry = domyslne_parametry()
    przeplyw = oblicz_przeplyw(parametry)
    if "pracownicy" not in parametry:
        raise ValueError("Brak wspólnej obsady pracowników do wyceny stawek.")
    stawki = srednie_stawki_wedlug_roli(parametry["pracownicy"])
    liczba = parametry["liczba_spraw"]
    dzienne = fsum(parametry["codzienne_czynnosci"].values())
    brak = [r for r in ROLE if (przeplyw["roczne_minuty_wedlug_roli"][r] > 0
            or (r == "EH" and liczba > 0 and dzienne > 0)) and stawki[r] is None]
    if brak:
        raise ValueError("Brak stawki godzinowej wymaganej roli: " + ", ".join(brak)
                         + ". Dodaj pracownika z dodatnim przydziałem do projektu. Kontrakt w czasie pozostaje dostępny.")
    role = {}
    for r in ROLE:
        direct = przeplyw["roczne_minuty_wedlug_roli"][r]
        daily = (12 * GODZINY_ETATU_MIESIECZNIE / 8 * dzienne
                 if r == "EH" and liczba > 0 else 0.0)
        role[r] = {
            "bezposrednie_minuty": direct, "mnoznik_zasobu": 1.0,
            "stawka_godzinowa": stawki[r],
            "ekwiwalent_osobodni_kohorty": 12 * GODZINY_ETATU_MIESIECZNIE / 8 if r == "EH" and liczba else 0.0,
            "czynnosci_dzienne_lifecycle_minuty": daily,
            "czynnosci_dzienne_lifecycle_godziny": daily / 60,
            "laczne_minuty_zasobu_lifecycle": direct + daily,
            "laczne_godziny_zasobu_lifecycle": (direct + daily) / 60,
        }
    dzienne_h_na_sprawe = role["EH"]["czynnosci_dzienne_lifecycle_godziny"] / liczba if liczba else 0.0
    grupy = [oblicz_grupe(g, parametry, przeplyw["minuty_rodzajow_wedlug_roli"][g["rodzaj"]], stawki, dzienne_h_na_sprawe)
             for g in przeplyw["grupy"]]
    wedlug_wps = {key: podsumuj_grupy([g for g in grupy if g["grupa_wps"] == key])
                  for key in ("niski_wps", "wysoki_wps")}
    rodzaje = {r: podsumuj_grupy([g for g in grupy if g["rodzaj"] == r]) for r in parametry["udzialy_rodzajow"]}
    ogolem = podsumuj_grupy(grupy)
    ogolem.update(oblicz_podatek_dochodowy(ogolem["przychod"], ogolem["koszt_calkowity"], parametry["podatek_dochodowy_percent"]))
    liczba = parametry["liczba_spraw"]
    ogolem["sredni_wynik_po_podatku"] = ogolem["wynik_po_podatku"] / liczba if liczba else 0.0
    metryki = {key: fsum(role[r][key] for r in ROLE) for key in (
        "ekwiwalent_osobodni_kohorty", "czynnosci_dzienne_lifecycle_minuty", "czynnosci_dzienne_lifecycle_godziny",
        "laczne_minuty_zasobu_lifecycle", "laczne_godziny_zasobu_lifecycle")}
    koszt_dzienny = fsum(g["liczba"] * g["narzut_dzienny_na_sprawe"] for g in grupy if g["liczba"] > 0)
    return {**przeplyw, **metryki, "ogolem": ogolem, "grupy": grupy,
        "wps_niski": wedlug_wps["niski_wps"], "wps_wysoki": wedlug_wps["wysoki_wps"], "rodzaje": rodzaje,
        "role": role, "stawki_wedlug_roli": stawki,
        "narzut_kosztow_ogolnych_na_godzine": parametry["koszt_staly_na_godzine"],
        "koszt_narzutu_ogolnego_lifecycle": ogolem["koszt_narzutu_ogolnego"],
        "sredni_narzut_ogolny_na_sprawe": ogolem["koszt_narzutu_ogolnego"] / liczba if liczba else 0.0,
        "wynagrodzenia_bezposrednie": fsum(role[r]["bezposrednie_minuty"] / 60 * (stawki[r] or 0) for r in ROLE),
        "wynagrodzenia_dzienne": role["EH"]["czynnosci_dzienne_lifecycle_godziny"] * (stawki["EH"] or 0),
        "koszt_wynagrodzen_lifecycle": ogolem["koszt_wynagrodzenia"],
        "koszt_sekretariatu_lifecycle": ogolem["koszt_sekretariatu"],
        "koszt_sekretariatu_na_sprawe": wspolne_stawki(parametry)["secretariat_cost_per_case"],
        "koszt_sekretariatu_na_godzine": parametry["koszt_sekretariatu_na_godzine"],
        "koszt_lifecycle_razem": ogolem["koszt_calkowity"], "czynnosci_dzienne_lifecycle_koszt": koszt_dzienny,
        "narzut_dzienny_na_sprawe": koszt_dzienny / liczba if liczba else 0.0,
        "koszty_jednostkowe": {r: next(g["koszt_calkowity"] for g in grupy if g["rodzaj"] == r)
                                 for r in parametry["udzialy_rodzajow"]}}


def _parametry_z_zmiana(parametry: dict, **zmiany) -> dict:
    """Tworzy bezpieczną kopię parametrów z podmienionymi wartościami."""
    kopia = {
        **parametry,
        "pracownicy": [dict(p) for p in parametry["pracownicy"]],
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
        - wyniki["koszt_sekretariatu_lifecycle"]
    ) / godziny_zasobu
    if prog < 0:
        return {"mozliwe": False, "obecnie": obecny}
    return {
        "mozliwe": True,
        "obecnie": obecny,
        "prog": prog,
        "wymagana_redukcja": max(0.0, obecny - prog),
    }


def oblicz_prog_wynagrodzenia_pracownika(parametry: dict, indeks: int = 0) -> dict:
    """Próg stawki jednej jawnej osoby, przy niezmienionych pozostałych stawkach."""
    wyniki = oblicz_model(parametry)
    if not isinstance(indeks, int) or isinstance(indeks, bool) or indeks < 0:
        raise ValueError("Indeks pracownika musi być nieujemną liczbą całkowitą.")
    if indeks >= len(parametry["pracownicy"]):
        return {"mozliwe": False, "obecnie": None}
    osoba = parametry["pracownicy"][indeks]
    obecny = osoba["stawka"]
    przypisani = [p for p in parametry["pracownicy"] if p["rola"] == osoba["rola"] and p["wykorzystanie_percent"] > 0]
    godziny = wyniki["role"][osoba["rola"]]["laczne_godziny_zasobu_lifecycle"]
    nachylenie = godziny / len(przypisani) if przypisani and osoba["wykorzystanie_percent"] > 0 else 0.0
    if nachylenie <= 0:
        return {"mozliwe": False, "obecnie": obecny}
    prog = obecny + wyniki["ogolem"]["wynik_przed_podatkiem"] / nachylenie
    if prog < 0:
        return {"mozliwe": False, "obecnie": obecny}
    return {"mozliwe": True, "obecnie": obecny, "prog": prog,
            "wymagana_redukcja": max(0.0, obecny - prog), "indeks_pracownika": indeks}
