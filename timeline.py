"""Model pracy FIFO, formalnych zegarów i płatności w czasie.

``oblicz_przeplyw`` jest wspólnym źródłem oczekiwanej pracy i przychodu
kohorty referencyjnej, bez wyceny lifecycle. Harmonogram zachowuje tożsamość
ważonych spraw, rozłączne role i zależności etapów. Koszt okresowy
nie jest zatem uzgadniany z kosztem pracy zużytej przez pojedynczą kohortę.
"""

from collections import defaultdict
from heapq import heappush, heappop
from dataclasses import dataclass, field
from functools import lru_cache
from workflow import Etap, etapy_sprawy
from math import fsum, isclose, isfinite

from config import wczytaj_defaults
from staff import GODZINY_ETATU_MIESIECZNIE, ROLE, pojemnosc_obsady

from model import (
    SCIEZKI_BEZ_UGODY,
    SCIEZKI_UGODOWE,
    domyslne_parametry,
    oblicz_przeplyw,
    waliduj_parametry,
)


TOLERANCJA = 1e-8


@lru_cache(maxsize=1024)
def _plan_minut(etapy: tuple[Etap, ...]) -> tuple:
    """Wspólne sumy odcinków na jedną sprawę, liczone raz dla danego planu.

    Kolejność pól: przyszłe EH, przyszłe UGODY, dalszy bieżący odcinek,
    przyszła II instancja. Wagi i pozostała praca należą do konkretnej sprawy.
    """
    wynik = []
    for indeks, etap in enumerate(etapy):
        dalsze = etapy[indeks + 1:]
        odcinek = []
        poprzedni = etap
        for nastepny in dalsze:
            if poprzedni.zegar or nastepny.rola != etap.rola:
                break
            odcinek.append(nastepny.minuty)
            poprzedni = nastepny
        wynik.append((fsum(e.minuty for e in dalsze if e.rola == "EH"),
                      fsum(e.minuty for e in dalsze if e.rola == "UGODY"),
                      fsum(odcinek),
                      fsum(e.minuty for e in dalsze if e.nazwa == "ii_instancja")))
    return tuple(wynik)


@dataclass
class Sprawa:
    """Stała tożsamość reprezentanta o wadze (0, 1], bez zaokrąglania portfela.

    Waga oznacza oczekiwaną liczbę identycznych spraw. Częściowa praca
    zmniejsza pozostałe minuty tego samego reprezentanta, nigdy jego wagę.
    """
    identyfikator: int
    wplyw: int
    sciezka: str
    wynik: str
    waga: float
    przychod: float
    etapy: tuple[Etap, ...]
    indeks: int = 0
    pozostale: float = 0.0
    dostepna_od: int = 1
    starty: dict = field(default_factory=dict)
    konce_pracy: dict = field(default_factory=dict)
    termin: int | None = None
    plan: tuple = field(init=False, repr=False)

    def __post_init__(self):
        self.plan = _plan_minut(self.etapy)

    @property
    def etap(self):
        return self.etapy[self.indeks]

    def przyszle_minuty(self, rola):
        return self.plan[self.indeks][0 if rola == "EH" else 1] * self.waga

    def minuty_kolejki(self):
        """Cały bieżący odcinek jednej roli, do zmiany roli lub wyniku formalnego.

        Przyjęcie i bezpośredni proces tworzą jedną kolejkę EH. Ich kolejność
        wykonania i inicjacja zegara pozostają odrębnymi zdarzeniami.
        """
        return self.pozostale + self.plan[self.indeks][2] * self.waga


def domyslne_parametry_czasowe() -> dict:
    """Zwraca referencyjne założenia procesu dla ciągłej symulacji."""
    return wczytaj_defaults()["timeline"]


def _parametry_czasowe(parametry_czasowe: dict | None) -> dict:
    wynik = domyslne_parametry_czasowe()
    if parametry_czasowe:
        nieznane = set(parametry_czasowe) - set(wynik)
        if nieznane:
            raise ValueError(
                "Nieznane parametry czasowe: " + ", ".join(sorted(nieznane))
            )
        wynik.update(parametry_czasowe)
    for nazwa, wartosc in wynik.items():
        if not isinstance(wartosc, int) or isinstance(wartosc, bool):
            raise ValueError(f"Parametr {nazwa} musi być liczbą całkowitą.")
        minimum = 1 if nazwa == "horyzont_miesiace" else 0
        if wartosc < minimum:
            raise ValueError(f"Parametr {nazwa} musi wynosić co najmniej {minimum}.")
    return wynik


def miesieczny_naplyw(liczba_spraw_rocznie: float) -> float:
    """Zwraca stały oczekiwany napływ w każdym miesiącu."""
    if liczba_spraw_rocznie < 0:
        raise ValueError("Roczny napływ spraw nie może być ujemny.")
    return liczba_spraw_rocznie / 12


def wyznacz_break_even(
    wyniki_skumulowane: list[float], miesiace: list[int] | None = None
) -> dict:
    """Wskazuje pierwszy powrót z deficytu do co najmniej zera."""
    if miesiace is None:
        miesiace = list(range(1, len(wyniki_skumulowane) + 1))
    if len(miesiace) != len(wyniki_skumulowane):
        raise ValueError("Lista miesięcy musi odpowiadać liście wyników.")
    byl_deficyt = False
    for miesiac, wynik in zip(miesiace, wyniki_skumulowane):
        if miesiac <= 0:
            continue
        if wynik < -TOLERANCJA:
            byl_deficyt = True
        elif byl_deficyt and wynik >= -TOLERANCJA:
            return {
                "status": "osiagniety",
                "miesiac": miesiac,
                "etykieta": f"Miesiąc {miesiac}",
            }
    if byl_deficyt:
        return {
            "status": "nie_osiagnieto",
            "miesiac": None,
            "etykieta": "Nie osiągnięto w horyzoncie",
        }
    return {"status": "od_poczatku", "miesiac": None, "etykieta": "Od początku"}


