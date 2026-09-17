"""Czasowy rozkład ekonomii lifecycle portfela.

Moduł nie definiuje osobnej ekonomii spraw. Pobiera skład portfela,
wynagrodzenia, udziały ścieżek oraz koszt godziny z ``oblicz_model`` i
wyłącznie przypisuje te wartości do miesięcy.
"""

from collections import defaultdict
from math import isclose

from model import MINUTY_DNIA_PRACY, oblicz_model


SCIEZKI_UGODOWE = ("automatyczne_ramy", "zawarte_poza_ramami")
SCIEZKI_BEZ_UGODY = (
    "kategoryczna_odmowa",
    "brak_szans",
    "brak_ugody_poza_ramami",
)


def domyslne_parametry_czasowe() -> dict:
    """Zwraca edytowalne, testowe założenia kalendarza miesięcznego."""
    return {
        "tryb_naplywu": "równomiernie",
        "okres_naplywu_miesiace": 12,
        "miesiace_do_ugody": 6,
        "miesiace_do_wyroku_i": 9,
        "miesiace_wyrok_i_do_ii": 6,
        "opoznienie_platnosci_miesiace": 0,
        "horyzont_miesiace": 36,
    }


def _znormalizuj_tryb(tryb: str) -> str:
    if not isinstance(tryb, str):
        raise ValueError("Sposób napływu spraw musi być tekstem.")
    wartosc = tryb.strip().casefold().replace("_", " ")
    if wartosc == "równomiernie":
        return "równomiernie"
    if wartosc in {"wszystkie na początku", "wszystkie na poczatku"}:
        return "wszystkie na początku"
    raise ValueError(
        "Sposób napływu musi mieć wartość 'równomiernie' "
        "albo 'wszystkie na początku'."
    )


def _parametry_czasowe(parametry_czasowe: dict | None) -> dict:
    wynik = domyslne_parametry_czasowe()
    if parametry_czasowe:
        wynik.update(parametry_czasowe)
    wynik["tryb_naplywu"] = _znormalizuj_tryb(wynik["tryb_naplywu"])

    nieujemne = (
        "miesiace_do_ugody",
        "miesiace_do_wyroku_i",
        "miesiace_wyrok_i_do_ii",
        "opoznienie_platnosci_miesiace",
    )
    for nazwa in nieujemne:
        if not isinstance(wynik[nazwa], int) or isinstance(wynik[nazwa], bool):
            raise ValueError(f"Parametr {nazwa} musi być liczbą całkowitą.")
        if wynik[nazwa] < 0:
            raise ValueError(f"Parametr {nazwa} nie może być ujemny.")
    for nazwa in ("okres_naplywu_miesiace", "horyzont_miesiace"):
        if not isinstance(wynik[nazwa], int) or isinstance(wynik[nazwa], bool):
            raise ValueError(f"Parametr {nazwa} musi być liczbą całkowitą.")
        if wynik[nazwa] < 1:
            raise ValueError(f"Parametr {nazwa} musi wynosić co najmniej 1.")
    return wynik


def rozloz_naplyw(liczba_spraw: float, tryb: str, okres_miesiace: int) -> list[float]:
    """Rozkłada istniejący wolumen portfela na miesiące wpływu."""
    if liczba_spraw < 0:
        raise ValueError("Liczba spraw nie może być ujemna.")
    if not isinstance(okres_miesiace, int) or okres_miesiace < 1:
        raise ValueError("Okres napływu musi być dodatnią liczbą całkowitą.")
    tryb = _znormalizuj_tryb(tryb)
    if tryb == "wszystkie na początku":
        return [float(liczba_spraw)]
    miesiecznie = liczba_spraw / okres_miesiace
    return [miesiecznie] * okres_miesiace


