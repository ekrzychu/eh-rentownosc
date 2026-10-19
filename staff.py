"""Jawna obsada projektu i rozłączne zasoby EH oraz ugód."""

from math import fsum, isfinite

from config import wczytaj_defaults

ROLE = ("EH", "UGODY")
ETYKIETY_ROL = {"EH": "Prawnik EH", "UGODY": "Prawnik ugody"}
GODZINY_ETATU_MIESIECZNIE = wczytaj_defaults()["organizacja"]["godziny_etatu_miesiecznie"]
CZYNNOSCI_DZIENNE = frozenset(wczytaj_defaults()["czynnosci_dzienne"])


def nowy_pracownik(indeks: int) -> dict:
    """Edytowalna inicjalizacja; stawka pochodzi wyłącznie z defaults.toml."""
    dane = wczytaj_defaults()
    role = dane["obsada"]["role_poczatkowe"]
    return {
        "rola": role[indeks] if indeks < len(role) else "EH",
        "stawka": dane["obsada"]["stawka_poczatkowa"],
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
    if set(czynnosci) - CZYNNOSCI_DZIENNE:
        raise ValueError("Nieznana rola czynności dziennej.")
    return {"EH": fsum(czynnosci.values()), "UGODY": 0.0}


def pojemnosc_obsady(pracownicy: list[dict], czynnosci: dict) -> dict:
    waliduj_obsade(pracownicy)
    wymagane = GODZINY_ETATU_MIESIECZNIE / 8 * minuty_dzienne_wedlug_roli(czynnosci)["EH"]
    wynik = {rola: {"brutto_minuty": 0.0, "dzienne_minuty": 0.0,
                    "netto_minuty": 0.0, "wynagrodzenia": 0.0,
                    "dzienne_wymagane_minuty": wymagane if rola == "EH" else 0.0,
                    "dzienne_niewykonane_minuty": 0.0,
                    "opiekun_dziennych": None,
                    "dodatnio_przydzieleni": 0} for rola in ROLE}
    kandydaci = []
    for indeks, osoba in enumerate(pracownicy):
        godziny = GODZINY_ETATU_MIESIECZNIE * osoba["wykorzystanie_percent"] / 100
        pula = wynik[osoba["rola"]]
        pula["brutto_minuty"] += godziny * 60
        pula["wynagrodzenia"] += godziny * osoba["stawka"]
        pula["dodatnio_przydzieleni"] += godziny > 0
        if osoba["rola"] == "EH" and godziny > 0:
            kandydaci.append((godziny * 60, -indeks))
    eh = wynik["EH"]
    if kandydaci and wymagane > 0:
        dostepne, ujemny_indeks = max(kandydaci)
        eh["opiekun_dziennych"] = -ujemny_indeks
        eh["dzienne_minuty"] = min(wymagane, dostepne)
    eh["dzienne_niewykonane_minuty"] = max(wymagane - eh["dzienne_minuty"], 0.0)
    for pula in wynik.values():
        pula["netto_minuty"] = max(pula["brutto_minuty"] - pula["dzienne_minuty"], 0.0)
    return wynik


def srednie_stawki_wedlug_roli(pracownicy: list[dict]) -> dict[str, float | None]:
    """Średnia arytmetyczna osób z dodatnim przydziałem, bez ważenia procentem."""
    waliduj_obsade(pracownicy)
    wynik = {}
    for rola in ROLE:
        stawki = [p["stawka"] for p in pracownicy
                  if p["rola"] == rola and p["wykorzystanie_percent"] > 0]
        wynik[rola] = fsum(stawki) / len(stawki) if stawki else None
    return wynik