def wyznacz_trwaly_break_even(
    wyniki_skumulowane: list[float],
    miesiace: list[int],
    status_pojemnosci: str,
    wynik_miesieczny_w_stanie_stabilnym: float | None,
) -> dict:
    """Wskazuje przecięcie, po którym wynik nie wraca pod zero i jest trwały."""
    if len(miesiace) != len(wyniki_skumulowane):
        raise ValueError("Lista miesięcy musi odpowiadać liście wyników.")
    if status_pojemnosci == "Niewystarczająca":
        return {
            "status": "brak_pojemnosci",
            "miesiac": None,
            "etykieta": "Brak trwałego break-even przy obecnej obsadzie",
        }
    if wynik_miesieczny_w_stanie_stabilnym is None:
        return {
            "status": "niepotwierdzony",
            "miesiac": None,
            "etykieta": "Niepotwierdzony w horyzoncie",
        }
    if wynik_miesieczny_w_stanie_stabilnym <= TOLERANCJA:
        return {
            "status": "brak_ekonomiczny",
            "miesiac": None,
            "etykieta": "Brak trwałego break-even przy obecnej ekonomice",
        }

    byl_deficyt = any(wynik < -TOLERANCJA for wynik in wyniki_skumulowane)
    if not byl_deficyt:
        return {"status": "od_poczatku", "miesiac": None, "etykieta": "Od początku"}
    for indeks, (miesiac, wynik) in enumerate(zip(miesiace, wyniki_skumulowane)):
        if (
            miesiac > 0
            and wynik >= -TOLERANCJA
            and all(pozniejszy >= -TOLERANCJA for pozniejszy in wyniki_skumulowane[indeks:])
        ):
            return {
                "status": "osiagniety",
                "miesiac": miesiac,
                "etykieta": f"Miesiąc {miesiac}",
            }
    return {
        "status": "nie_osiagnieto",
        "miesiac": None,
        "etykieta": "Nie osiągnięto w horyzoncie",
    }


def _dane_przeplywu(parametry: dict) -> dict:
    """Wspólne ścieżki, minuty i przychód bez rachunku kosztów Panelu 1.

    Dzienny narzut lifecycle nie ogranicza rozłącznych zasobów ról kontraktu.
    Właściwe czynności dzienne rozlicza pojemnosc_obsady.
    """
    return oblicz_przeplyw(parametry)


def oblicz_pojemnosc_miesieczna(
    parametry: dict, lifecycle: dict | None = None, *, pracownicy: list[dict] | None = None
) -> dict:
    """Każda rola ma własne płatne godziny, czynności dzienne i popyt."""
    waliduj_parametry(parametry)
    if lifecycle is None:
        lifecycle = _dane_przeplywu(parametry)
    if pracownicy is None:
        if "pracownicy" not in parametry:
            raise ValueError("Brak wspólnej obsady pracowników kontraktu.")
        pracownicy = parametry["pracownicy"]
    pools = pojemnosc_obsady(pracownicy, parametry["codzienne_czynnosci"])
    wymagane_role = {"EH"} if parametry["liczba_spraw"] > 0 else set()
    if any(lifecycle["udzialy_ugod"][path] > 0 for path in (
            "automatyczne_ramy_ugoda", "automatyczne_ramy_brak_ugody",
            "zawarte_poza_ramami", "brak_ugody_poza_ramami")) and parametry["liczba_spraw"] > 0:
        wymagane_role.add("UGODY")
    for role in ROLE:
        pool = pools[role]
        demand = lifecycle["roczne_minuty_wedlug_roli"][role] / 12
        pool["popyt_minuty"] = demand
        pool["niedobor_minuty"] = max(demand - pool["netto_minuty"], 0.0)
        pool["wymagana_rola"] = role in wymagane_role
        tolerance = max(TOLERANCJA, demand * 1e-9)
        brak_roli = role in wymagane_role and pool["netto_minuty"] <= 0
        pool["status"] = ("Niewystarczająca" if brak_roli
                          or pool["dzienne_niewykonane_minuty"] > TOLERANCJA
                          or demand > pool["netto_minuty"] + tolerance
                          else "Na granicy" if demand > 0 and abs(demand - pool["netto_minuty"]) <= tolerance
                          else "Stabilna")
    statuses = [pool["status"] for pool in pools.values()]
    status = ("Niewystarczająca" if "Niewystarczająca" in statuses else
              "Na granicy" if "Na granicy" in statuses else "Stabilna")
    return {
        "role": pools,
        "pracownicy": [dict(p) for p in pracownicy],
        "pojemnosc_brutto_minuty": fsum(p["brutto_minuty"] for p in pools.values()),
        "czynnosci_dzienne_minuty": fsum(p["dzienne_minuty"] for p in pools.values()),
        "pojemnosc_na_sprawy_minuty": fsum(p["netto_minuty"] for p in pools.values()),
        "miesieczny_popyt_minuty": fsum(p["popyt_minuty"] for p in pools.values()),
        "miesieczny_koszt_wynagrodzen": fsum(p["wynagrodzenia"] for p in pools.values()),
        "status_pojemnosci": status,
    }