def wyznacz_break_even(
    wyniki_skumulowane: list[float], miesiace: list[int] | None = None
) -> dict:
    """Wyznacza pierwsze wyjście z deficytu, ignorując początkowe zero."""
    if miesiace is None:
        miesiace = list(range(len(wyniki_skumulowane)))
    if len(miesiace) != len(wyniki_skumulowane):
        raise ValueError("Lista miesięcy musi odpowiadać liście wyników.")

    byl_deficyt = False
    for miesiac, wynik in zip(miesiace, wyniki_skumulowane):
        if wynik < -1e-9:
            byl_deficyt = True
        elif byl_deficyt and wynik >= -1e-9:
            return {"status": "osiagniety", "miesiac": miesiac, "etykieta": f"Miesiąc {miesiac}"}
    if byl_deficyt:
        return {
            "status": "nie_osiagnieto",
            "miesiac": None,
            "etykieta": "Nie osiągnięto w horyzoncie",
        }
    return {"status": "od_poczatku", "miesiac": None, "etykieta": "Od początku"}


def _dodaj(zdarzenia: dict, miesiac: int, nazwa: str, wartosc: float) -> None:
    zdarzenia[miesiac][nazwa] += wartosc


def _rozloz_rowno(
    zdarzenia: dict, poczatek: int, koniec: int, nazwa: str, wartosc: float
) -> None:
    liczba_miesiecy = koniec - poczatek + 1
    if liczba_miesiecy <= 0:
        raise ValueError("Nieprawidłowy przedział alokacji czasu.")
    czesc = wartosc / liczba_miesiecy
    for miesiac in range(poczatek, koniec + 1):
        _dodaj(zdarzenia, miesiac, nazwa, czesc)


def _wiersze_miesieczne(
    zdarzenia: dict, ostatni_miesiac: int, koszt_godziny: float, narzut_dzienny: float
) -> list[dict]:
    wiersze = []
    skumulowany = 0.0
    for miesiac in range(ostatni_miesiac + 1):
        dane = zdarzenia[miesiac]
        minuty_bezposrednie = dane["bezposrednie_minuty"]
        minuty_dzienne = minuty_bezposrednie / MINUTY_DNIA_PRACY * narzut_dzienny
        koszt = (minuty_bezposrednie + minuty_dzienne) / 60 * koszt_godziny
        przychod_ugody = dane["przychod_ugody"]
        przychod_wyroki = dane["przychod_wyroki"]
        przychod = przychod_ugody + przychod_wyroki
        wynik = przychod - koszt
        skumulowany += wynik
        wiersze.append(
            {
                "Miesiąc": miesiac,
                "Nowe sprawy": dane["nowe_sprawy"],
                "Ugody": dane["ugody"],
                "Zakończenia po I instancji": dane["zakonczenia_i"],
                "Zakończenia po II instancji": dane["zakonczenia_ii"],
                "Przychód z ugód": przychod_ugody,
                "Przychód z wyroków": przychod_wyroki,
                "Przychód razem": przychod,
                "Bezpośrednie minuty pracy": minuty_bezposrednie,
                "Minuty czynności dziennych": minuty_dzienne,
                "Bezpośrednie godziny pracy": minuty_bezposrednie / 60,
                "Godziny czynności dziennych": minuty_dzienne / 60,
                "Koszt": koszt,
                "Wynik miesięczny": wynik,
                "Wynik skumulowany": skumulowany,
            }
        )
    return wiersze


def _suma(wiersze: list[dict], klucz: str) -> float:
    return sum(wiersz[klucz] for wiersz in wiersze)


def _sprawdz_uzgodnienie(nazwa: str, czasowe: float, lifecycle: float) -> None:
    if not isclose(czasowe, lifecycle, rel_tol=1e-10, abs_tol=1e-6):
        raise RuntimeError(
            f"Model czasowy nie uzgadnia {nazwa}: {czasowe} zamiast {lifecycle}."
        )


