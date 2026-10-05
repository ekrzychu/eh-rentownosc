"""Jawne mapowanie referencyjnych danych TOML; matematyka pozostaje w modelach."""

from math import isfinite
from pathlib import Path
import tomllib


DEFAULTS_PATH = Path(__file__).resolve().with_name("defaults.toml")

# Wymagane nazwy, bez kopii wartości referencyjnych.
WYMAGANE = {
    "metadata": (
        "version",
        "description",
    ),
    "portfolio": (
        "liczba_spraw",
        "prog_wps",
        "niski_wps",
        "wysoki_wps",
        "wysoki_wps_procent",
    ),
    "rodzaje_spraw": (
        "P1_percent",
        "P2_percent",
        "P3_percent",
    ),
    "przychod": (
        "srednia_kwota_ugody_percent",
        "srednia_kwota_wyroku_percent",
        "podatek_dochodowy_percent",
    ),
    "ugody": (
        "kategoryczna_odmowa_percent",
        "automatyczne_ramy_percent",
        "skutecznosc_automatycznych_ram_percent",
        "szansa_na_ugode_percent",
        "zawarte_ugody_percent",
    ),
    "ii_instancja": (
        "udzial_percent",
        "obsluga_minuty",
    ),
    "koszty": (
        "narzut_kosztow_ogolnych_na_godzine",
        "wynagrodzenie_pracownika_na_godzine",
    ),
    "organizacja": (
        "liczba_pracownikow",
        "godziny_etatu_miesiecznie",
        "minuty_dnia_pracy",
    ),
    "czas_dodatkowy": (
        "P1",
        "P2",
        "P3",
    ),
    "czynnosci_wspolne": (
        "Analiza sprawy i kompletowanie załącznika",
    ),
    "czynnosci_procesowe": (
        "Wniosek o wideo",
        "Duplika",
        "Pytania do świadków",
        "Rozprawa",
        "Notatka z rozprawy",
        "Wyrok",
    ),
    "czynnosci_ugodowe": (
        "Oferta ugody",
        "Projekt ugody",
        "Podpisanie ugody",
    ),
    "pozostale_czasy": (
        "analiza_mozliwosci_ugody",
    ),
    "czynnosci_dzienne": (
        "Obsługa skrzynki ugody EH",
        "Komunikacja z EH i zlecanie opłat w SOSS",
        "Umieszczanie dokumentów w SOSS",
    ),
    "timeline": (
        "miesiace_do_ugody",
        "miesiace_do_wyroku_i",
        "miesiace_wyrok_i_do_ii",
        "opoznienie_platnosci_miesiace",
        "horyzont_miesiace",
    ),
}


def wczytaj_defaults() -> dict:
    """Czyta świeże słowniki i zgłasza błędy wraz ze ścieżką konfiguracji."""
    try:
        with DEFAULTS_PATH.open("rb") as plik:
            dane = tomllib.load(plik)
    except (OSError, tomllib.TOMLDecodeError) as blad:
        raise ValueError(f"Nie można wczytać konfiguracji {DEFAULTS_PATH}: {blad}") from blad
    for sekcja, klucze in WYMAGANE.items():
        tabela = dane.get(sekcja)
        if not isinstance(tabela, dict):
            raise ValueError(f"{DEFAULTS_PATH}: brak tabeli [{sekcja}].")
        for klucz in klucze:
            if klucz not in tabela:
                raise ValueError(f"{DEFAULTS_PATH}: brak {sekcja}.{klucz}.")
            wartosc = tabela[klucz]
            if sekcja == "metadata":
                poprawna = isinstance(wartosc, str) and bool(wartosc.strip())
            else:
                poprawna = (
                    isinstance(wartosc, (int, float))
                    and not isinstance(wartosc, bool)
                    and isfinite(wartosc)
                    and wartosc >= 0
                )
                if klucz.endswith("percent") or klucz == "wysoki_wps_procent":
                    poprawna = poprawna and wartosc <= 100
                if sekcja == "timeline" or klucz in {"liczba_spraw", "liczba_pracownikow"}:
                    poprawna = poprawna and isinstance(wartosc, int)
                if klucz in {"prog_wps", "godziny_etatu_miesiecznie", "minuty_dnia_pracy", "horyzont_miesiace"}:
                    poprawna = poprawna and wartosc > 0
            if not poprawna:
                raise ValueError(f"{DEFAULTS_PATH}: niepoprawna wartość {sekcja}.{klucz}.")
    return dane


def parametry_modelu() -> dict:
    """Zachowuje dotychczasowy format publicznych parametrów lifecycle."""
    dane = wczytaj_defaults()
    return {
        "liczba_spraw": dane["portfolio"]["liczba_spraw"],
        "prog_wps": dane["portfolio"]["prog_wps"],
        "niski_wps": dane["portfolio"]["niski_wps"],
        "wysoki_wps": dane["portfolio"]["wysoki_wps"],
        "koszt_staly_na_godzine": dane["koszty"]["narzut_kosztow_ogolnych_na_godzine"],
        "wynagrodzenie_pracownika_na_godzine": dane["koszty"]["wynagrodzenie_pracownika_na_godzine"],
        "wspolne_czynnosci": dane["czynnosci_wspolne"],
        "procesowe_czynnosci": dane["czynnosci_procesowe"],
        "ugodowe_czynnosci": dane["czynnosci_ugodowe"],
        "analiza_mozliwosci_ugody": dane["pozostale_czasy"]["analiza_mozliwosci_ugody"],
        "codzienne_czynnosci": dane["czynnosci_dzienne"],
        "dodatkowe_minuty": dane["czas_dodatkowy"],
        "udzialy_rodzajow": {rodzaj: dane["rodzaje_spraw"][rodzaj + "_percent"] for rodzaj in ("P1", "P2", "P3")},
        "wysoki_wps_procent": dane["portfolio"]["wysoki_wps_procent"],
        **dane["przychod"],
        **dane["ugody"],
        "udzial_ii_instancji_percent": dane["ii_instancja"]["udzial_percent"],
        "obsluga_ii_instancji_minuty": dane["ii_instancja"]["obsluga_minuty"],
        "liczba_pracownikow": dane["organizacja"]["liczba_pracownikow"],
    }