def _koszty_kontraktu(zmiany: dict | None) -> dict:
    koszty = wczytaj_defaults()["koszty_kontraktu"]
    if zmiany is not None:
        if not isinstance(zmiany, dict) or set(zmiany) - set(koszty):
            raise ValueError("Nieznane koszty kontraktu.")
        koszty.update(zmiany)
    for nazwa, wartosc in koszty.items():
        if (isinstance(wartosc, bool) or not isinstance(wartosc, (int, float))
                or not isfinite(wartosc) or wartosc < 0):
            raise ValueError(f"Koszt {nazwa} musi być nieujemną skończoną kwotą.")
    return koszty


def _status_break_even(
    break_even: dict, capacity_status: str, steady_monthly_result: float | None
) -> str:
    if capacity_status == "Niewystarczająca":
        return "Brak trwałego break-even przy obecnej obsadzie"
    if steady_monthly_result is not None and steady_monthly_result <= TOLERANCJA:
        return "Brak trwałego break-even przy obecnej ekonomice"
    if break_even["status"] == "niepotwierdzony":
        return "Niepotwierdzony w horyzoncie"
    if break_even["status"] == "nie_osiagnieto":
        return "Nie osiągnięto w horyzoncie"
    sustainable = (
        capacity_status in {"Stabilna", "Na granicy"}
        and steady_monthly_result is not None
        and steady_monthly_result > TOLERANCJA
    )
    if break_even["status"] == "od_poczatku":
        return "Rentowna od początku" if sustainable else "Wynik nietrwały"
    return "Break-even trwały" if sustainable else "Przecięcie nietrwałe"


def klasyfikuj_status_kontraktu(
    liczba_spraw: float, status_pojemnosci: str, wynik_miesieczny: float | None
) -> dict:
    """Ocena wyłącznie skonfigurowanego kontraktu po potwierdzeniu dojrzałości."""
    if status_pojemnosci not in {"Stabilna", "Na granicy", "Niewystarczająca"}:
        raise ValueError("Nieznany status pojemności.")
    if liczba_spraw <= TOLERANCJA:
        label = "Brak napływu spraw"
    elif status_pojemnosci == "Niewystarczająca":
        label = "Niewystarczająca pojemność według roli"
    elif wynik_miesieczny is None:
        label = "Stabilny operacyjnie, rentowność niepotwierdzona"
    elif wynik_miesieczny > TOLERANCJA:
        label = "Rentowny i stabilny"
    elif wynik_miesieczny < -TOLERANCJA:
        label = "Stabilny, ale nierentowny"
    else:
        label = "Stabilny, wynik zerowy"
    return {"etykieta": label, "status_pojemnosci": status_pojemnosci,
            "wynik_miesieczny_biezacej_obsady": wynik_miesieczny}


def _nominalny_miesiac_dojrzalosci(lifecycle: dict, czas: dict) -> int | None:
    """Pierwszy miesiąc dojrzałych wpływów z najdłuższej aktywnej ścieżki."""
    if lifecycle["ogolem"]["liczba_spraw"] <= TOLERANCJA:
        return None
    shares = lifecycle["udzialy_ugod"]
    ii_share = lifecycle["udzial_ii_instancji_w_portfelu"]
    failed_share = shares["automatyczne_ramy_brak_ugody"] + shares["brak_ugody_poza_ramami"]
    handoff = 1 if failed_share > TOLERANCJA else 0
    outcome_lags = (
        (shares["zakonczone_ugoda"], czas["miesiace_do_ugody"]),
        (shares["bez_ugody"] - ii_share, handoff + czas["miesiace_do_wyroku_i"]),
        (ii_share, handoff + czas["miesiace_do_wyroku_i"] + 1 + czas["miesiace_wyrok_i_do_ii"]),
    )
    active_lags = [lag for share, lag in outcome_lags if share > TOLERANCJA]
    if not active_lags:
        return None
    return 1 + max(active_lags) + czas["opoznienie_platnosci_miesiace"]


def podsumuj_finanse_kontraktu(rows: list[dict]) -> dict:
    """Jawne uzgodnienie całego horyzontu; wszystkie składniki pochodzą z miesięcy."""
    columns = ("Wynagrodzenia EH", "Wynagrodzenia ugód", "Koszty ogólne spraw, nad którymi pracowano",
               "Koszt sekretariatu spraw, nad którymi pracowano", "Łączny koszt miesięczny", "Przychód razem",
               "Wynik miesięczny przed podatkiem", "Sprawy, nad którymi pracowano w miesiącu")
    result = {column: fsum(row[column] for row in rows) for column in columns}
    components = fsum(result[column] for column in columns[:4])
    if not isclose(components, result["Łączny koszt miesięczny"], rel_tol=1e-10, abs_tol=1e-6):
        raise RuntimeError("Składniki kosztu kontraktu nie uzgadniają się z kosztami miesięcznymi.")
    if not isclose(result["Przychód razem"] - components, rows[-1]["Wynik skumulowany przed podatkiem"],
                   rel_tol=1e-10, abs_tol=1e-6):
        raise RuntimeError("Przychód minus pełny koszt nie uzgadnia się z wynikiem skumulowanym.")
    return result


