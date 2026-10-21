"""Wspólne stawki kosztów i jawna migracja dawnego API sprawomiesięcy."""

from math import isfinite


LEGACY_COST_KEYS = frozenset({"ogolne_na_aktywna_sprawe", "sekretariat_na_aktywna_sprawe"})


def sprawdz_stare_koszty(koszty: dict | None) -> None:
    """Dopuszcza wyłącznie puste/zerowe stare ustawienia, bez dodatkowej opłaty."""
    if koszty is None:
        return
    if not isinstance(koszty, dict) or set(koszty) - LEGACY_COST_KEYS:
        raise ValueError("Nieznane koszty kontraktu.")
    for nazwa, wartosc in koszty.items():
        if (isinstance(wartosc, bool) or not isinstance(wartosc, (int, float))
                or not isfinite(wartosc) or wartosc != 0):
            raise ValueError(
                f"Wycofany koszt {nazwa}: koszty za sprawomiesiąc nie są obsługiwane. "
                "Użyj wspólnych parametrów koszt_staly_na_godzine, "
                "sekretariat_minuty_na_sprawe i koszt_sekretariatu_na_godzine."
            )


def wspolne_stawki(parametry: dict) -> dict:
    """Parametry są walidowane przez model; brak niezależnych stawek Panelu 2."""
    return {
        "general_overhead_per_hour": parametry["koszt_staly_na_godzine"],
        "secretariat_cost_per_case": (
            parametry["sekretariat_minuty_na_sprawe"] / 60
            * parametry["koszt_sekretariatu_na_godzine"]
        ),
    }