def oblicz_model_czasowy(
    parametry: dict | None = None, parametry_czasowe: dict | None = None
) -> dict:
    """Rozkłada kanoniczną ekonomię lifecycle na miesiące.

    Pełny harmonogram służy do obowiązkowych uzgodnień, natomiast
    ``tabela_miesieczna`` jest przycięta lub dopełniona do horyzontu UI.
    Podatek i payroll nie są elementem tego rozkładu.
    """
    czas = _parametry_czasowe(parametry_czasowe)
    lifecycle = oblicz_model(parametry)
    if parametry is None:
        # oblicz_model użył swoich aktualnych wartości domyślnych; parametry
        # potrzebne niżej są dostępne w wynikach lub strukturze grup.
        from model import domyslne_parametry

        parametry = domyslne_parametry()

    liczba_spraw = lifecycle["ogolem"]["liczba_spraw"]
    naplyw = rozloz_naplyw(
        liczba_spraw, czas["tryb_naplywu"], czas["okres_naplywu_miesiace"]
    )
    udzialy_sciezek = lifecycle["udzialy_ugod"]
    udzial_ii = parametry["udzial_ii_instancji_percent"] / 100
    wspolne_minuty = sum(parametry["wspolne_czynnosci"].values())
    procesowe_minuty = sum(parametry["procesowe_czynnosci"].values())
    analiza_minuty = parametry["analiza_mozliwosci_ugody"]
    ugodowe_minuty = sum(parametry["ugodowe_czynnosci"].values())
    przygotowanie_ugody_minuty = (
        parametry["ugodowe_czynnosci"].get("Oferta ugody", 0)
        + parametry["ugodowe_czynnosci"].get("Projekt ugody", 0)
    )
    minuty_ii = parametry["obsluga_ii_instancji_minuty"]

    zdarzenia = defaultdict(lambda: defaultdict(float))
    przychod_rodzaje = defaultdict(float)
    przychod_wps = defaultdict(float)
    ostatni_miesiac = 0

    for miesiac_wplywu, nowe_sprawy in enumerate(naplyw):
        _dodaj(zdarzenia, miesiac_wplywu, "nowe_sprawy", nowe_sprawy)
        if liczba_spraw == 0:
            continue
        udzial_kohorty = nowe_sprawy / liczba_spraw
        for grupa in lifecycle["grupy"]:
            liczba_grupy = grupa["liczba"] * udzial_kohorty
            minuty_p = parametry["dodatkowe_minuty"][grupa["rodzaj"]]

            for sciezka in SCIEZKI_UGODOWE:
                liczba = liczba_grupy * udzialy_sciezek[sciezka] / 100
                koniec = miesiac_wplywu + czas["miesiace_do_ugody"]
                platnosc = koniec + czas["opoznienie_platnosci_miesiace"]
                _dodaj(zdarzenia, koniec, "ugody", liczba)
                przychod = liczba * grupa["wynagrodzenie_ugoda"]
                _dodaj(zdarzenia, platnosc, "przychod_ugody", przychod)
                przychod_rodzaje[grupa["rodzaj"]] += przychod
                przychod_wps[grupa["grupa_wps"]] += przychod
                _dodaj(
                    zdarzenia,
                    miesiac_wplywu,
                    "bezposrednie_minuty",
                    liczba * wspolne_minuty,
                )
                if sciezka == "zawarte_poza_ramami":
                    _dodaj(
                        zdarzenia,
                        miesiac_wplywu,
                        "bezposrednie_minuty",
                        liczba * analiza_minuty,
                    )
                _dodaj(
                    zdarzenia, koniec, "bezposrednie_minuty", liczba * ugodowe_minuty
                )
                _rozloz_rowno(
                    zdarzenia,
                    miesiac_wplywu,
                    koniec,
                    "bezposrednie_minuty",
                    liczba * minuty_p,
                )
                ostatni_miesiac = max(ostatni_miesiac, koniec, platnosc)

            for sciezka in SCIEZKI_BEZ_UGODY:
                liczba_sciezki = liczba_grupy * udzialy_sciezek[sciezka] / 100
                for czy_ii, liczba in (
                    (False, liczba_sciezki * (1 - udzial_ii)),
                    (True, liczba_sciezki * udzial_ii),
                ):
                    wyrok_i = miesiac_wplywu + czas["miesiace_do_wyroku_i"]
                    koniec = wyrok_i + (czas["miesiace_wyrok_i_do_ii"] if czy_ii else 0)
                    platnosc = koniec + czas["opoznienie_platnosci_miesiace"]
                    _dodaj(
                        zdarzenia,
                        koniec,
                        "zakonczenia_ii" if czy_ii else "zakonczenia_i",
                        liczba,
                    )
                    przychod = liczba * grupa["wynagrodzenie_wyrok"]
                    _dodaj(zdarzenia, platnosc, "przychod_wyroki", przychod)
                    przychod_rodzaje[grupa["rodzaj"]] += przychod
                    przychod_wps[grupa["grupa_wps"]] += przychod

                    _dodaj(
                        zdarzenia,
                        miesiac_wplywu,
                        "bezposrednie_minuty",
                        liczba * wspolne_minuty,
                    )
                    if sciezka in {"brak_szans", "brak_ugody_poza_ramami"}:
                        _dodaj(
                            zdarzenia,
                            miesiac_wplywu,
                            "bezposrednie_minuty",
                            liczba * analiza_minuty,
                        )
                    if sciezka == "brak_ugody_poza_ramami":
                        proba_ugody = min(
                            miesiac_wplywu + czas["miesiace_do_ugody"], wyrok_i
                        )
                        _dodaj(
                            zdarzenia,
                            proba_ugody,
                            "bezposrednie_minuty",
                            liczba * przygotowanie_ugody_minuty,
                        )
                    if czas["miesiace_do_wyroku_i"] > 0:
                        proces_od = miesiac_wplywu + 1
                    else:
                        proces_od = wyrok_i
                    _rozloz_rowno(
                        zdarzenia,
                        proces_od,
                        wyrok_i,
                        "bezposrednie_minuty",
                        liczba * procesowe_minuty,
                    )
                    _rozloz_rowno(
                        zdarzenia,
                        miesiac_wplywu,
                        koniec,
                        "bezposrednie_minuty",
                        liczba * minuty_p,
                    )
                    if czy_ii:
                        ii_od = wyrok_i + 1 if czas["miesiace_wyrok_i_do_ii"] > 0 else wyrok_i
                        _rozloz_rowno(
                            zdarzenia,
                            ii_od,
                            koniec,
                            "bezposrednie_minuty",
                            liczba * minuty_ii,
                        )
                    ostatni_miesiac = max(ostatni_miesiac, koniec, platnosc)

    narzut_dzienny = sum(parametry["codzienne_czynnosci"].values())
    pelna_tabela = _wiersze_miesieczne(
        zdarzenia, ostatni_miesiac, lifecycle["koszt_godziny"], narzut_dzienny
    )
    tabela_w_horyzoncie = _wiersze_miesieczne(
        zdarzenia,
        czas["horyzont_miesiace"] - 1,
        lifecycle["koszt_godziny"],
        narzut_dzienny,
    )

    pelny_przychod = _suma(pelna_tabela, "Przychód razem")
    pelny_koszt = _suma(pelna_tabela, "Koszt")
    pelne_minuty = _suma(pelna_tabela, "Bezpośrednie minuty pracy")
    pelne_minuty_dzienne = _suma(pelna_tabela, "Minuty czynności dziennych")
    liczba_ugod = _suma(pelna_tabela, "Ugody")
    liczba_i = _suma(pelna_tabela, "Zakończenia po I instancji")
    liczba_ii = _suma(pelna_tabela, "Zakończenia po II instancji")

    _sprawdz_uzgodnienie("przychodu", pelny_przychod, lifecycle["ogolem"]["przychod"])
    _sprawdz_uzgodnienie(
        "przychodu z ugód",
        _suma(pelna_tabela, "Przychód z ugód"),
        lifecycle["ogolem"]["przychod_ugody"],
    )
    _sprawdz_uzgodnienie(
        "przychodu z wyroków",
        _suma(pelna_tabela, "Przychód z wyroków"),
        lifecycle["ogolem"]["przychod_wyroki"],
    )
    _sprawdz_uzgodnienie("czasu bezpośredniego", pelne_minuty, lifecycle["bezposrednie_minuty_spraw"])
    _sprawdz_uzgodnienie(
        "czasu czynności dziennych",
        pelne_minuty_dzienne,
        lifecycle["czynnosci_dzienne_lifecycle_minuty"],
    )
    _sprawdz_uzgodnienie("kosztu", pelny_koszt, lifecycle["ogolem"]["koszt"])
    _sprawdz_uzgodnienie("liczby zakończeń", liczba_ugod + liczba_i + liczba_ii, liczba_spraw)
    _sprawdz_uzgodnienie(
        "liczby spraw w II instancji",
        liczba_ii,
        lifecycle["oczekiwana_liczba_spraw_ii_instancji"],
    )
    for rodzaj, podsumowanie in lifecycle["rodzaje"].items():
        _sprawdz_uzgodnienie(
            f"przychodu {rodzaj}", przychod_rodzaje[rodzaj], podsumowanie["przychod"]
        )
    for grupa_wps, klucz in (("niski_wps", "wps_niski"), ("wysoki_wps", "wps_wysoki")):
        _sprawdz_uzgodnienie(
            f"przychodu {grupa_wps}", przychod_wps[grupa_wps], lifecycle[klucz]["przychod"]
        )

    przychod_w_horyzoncie = _suma(tabela_w_horyzoncie, "Przychód razem")
    koszt_w_horyzoncie = _suma(tabela_w_horyzoncie, "Koszt")
    pozostaly_przychod = pelny_przychod - przychod_w_horyzoncie
    pozostaly_koszt = pelny_koszt - koszt_w_horyzoncie
    udzial_przychodu = (
        przychod_w_horyzoncie / pelny_przychod * 100 if pelny_przychod else 100.0
    )
    break_even = wyznacz_break_even(
        [wiersz["Wynik skumulowany"] for wiersz in tabela_w_horyzoncie],
        [wiersz["Miesiąc"] for wiersz in tabela_w_horyzoncie],
    )
    dodatni = next(
        (wiersz["Miesiąc"] for wiersz in tabela_w_horyzoncie if wiersz["Wynik miesięczny"] > 1e-9),
        None,
    )
    najglebszy = min(tabela_w_horyzoncie, key=lambda wiersz: wiersz["Wynik skumulowany"])
    koncowy = tabela_w_horyzoncie[-1]["Wynik skumulowany"]
    pelny_w_horyzoncie = isclose(pozostaly_przychod, 0.0, abs_tol=1e-6) and isclose(
        pozostaly_koszt, 0.0, abs_tol=1e-6
    )

    return {
        "parametry_czasowe": czas,
        "tabela_miesieczna": tabela_w_horyzoncie,
        "pelna_tabela_miesieczna": pelna_tabela,
        "ostatni_miesiac_pelnego_cyklu": ostatni_miesiac,
        "kpi": {
            "break_even_skumulowany": break_even["etykieta"],
            "break_even_status": break_even["status"],
            "break_even_miesiac": break_even["miesiac"],
            "pierwszy_dodatni_miesiac": dodatni,
            "najglebszy_deficyt_skumulowany": najglebszy["Wynik skumulowany"],
            "miesiac_najglebszego_deficytu": najglebszy["Miesiąc"],
            "wynik_skumulowany_na_koniec_horyzontu": koncowy,
            "udzial_przychodu_lifecycle_w_horyzoncie": udzial_przychodu,
        },
        "podsumowanie": {
            "przychod_pelny": pelny_przychod,
            "koszt_pelny": pelny_koszt,
            "przychod_w_horyzoncie": przychod_w_horyzoncie,
            "koszt_w_horyzoncie": koszt_w_horyzoncie,
            "pozostaly_przychod": pozostaly_przychod,
            "pozostaly_koszt": pozostaly_koszt,
            "pelny_cykl_w_horyzoncie": pelny_w_horyzoncie,
            "liczba_ugod": liczba_ugod,
            "liczba_zakonczen_i": liczba_i,
            "liczba_zakonczen_ii": liczba_ii,
        },
        "uzgodnienie": {
            "przychod_czasowy": pelny_przychod,
            "przychod_lifecycle": lifecycle["ogolem"]["przychod"],
            "przychod_ugody_czasowy": _suma(pelna_tabela, "Przychód z ugód"),
            "przychod_wyroki_czasowy": _suma(pelna_tabela, "Przychód z wyroków"),
            "bezposrednie_minuty_czasowe": pelne_minuty,
            "bezposrednie_minuty_lifecycle": lifecycle["bezposrednie_minuty_spraw"],
            "czynnosci_dzienne_minuty_czasowe": pelne_minuty_dzienne,
            "czynnosci_dzienne_minuty_lifecycle": lifecycle["czynnosci_dzienne_lifecycle_minuty"],
            "koszt_czasowy": pelny_koszt,
            "koszt_lifecycle": lifecycle["ogolem"]["koszt"],
            "przychod_wedlug_rodzaju": dict(przychod_rodzaje),
            "przychod_wedlug_wps": dict(przychod_wps),
        },
    }
