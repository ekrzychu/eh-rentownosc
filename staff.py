"""Jawna obsada projektu i rozłączne zasoby EH oraz ugód."""

from math import isfinite

from config import wczytaj_defaults

ROLE = ("EH", "UGODY")
ETYKIETY_ROL = {"EH": "Prawnik EH", "UGODY": "Prawnik ugody"}
GODZINY_ETATU_MIESIECZNIE = wczytaj_defaults()["organizacja"]["godziny_etatu_miesiecznie"]


def nowy_pracownik(indeks: int) -> dict:
    """Edytowalna inicjalizacja; stawka pochodzi wyłącznie z defaults.toml."""
    dane = wczytaj_defaults()
    role = dane["obsada"]["role_poczatkowe"]
    return {
        "rola": role[indeks] if indeks < len(role) else "EH",
        "stawka": dane["koszty"]["wynagrodzenie_pracownika_na_godzine"],
        "wykorzystanie_percent": dane["obsada"]["wykorzystanie_percent"],
    }


def przywroc_obsade(stan: dict, liczba: int) -> list[dict]:
    """Trwały magazyn niezależny od usuwanych przez Streamlit kluczy widgetów."""
    if not isinstance(liczba, int) or isinstance(liczba, bool) or liczba < 0:
        raise ValueError("Liczba pracowników musi być nieujemną liczbą całkowitą.")
    zapisane = dict(stan.get("ustawienia_obsady", {}))
    for indeks in range(liczba):
        zapisane.setdefault(indeks, nowy_pracownik(indeks))
    stan["ustawienia_obsady"] = zapisane
    return [dict(zapisane[indeks]) for indeks in range(liczba)]


def waliduj_obsade(pracownicy: list[dict]) -> None:
    if not isinstance(pracownicy, list):
        raise ValueError("Obsada musi być listą pracowników.")
    for i, osoba in enumerate(pracownicy, 1):
        if not isinstance(osoba, dict) or set(osoba) != {"rola", "stawka", "wykorzystanie_percent"}:
            raise ValueError(f"Niepełne ustawienia pracownika {i}.")
        if osoba["rola"] not in ROLE:
            raise ValueError(f"Nieznana rola pracownika {i}.")
        for pole in ("stawka", "wykorzystanie_percent"):
            v = osoba[pole]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or v < 0:
                raise ValueError(f"Niepoprawne {pole} pracownika {i}.")
        if osoba["wykorzystanie_percent"] > 100:
            raise ValueError(f"Wykorzystanie pracownika {i} przekracza 100%.")


def minuty_dzienne_wedlug_roli(czynnosci: dict) -> dict:
    role = {
        "Obsługa skrzynki ugody EH": "UGODY",
        "Komunikacja z EH i zlecanie opłat w SOSS": "EH",
        "Umieszczanie dokumentów w SOSS": "EH",
    }
    if set(czynnosci) - set(role):
        raise ValueError("Nieznana rola czynności dziennej.")
    return {rola: sum(v for k, v in czynnosci.items() if role[k] == rola) for rola in ROLE}


def pojemnosc_obsady(pracownicy: list[dict], czynnosci: dict) -> dict:
    waliduj_obsade(pracownicy)
    dzienne = minuty_dzienne_wedlug_roli(czynnosci)
    wynik = {rola: {"brutto_minuty": 0.0, "dzienne_minuty": 0.0,
                    "netto_minuty": 0.0, "wynagrodzenia": 0.0} for rola in ROLE}
    for osoba in pracownicy:
        godziny = GODZINY_ETATU_MIESIECZNIE * osoba["wykorzystanie_percent"] / 100
        dzienne_minuty = godziny / 8 * dzienne[osoba["rola"]]
        pula = wynik[osoba["rola"]]
        pula["brutto_minuty"] += godziny * 60
        pula["dzienne_minuty"] += dzienne_minuty
        pula["netto_minuty"] += max(godziny * 60 - dzienne_minuty, 0.0)
        pula["wynagrodzenia"] += godziny * osoba["stawka"]
    return wynik