def oblicz_model_czasowy(
    parametry: dict | None = None, parametry_czasowe: dict | None = None,
    *, pracownicy: list[dict] | None = None, koszty_kontraktu: dict | None = None,
    zapisz_zdarzenia: bool = False,
) -> dict:
    """Miesiące numerujemy od 1; termin = inicjacja etapu + opóźnienie.

    Wpływ → uwolnienie kolejek → praca FIFO z natychmiastowym przekazaniem
    przyjęcia EH do następnego etapu → wyniki formalne na koniec miesiąca
    → płatności → koszty. Odrzucenie ugody i wyrok I uwalniają kolejny etap
    od następnego miesiąca. Formalne czekanie nie zużywa minut ani opłat.
    """
    if parametry is None:
        parametry = domyslne_parametry()
    czas = _parametry_czasowe(parametry_czasowe)
    waliduj_parametry(parametry)
    lifecycle = _dane_przeplywu(parametry)
    capacity = oblicz_pojemnosc_miesieczna(parametry, lifecycle, pracownicy=pracownicy)
    costs = _koszty_kontraktu(koszty_kontraktu)
    horizon = czas["horyzont_miesiace"]
    monthly_inflow = miesieczny_naplyw(lifecycle["ogolem"]["liczba_spraw"])
    queues = {r: [] for r in ROLE}
    formal_outcomes = []
    active: dict[int, Sprawa] = {}
    deferred = defaultdict(list)
    payments = defaultdict(lambda: {"ugoda": 0.0, "wyrok": 0.0})
    events = []
    rows = []
    next_id = 0
    cumulative_inflow = cumulative_completed = cumulative_result = 0.0
    completed_delay_weight = completed_cases_for_delay = 0.0
    maximum_capacity_delay = 0
    total_due_minutes = total_executed_minutes = 0.0
    lags = {"ugoda": czas["miesiace_do_ugody"], "i": czas["miesiace_do_wyroku_i"],
            "ii": czas["miesiace_wyrok_i_do_ii"]}
    # Kolejność kanoniczna uniezależnia harmonogram od kolejności słowników.
    templates = []
    for group in sorted(lifecycle["grupy"], key=lambda g: (g["rodzaj"], g["grupa_wps"])):
        for path in sorted(SCIEZKI_UGODOWE + SCIEZKI_BEZ_UGODY):
            cases = group["liczba"] / 12 * lifecycle["udzialy_ugod"][path] / 100
            outcomes = [("ugoda", 1.0)] if path in SCIEZKI_UGODOWE else [
                ("i", 1 - parametry["udzial_ii_instancji_percent"] / 100),
                ("ii", parametry["udzial_ii_instancji_percent"] / 100)]
            for outcome, share in outcomes:
                count = cases * share
                if count <= 0:
                    continue
                stages = etapy_sprawy(parametry, path, parametry["dodatkowe_minuty"][group["rodzaj"]], outcome == "ii")
                unit_revenue = group["wynagrodzenie_ugoda" if outcome == "ugoda" else "wynagrodzenie_wyrok"]
                # Jednostkowe reprezentanty i reszta: zachowujemy dokładną wagę,
                # bez udawania ułamkowego zakończenia częściowo wykonanej sprawy.
                whole = int(count)
                weights = [1.0] * whole
                if count > whole:
                    weights.append(count - whole)
                templates.extend((path, outcome, w, unit_revenue * w, stages) for w in weights)
    cohort_reference = {"przychod": lifecycle["ogolem"]["przychod"] / 12,
                        "bezposrednie_minuty": lifecycle["bezposrednie_minuty_spraw"] / 12,
                        "liczba_spraw": monthly_inflow}
    cohort_stats = {"revenue": fsum(t[3] for t in templates),
                    "direct_minutes": fsum(t[2] * fsum(e.minuty for e in t[4]) for t in templates),
                    "cases": fsum(t[2] for t in templates)}
    for name, built in (("przychod", "revenue"), ("bezposrednie_minuty", "direct_minutes"), ("liczba_spraw", "cases")):
        if not isclose(cohort_stats[built], cohort_reference[name], rel_tol=1e-10, abs_tol=1e-6):
            raise RuntimeError(f"Miesięczna kohorta nie uzgadnia pola {name}.")

    def event(kind, c, minutes=0.0):
        if zapisz_zdarzenia:
            events.append({"miesiac": month, "rodzaj": kind, "sprawa": c.identyfikator,
                           "waga": c.waga, "sciezka": c.sciezka, "wynik": c.wynik,
                           "etap": c.etap.nazwa, "rola": c.etap.rola, "minuty": minutes})

    def enqueue(c, kontynuacja=False):
        c.dostepna_od = month
        heappush(queues[c.etap.rola], (month, c.wplyw, c.identyfikator))
        if not kontynuacja:
            role_work[c.etap.rola]["new"] += c.minuty_kolejki()

    def advance(c, next_month=False):
        poprzednia_rola = c.etap.rola
        c.indeks += 1
        c.pozostale = c.waga * c.etap.minuty
        c.termin = None
        c.dostepna_od = month + int(next_month)
        if next_month:
            deferred[month + 1].append(c)
        else:
            enqueue(c, kontynuacja=poprzednia_rola == c.etap.rola)

    for month in range(1, horizon + 1):
        role_work = {r: {"start": rows[-1][f"Backlog {r} (h)"] * 60 if rows else 0.0,
                         "new": 0.0, "executed": 0.0} for r in ROLE}
        work_cases_start = rows[-1]["Sprawy oczekujące na pracę"] if rows else 0.0
        for c in deferred.pop(month, []):
            enqueue(c)
        for path, outcome, weight, revenue, stages in templates:
            c = Sprawa(next_id, month, path, outcome, weight, revenue, stages,
                       pozostale=weight * stages[0].minuty, dostepna_od=month)
            active[next_id] = c
            next_id += 1
            enqueue(c)
        cumulative_inflow += monthly_inflow
        available = {r: capacity["role"][r]["netto_minuty"] for r in ROLE}
        worked = set()
        stage_finished = defaultdict(float)
        while True:
            candidates = []
            for r in ROLE:
                if not queues[r] or capacity["role"][r]["netto_minuty"] <= 0:
                    continue
                c = active[queues[r][0][2]]
                if c.pozostale == 0 or available[r] > 0:
                    candidates.append((queues[r][0], r))
            if not candidates:
                break
            _, r = min(candidates)
            _, _, ident = heappop(queues[r])
            c = active[ident]
            stage = c.etap
            if stage.nazwa not in c.starty:
                c.starty[stage.nazwa] = month
                if stage.zegar:
                    c.termin = month + lags[stage.zegar]
                event("inicjacja", c)
            executed = min(c.pozostale, available[r])
            if executed > 0:
                event("praca", c, executed)
                worked.add(ident)
                role_work[r]["executed"] += executed
                available[r] = max(available[r] - executed, 0.0)
                c.pozostale = max(c.pozostale - executed, 0.0)
            if c.pozostale > 0:
                heappush(queues[r], (c.dostepna_od, c.wplyw, ident))
                continue
            c.konce_pracy[stage.nazwa] = month
            stage_finished[stage.nazwa] += c.waga
            event("koniec_pracy", c)
            if stage.zegar is None:
                advance(c, next_month=stage.nazwa == "proba_ugody")
            else:
                # Termin jest ustalony przy inicjacji; do menedżera wyników
                # trafia dopiero po zakończeniu całej wymaganej pracy etapu.
                heappush(formal_outcomes, (max(c.termin, month), ident))
        worked_count = fsum(active[i].waga for i in worked)
        settlements = first_instance_endings = second_instance_endings = 0.0
        while formal_outcomes and formal_outcomes[0][0] <= month:
            _, ident = heappop(formal_outcomes)
            c = active[ident]
            if c.etap.zegar == "i" and c.wynik == "ii":
                event("wyrok_i", c)
                advance(c, next_month=True)
                continue
            event("zakonczenie", c)
            cumulative_completed += c.waga
            if c.wynik == "ugoda":
                settlements += c.waga
            elif c.wynik == "i":
                first_instance_endings += c.waga
            else:
                second_instance_endings += c.waga
            nominal_lag = (lags["ugoda"] if c.wynik == "ugoda" else lags["i"]
                + int(any(e.nazwa == "proba_ugody" for e in c.etapy))
                + (1 + lags["ii"] if c.wynik == "ii" else 0))
            delay = month - c.wplyw - nominal_lag
            completed_delay_weight += delay * c.waga
            completed_cases_for_delay += c.waga
            maximum_capacity_delay = max(maximum_capacity_delay, delay)
            payments[month + czas["opoznienie_platnosci_miesiace"]]["ugoda" if c.wynik == "ugoda" else "wyrok"] += c.przychod
            del active[ident]
        settlement_revenue = payments[month]["ugoda"]
        judgment_revenue = payments[month]["wyrok"]
        revenue = settlement_revenue + judgment_revenue
        overhead_cost = worked_count * costs["ogolne_na_aktywna_sprawe"]
        secretariat_cost = worked_count * costs["sekretariat_na_aktywna_sprawe"]
        wage_cost = capacity["miesieczny_koszt_wynagrodzen"]
        operation_cost = wage_cost + overhead_cost + secretariat_cost
        monthly_result = revenue - operation_cost
        cumulative_result += monthly_result
        for r in ROLE:
            role_work[r]["end"] = fsum(active[i].minuty_kolejki() for _, _, i in queues[r])
            w = role_work[r]
            if not isclose(w["start"] + w["new"] - w["executed"], w["end"], rel_tol=1e-10, abs_tol=1e-6):
                raise RuntimeError(f"Kolejka {r} nie zachowuje minut.")
        backlog_start_minutes = fsum(w["start"] for w in role_work.values())
        new_due_minutes = fsum(w["new"] for w in role_work.values())
        executed_minutes = fsum(w["executed"] for w in role_work.values())
        backlog_end_minutes_month = fsum(w["end"] for w in role_work.values())
        total_due_minutes += new_due_minutes
        total_executed_minutes += executed_minutes
        direct_capacity = capacity["pojemnosc_na_sprawy_minuty"]
        used_minutes = capacity["czynnosci_dzienne_minuty"] + executed_minutes
        if used_minutes > capacity["pojemnosc_brutto_minuty"] + TOLERANCJA:
            raise RuntimeError("Wykonano pracę ponad limit płatnych godzin FTE.")
        unused_minutes = max(capacity["pojemnosc_brutto_minuty"] - used_minutes, 0.0)
        utilization = used_minutes / capacity["pojemnosc_brutto_minuty"] * 100 if capacity["pojemnosc_brutto_minuty"] > 0 else None
        queued = {i for queue in queues.values() for _, _, i in queue}
        weights, outstanding, waiting, blocked_second = [], [], [], []
        future_parts = {r: [] for r in ROLE}
        # Jeden przegląd portfela uzgadnia rzeczywisty stan wszystkich spraw;
        # nie wyprowadzamy przyszłej pracy jako reszty równania bilansowego.
        for c in active.values():
            weights.append(c.waga)
            future = {r: c.przyszle_minuty(r) for r in ROLE}
            unfinished = c.pozostale > 0 or any(v > 0 for v in future.values())
            if unfinished or c.etap.nazwa not in c.konce_pracy:
                outstanding.append(c.waga)
            if c.termin is not None and c.etap.nazwa in c.konce_pracy:
                waiting.append(c.waga)
            future[c.etap.rola] += c.pozostale
            if c.identyfikator in queued:
                future[c.etap.rola] -= c.minuty_kolejki()
            for r in ROLE:
                future_parts[r].append(future[r])
            blocked_second.append(c.waga * c.plan[c.indeks][3])
        active_cases = fsum(weights)
        outstanding_cases = fsum(outstanding)
        formal_waiting = fsum(waiting)
        blocked_ii_minutes = fsum(blocked_second)
        if not isclose(cumulative_inflow - cumulative_completed, active_cases, rel_tol=1e-10, abs_tol=1e-6):
            raise RuntimeError("Sprawy otwarte nie uzgadniają się z wpływem i zakończeniami.")
        future_by_role = {r: fsum(future_parts[r]) for r in ROLE}
        future_minutes = fsum(future_by_role.values())
        all_cohort_minutes = cohort_stats["direct_minutes"] * month
        if not isclose(total_executed_minutes + backlog_end_minutes_month + future_minutes,
                       all_cohort_minutes, rel_tol=1e-10, abs_tol=1e-5):
            raise RuntimeError("Praca wykonana, zaległa i przyszła nie uzgadnia się z kohortami.")
        rows.append({
            "Miesiąc": month, "Nowe sprawy": monthly_inflow,
            "Sprawy otwarte": active_cases,
            "Aktywne sprawy": active_cases,
            "Sprawy oczekujące na pracę": outstanding_cases,
            "Sprawy oczekujące na pracę na początku": work_cases_start,
            "Sprawy, nad którymi pracowano w miesiącu": worked_count,
            "Sprawy oczekujące na formalne zakończenie": formal_waiting,
            "Praca przyszła i zablokowana (h)": future_minutes / 60,
            "II instancja oczekująca na pracę I (h)": blocked_ii_minutes / 60,
            **{f"{label} {r} (h)": role_work[r][key] / 60 for r in ROLE
               for label, key in (("Backlog początek", "start"), ("Nowa praca", "new"), ("Wykonana praca", "executed"), ("Backlog", "end"))},
            **{f"Pojemność {r} (h)": capacity["role"][r]["netto_minuty"] / 60 for r in ROLE},
            **{f"Ukończona praca: {stage}": stage_finished[stage] for stage in ("przyjecie", "ugoda", "proba_ugody", "proces", "ii_instancja")},
            "Ugody zakończone": settlements,
            "Zakończenia po I instancji": first_instance_endings,
            "Zakończenia po II instancji": second_instance_endings,
            "Przychód z ugód": settlement_revenue, "Przychód z wyroków": judgment_revenue,
            "Przychód razem": revenue,
            "Pojemność brutto (h)": capacity["pojemnosc_brutto_minuty"] / 60,
            "Czynności dzienne (h)": capacity["czynnosci_dzienne_minuty"] / 60,
            "Niewykonane czynności dzienne (h)": capacity["role"]["EH"]["dzienne_niewykonane_minuty"] / 60,
            "Dostępna pojemność na sprawy (h)": direct_capacity / 60,
            "Backlog na początku (h)": backlog_start_minutes / 60,
            "Nowa praca (h)": new_due_minutes / 60,
            "Praca oczekująca (h)": (backlog_start_minutes + new_due_minutes) / 60,
            "Wykonana praca (h)": executed_minutes / 60,
            "Wykorzystane płatne godziny": used_minutes / 60,
            "Backlog na koniec (h)": backlog_end_minutes_month / 60,
            "Wykorzystanie pojemności (%)": utilization,
            "Niewykorzystana pojemność (h)": unused_minutes / 60,
            "Wynagrodzenia EH": capacity["role"]["EH"]["wynagrodzenia"],
            "Wynagrodzenia ugód": capacity["role"]["UGODY"]["wynagrodzenia"],
            "Koszty ogólne spraw, nad którymi pracowano": overhead_cost,
            "Koszt sekretariatu spraw, nad którymi pracowano": secretariat_cost,
            "Miesięczny koszt wynagrodzeń": wage_cost, "Łączny koszt miesięczny": operation_cost,
            "Wynik miesięczny przed podatkiem": monthly_result,
            "Wynik skumulowany przed podatkiem": cumulative_result,
        })
    backlog_end_minutes = rows[-1]["Backlog na koniec (h)"] * 60
    blocked_ii_minutes = rows[-1]["II instancja oczekująca na pracę I (h)"] * 60
    cohort_validations = [cohort_stats]

    pierwsze_przeciecie = wyznacz_break_even(
        [row["Wynik skumulowany przed podatkiem"] for row in rows],
        [row["Miesiąc"] for row in rows],
    )
    first_positive = next(
        (
            row["Miesiąc"]
            for row in rows
            if row["Wynik miesięczny przed podatkiem"] > TOLERANCJA
        ),
        None,
    )
    deepest = min(rows, key=lambda row: row["Wynik skumulowany przed podatkiem"])
    nominal_maturity_month = _nominalny_miesiac_dojrzalosci(lifecycle, czas)
    target_monthly_revenue = lifecycle["ogolem"]["przychod"] / 12
    target_monthly_demand = lifecycle["bezposrednie_minuty_spraw"] / 12
    case_count = lifecycle["ogolem"]["liczba_spraw"]
    last_twelve = rows[-12:] if len(rows) >= 12 else []
    mature_revenue = fsum(row["Przychód razem"] for row in last_twelve) / 12 if last_twelve else None
    mature_demand = fsum(row["Nowa praca (h)"] * 60 for row in last_twelve) / 12 if last_twelve else None

    def blisko(a, b):
        return isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)

    expected_completions = {
        "Ugody zakończone": monthly_inflow * lifecycle["udzialy_ugod"]["zakonczone_ugoda"] / 100,
        "Zakończenia po II instancji": monthly_inflow * lifecycle["udzial_ii_instancji_w_portfelu"] / 100,
    }
    expected_completions["Zakończenia po I instancji"] = (monthly_inflow
        - expected_completions["Ugody zakończone"] - expected_completions["Zakończenia po II instancji"])

    # Pełne 12 miesięcy po najdłuższej aktywnej ścieżce i opóźnieniu płatności.
    maturity_reached = bool(
        nominal_maturity_month is not None
        and horizon >= nominal_maturity_month + 11
        and capacity["status_pojemnosci"] != "Niewystarczająca"
        and last_twelve
        and blisko(mature_demand, target_monthly_demand)
        and all(blisko(row["Przychód razem"], target_monthly_revenue)
                and all(blisko(row[key], expected) for key, expected in expected_completions.items())
                and blisko(row["Aktywne sprawy"], last_twelve[0]["Aktywne sprawy"])
                and blisko(row["Sprawy, nad którymi pracowano w miesiącu"], last_twelve[0]["Sprawy, nad którymi pracowano w miesiącu"])
                and blisko(row["Łączny koszt miesięczny"], last_twelve[0]["Łączny koszt miesięczny"])
                and all(blisko(row[f"Wykonana praca {role} (h)"] * 60, capacity["role"][role]["popyt_minuty"])
                        and blisko(row[f"Backlog {role} (h)"], 0) for role in ROLE)
                for row in last_twelve)
    )
    steady_monthly_result = (fsum(row["Wynik miesięczny przed podatkiem"] for row in last_twelve) / 12
                             if maturity_reached else None)
    current_staff_monthly_result = steady_monthly_result
    contract_status = klasyfikuj_status_kontraktu(case_count, capacity["status_pojemnosci"], steady_monthly_result)
    gross_minutes = capacity["pojemnosc_brutto_minuty"]
    average_utilization = (
        sum(
            row["Czynności dzienne (h)"] + row["Wykonana praca (h)"]
            for row in rows
        )
        / len(rows)
        / (gross_minutes / 60)
        * 100
        if gross_minutes > TOLERANCJA
        else None
    )
    current_utilization = rows[-1]["Wykorzystanie pojemności (%)"]
    recent_rows = rows[-12:]
    recent_utilization = (
        sum(row["Wykorzystanie pojemności (%)"] for row in recent_rows)
        / len(recent_rows)
        if recent_rows
        and all(
            row["Wykorzystanie pojemności (%)"] is not None
            for row in recent_rows
        )
        else None
    )
    role_backlog_months = {}
    for role in ROLE:
        backlog = rows[-1][f"Backlog {role} (h)"] * 60
        available = capacity["role"][role]["netto_minuty"]
        role_backlog_months[role] = (backlog / available if available > TOLERANCJA
                                     else 0.0 if backlog <= TOLERANCJA else None)
    backlog_months = (max(role_backlog_months.values())
                      if all(v is not None for v in role_backlog_months.values()) else None)
    average_capacity_delay = (
        completed_delay_weight / completed_cases_for_delay
        if completed_cases_for_delay > TOLERANCJA
        else 0.0
    )
    trwaly_break_even = wyznacz_trwaly_break_even(
        [row["Wynik skumulowany przed podatkiem"] for row in rows],
        [row["Miesiąc"] for row in rows],
        capacity["status_pojemnosci"],
        steady_monthly_result,
    )
    break_even_sustainability = _status_break_even(
        trwaly_break_even, capacity["status_pojemnosci"], steady_monthly_result
    )
    if case_count <= TOLERANCJA:
        maturity_status = "Brak napływu spraw"
    elif capacity["status_pojemnosci"] == "Niewystarczająca":
        maturity_status = "Nieosiągalny przy obecnej obsadzie"
    elif maturity_reached:
        maturity_status = "Osiągnięty"
    else:
        maturity_status = "Nie osiągnięto w horyzoncie"
    minimum_confirmed = deepest["Miesiąc"] < horizon and any(
        row["Wynik skumulowany przed podatkiem"]
        > deepest["Wynik skumulowany przed podatkiem"] + TOLERANCJA
        for row in rows[deepest["Miesiąc"] :]
    )
    recent_monthly_trend = (
        sum(row["Wynik miesięczny przed podatkiem"] for row in recent_rows)
        / len(recent_rows)
        if recent_rows
        else None
    )
    long_run_or_recent_result = (
        steady_monthly_result
        if steady_monthly_result is not None
        else recent_monthly_trend
    )
    # Trwały spadek wymaga wykonalnej ujemnej ekonomiki dojrzałej obsady;
    # średnia miesięcy rozruchowych pozostaje wyłącznie diagnostyką.
    structural_decline = (
        current_staff_monthly_result is not None
        and current_staff_monthly_result < -TOLERANCJA
    )
    current_capacity_delay = max((horizon - due for queue in queues.values() for due, _, _ in queue), default=0)
    startup_deficit = any(row["Wynik skumulowany przed podatkiem"] < -TOLERANCJA
                          for row in rows[:min(nominal_maturity_month or horizon, len(rows))])

    return {
        "zdarzenia": events,
        "parametry_czasowe": czas,
        "koszty_kontraktu": costs,
        "podsumowanie_finansowe": podsumuj_finanse_kontraktu(rows),
        "tabela_miesieczna": rows,
        "pojemnosc": {
            **capacity,
            "srednie_wykorzystanie_percent": average_utilization,
            "biezace_wykorzystanie_percent": current_utilization,
            "ostatnie_12_miesiecy_wykorzystanie_percent": recent_utilization,
        },
        "kpi": {
            "status_kontraktu": contract_status["etykieta"],
            "status_kontraktu_skladniki": contract_status,
            "wynik_miesieczny_biezacej_obsady": current_staff_monthly_result,
            "break_even_skumulowany": trwaly_break_even["etykieta"],
            "break_even_status": trwaly_break_even["status"],
            "break_even_miesiac": trwaly_break_even["miesiac"],
            "status_break_even": break_even_sustainability,
            "pierwsze_przeciecie_skumulowane": pierwsze_przeciecie["etykieta"],
            "pierwsze_przeciecie_status": pierwsze_przeciecie["status"],
            "pierwsze_przeciecie_miesiac": pierwsze_przeciecie["miesiac"],
            "pierwszy_dodatni_miesiac": first_positive,
            "najglebszy_deficyt_skumulowany": deepest[
                "Wynik skumulowany przed podatkiem"
            ],
            "miesiac_najglebszego_deficytu": deepest["Miesiąc"],
            "najglebszy_deficyt_potwierdzony": minimum_confirmed,
            "wynik_skumulowany_na_koniec_horyzontu": rows[-1][
                "Wynik skumulowany przed podatkiem"
            ],
            "wynik_nadal_narasta": structural_decline,
            "trend_miesieczny_wyniku": long_run_or_recent_result,
            "wynik_miesieczny_w_stanie_stabilnym": steady_monthly_result,
            "wynik_roczny_w_stanie_stabilnym": (
                steady_monthly_result * 12
                if steady_monthly_result is not None else None
            ),
        },
        "podsumowanie": {
            "roczny_naplyw": lifecycle["ogolem"]["liczba_spraw"],
            "sredni_naplyw_miesieczny": monthly_inflow,
            "laczny_naplyw": monthly_inflow * horizon,
            "aktywne_sprawy": rows[-1]["Aktywne sprawy"],
            "sprawy_oczekujace_na_prace": rows[-1]["Sprawy oczekujące na pracę"],
            "sprawomiesiace_pracy": fsum(r["Sprawy, nad którymi pracowano w miesiącu"] for r in rows),
            "backlog_koniec_godziny": rows[-1]["Backlog na koniec (h)"],
            "maksymalny_backlog_godziny": max(
                row["Backlog na koniec (h)"] for row in rows
            ),
            "miesiace_backlogu": backlog_months,
            "miesiace_backlogu_wedlug_roli": role_backlog_months,
            "srednie_opoznienie_pojemnosci_miesiace": average_capacity_delay,
            "maksymalne_opoznienie_pojemnosci_miesiace": maximum_capacity_delay,
            "biezace_opoznienie_pojemnosci_miesiace": current_capacity_delay,
            "dojrzalosc_osiagnieta": maturity_reached,
            "status_stanu_stabilnego": maturity_status,
            "nominalny_miesiac_dojrzalosci": nominal_maturity_month,
            "sredni_dojrzaly_przychod_miesieczny": mature_revenue if maturity_reached else None,
            "sredni_dojrzaly_popyt_minuty": mature_demand if maturity_reached else None,
        },
        "diagnoza": {
            "deficyt_rozruchowy": startup_deficit,
            "strukturalny_niedobor_pojemnosci": (
                capacity["status_pojemnosci"] == "Niewystarczająca"
            ),
            "roczny_przychod_lifecycle": lifecycle["ogolem"]["przychod"],
            "koszt_kontraktu_horyzont": fsum(row["Łączny koszt miesięczny"] for row in rows),
        },
        "walidacja": {
            "role": {role: {
                "nalezna_minuty": fsum(row[f"Nowa praca {role} (h)"] * 60 for row in rows),
                "wykonana_minuty": fsum(row[f"Wykonana praca {role} (h)"] * 60 for row in rows),
                "backlog_minuty": rows[-1][f"Backlog {role} (h)"] * 60,
            } for role in ROLE},
            "kohorta_miesieczna": cohort_reference,
            "kohorta_zbudowana": cohort_validations[0] if cohort_validations else {},
            "roczny_przychod_lifecycle": lifecycle["ogolem"]["przychod"],
            "roczne_minuty_bezposrednie_lifecycle": lifecycle["bezposrednie_minuty_spraw"],
            "dojrzaly_przychod_roczny": (
                mature_revenue * 12 if maturity_reached and mature_revenue is not None else None
            ),
            "dojrzaly_popyt_roczny_minuty": (
                mature_demand * 12 if maturity_reached and mature_demand is not None else None
            ),
            "praca_nalezna_do_horyzontu_minuty": total_due_minutes,
            "praca_wszystkich_kohort_minuty": all_cohort_minutes,
            "praca_przyszla_minuty": future_minutes,
            "w_tym_ii_oczekujaca_na_i_minuty": blocked_ii_minutes,
            "minuty_przyszle_wedlug_roli": future_by_role,
            "praca_wykonana_minuty": total_executed_minutes,
            "backlog_minuty": backlog_end_minutes,
            "laczny_naplyw_spraw": cumulative_inflow,
            "laczne_zakonczenia_spraw": cumulative_completed,
            "aktywne_sprawy": rows[-1]["Aktywne sprawy"],
        },
    }


def porownaj_obsade(parametry: dict, parametry_czasowe: dict | None = None,
                     *, scenariusze: dict[str, list[dict]], koszty_kontraktu: dict | None = None) -> list[dict]:
    """Porównuje wyłącznie jawnie podane składy, bez wymyślania etatów i stawek."""
    rows = []
    for nazwa, pracownicy in scenariusze.items():
        wynik = oblicz_model_czasowy(parametry, parametry_czasowe, pracownicy=pracownicy,
                                    koszty_kontraktu=koszty_kontraktu)
        rows.append({"Wariant": nazwa, "Liczba pracowników": len(pracownicy),
                     "Status pojemności": wynik["pojemnosc"]["status_pojemnosci"],
                     "Koszt wynagrodzeń": wynik["pojemnosc"]["miesieczny_koszt_wynagrodzen"],
                     "Backlog (h)": wynik["podsumowanie"]["backlog_koniec_godziny"],
                     "Dojrzały wynik miesięczny": wynik["kpi"]["wynik_miesieczny_w_stanie_stabilnym"]})
    return rows
