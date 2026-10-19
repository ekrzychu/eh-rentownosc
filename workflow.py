"""Wspólna definicja pracy sześciu ścieżek; bez kosztów i kalendarza.

Minuty dotyczą jednej sprawy. Etap zerowy nadal wymaga wskazanej roli.
Czas P przypada na przygotowanie EH, również w sprawach ugodowych.
"""

from dataclasses import dataclass


SCIEZKI_UGODOWE = ("automatyczne_ramy_ugoda", "zawarte_poza_ramami")
SCIEZKI_BEZ_UGODY = (
    "kategoryczna_odmowa", "automatyczne_ramy_brak_ugody",
    "brak_szans", "brak_ugody_poza_ramami",
)
SCIEZKI_PROBY = ("automatyczne_ramy_brak_ugody", "brak_ugody_poza_ramami")


@dataclass(frozen=True)
class Etap:
    nazwa: str
    rola: str
    minuty: float
    zegar: str | None = None


def etapy_sprawy(p: dict, sciezka: str, dodatkowe: float = 0,
                 druga_instancja: bool = False) -> tuple[Etap, ...]:
    if sciezka not in SCIEZKI_UGODOWE + SCIEZKI_BEZ_UGODY:
        raise ValueError("Nieznana ścieżka sprawy.")
    analiza = p["analiza_mozliwosci_ugody"]
    przygotowanie = sum(p["wspolne_czynnosci"].values()) + dodatkowe
    if sciezka == "brak_szans":
        przygotowanie += analiza
    etapy = [Etap("przyjecie", "EH", przygotowanie)]
    if sciezka in SCIEZKI_UGODOWE:
        ugody = sum(p["ugodowe_czynnosci"].values())
        if sciezka == "zawarte_poza_ramami":
            ugody += analiza
        etapy.append(Etap("ugoda", "UGODY", ugody, "ugoda"))
    else:
        if sciezka in SCIEZKI_PROBY:
            proba = sum(p["ugodowe_czynnosci"].get(k, 0)
                        for k in ("Oferta ugody", "Projekt ugody"))
            if sciezka == "brak_ugody_poza_ramami":
                proba += analiza
            etapy.append(Etap("proba_ugody", "UGODY", proba))
        etapy.append(Etap("proces", "EH", sum(p["procesowe_czynnosci"].values()), "i"))
        if druga_instancja:
            etapy.append(Etap("ii_instancja", "EH", p["obsluga_ii_instancji_minuty"], "ii"))
    return tuple(etapy)
