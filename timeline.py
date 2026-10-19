"""Ciągły, pojemnościowy model ekonomii operacyjnej w czasie.

``oblicz_przeplyw`` jest wspólnym źródłem oczekiwanej pracy i przychodu
kohorty referencyjnej, bez wyceny lifecycle. Ten moduł tworzy co miesiąc proporcjonalną kohortę, układa jej
pracę w kolejce FIFO i pobiera pełny koszt dostarczonej obsady. Koszt okresowy
nie jest zatem uzgadniany z kosztem pracy zużytej przez pojedynczą kohortę.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
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


@dataclass
class WorkPacket:
    """Porcja bezpośredniej pracy dostępna w kolejce od wskazanego miesiąca."""

    due_month: int
    cohort_month: int
    path: str
    stage: str
    minutes_remaining: float
    completion_id: int
    role: str = "EH"


@dataclass
class Completion:
    """Oczekiwana grupa spraw; postęp wszystkich etapów wyznacza zakończenia."""

    cohort_month: int
    path: str
    outcome: str
    nominal_month: int
    cases: float
    revenue: float
    stage_total_minutes: dict[str, float] = field(default_factory=dict)
    stage_executed_minutes: dict[str, float] = field(default_factory=dict)
    recognized_fraction: float = 0.0


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
    packets, completions = defaultdict(list), []
    _dodaj_kohorte(1, lifecycle, parametry, domyslne_parametry_czasowe(), packets, completions)
    for role in ROLE:
        pool = pools[role]
        demand = fsum(p.minutes_remaining for bucket in packets.values() for p in bucket if p.role == role)
        pool["popyt_minuty"] = demand
        pool["niedobor_minuty"] = max(demand - pool["netto_minuty"], 0.0)
        tolerance = max(TOLERANCJA, demand * 1e-9)
        pool["status"] = ("Niewystarczająca" if demand > pool["netto_minuty"] + tolerance
                          else "Na granicy" if abs(demand - pool["netto_minuty"]) <= tolerance
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


def _dodaj_pakiet(
    due_packets: dict[int, list[WorkPacket]],
    completions: list[Completion],
    completion_id: int,
    due_month: int,
    cohort_month: int,
    path: str,
    stage: str,
    minutes_value: float,
    cohort_stats: dict,
) -> None:
    if minutes_value <= TOLERANCJA:
        return
    packet = WorkPacket(
        due_month=due_month,
        cohort_month=cohort_month,
        path=path,
        stage=stage,
        minutes_remaining=minutes_value,
        completion_id=completion_id,
        role="UGODY" if stage in {"analiza_ugody", "zawarcie_ugody", "nieudana_proba_ugody"} else "EH",
    )
    due_packets[due_month].append(packet)
    completion = completions[completion_id]
    completion.stage_total_minutes[stage] = (
        completion.stage_total_minutes.get(stage, 0.0) + minutes_value
    )
    completion.stage_executed_minutes.setdefault(stage, 0.0)
    cohort_stats["direct_minutes"] += minutes_value


def _dodaj_kohorte(
    cohort_month: int,
    lifecycle: dict,
    parametry: dict,
    czas: dict,
    due_packets: dict[int, list[WorkPacket]],
    completions: list[Completion],
) -> dict:
    """Zleca pracę przy wpływie, a II instancję w terminie wyroku I.

    Terminy nominalne blokują zakończenie, nie rozkładają minut pracy.
    Kohorta zużywa dokładnie 1/12 pracy i przychodu referencyjnego lifecycle.
    """
    shares = lifecycle["udzialy_ugod"]
    second_instance_share = parametry["udzial_ii_instancji_percent"] / 100
    common_minutes = sum(parametry["wspolne_czynnosci"].values())
    process_minutes = sum(parametry["procesowe_czynnosci"].values())
    settlement_analysis_minutes = parametry["analiza_mozliwosci_ugody"]
    settlement_minutes = sum(parametry["ugodowe_czynnosci"].values())
    failed_offer_minutes = (
        parametry["ugodowe_czynnosci"].get("Oferta ugody", 0)
        + parametry["ugodowe_czynnosci"].get("Projekt ugody", 0)
    )
    second_instance_minutes = parametry["obsluga_ii_instancji_minuty"]
    cohort_stats = {"direct_minutes": 0.0, "revenue": 0.0, "cases": 0.0}

    def new_completion(
        path: str,
        outcome: str,
        nominal_month: int,
        cases: float,
        revenue: float,
    ) -> int:
        completion_id = len(completions)
        completions.append(
            Completion(
                cohort_month=cohort_month,
                path=path,
                outcome=outcome,
                nominal_month=nominal_month,
                cases=cases,
                revenue=revenue,
            )
        )
        cohort_stats["revenue"] += revenue
        cohort_stats["cases"] += cases
        return completion_id

    for group in lifecycle["grupy"]:
        group_cases = group["liczba"] / 12
        extra_minutes = parametry["dodatkowe_minuty"][group["rodzaj"]]
        for path in SCIEZKI_UGODOWE:
            cases = group_cases * shares[path] / 100
            if cases <= TOLERANCJA:
                continue
            nominal = cohort_month + czas["miesiace_do_ugody"]
            completion_id = new_completion(
                path,
                "ugoda",
                nominal,
                cases,
                cases * group["wynagrodzenie_ugoda"],
            )
            _dodaj_pakiet(
                due_packets, completions, completion_id, cohort_month,
                cohort_month, path, "przyjecie", cases * common_minutes, cohort_stats,
            )
            if path == "zawarte_poza_ramami":
                _dodaj_pakiet(
                    due_packets, completions, completion_id, cohort_month,
                    cohort_month, path, "analiza_ugody",
                    cases * settlement_analysis_minutes, cohort_stats,
                )
            _dodaj_pakiet(
                due_packets, completions, completion_id, cohort_month,
                cohort_month, path, "zawarcie_ugody",
                cases * settlement_minutes, cohort_stats,
            )
            _dodaj_pakiet(
                due_packets, completions, completion_id, cohort_month,
                cohort_month, path, "praca_dodatkowa_p",
                cases * extra_minutes, cohort_stats,
            )

        for path in SCIEZKI_BEZ_UGODY:
            path_cases = group_cases * shares[path] / 100
            for second_instance, cases in (
                (False, path_cases * (1 - second_instance_share)),
                (True, path_cases * second_instance_share),
            ):
                if cases <= TOLERANCJA:
                    continue
                first_judgment = cohort_month + czas["miesiace_do_wyroku_i"]
                nominal = first_judgment + (
                    czas["miesiace_wyrok_i_do_ii"] if second_instance else 0
                )
                outcome = "ii" if second_instance else "i"
                branch_path = f"{path}:{outcome}"
                completion_id = new_completion(
                    branch_path,
                    outcome,
                    nominal,
                    cases,
                    cases * group["wynagrodzenie_wyrok"],
                )
                _dodaj_pakiet(
                    due_packets, completions, completion_id, cohort_month,
                    cohort_month, branch_path, "przyjecie",
                    cases * common_minutes, cohort_stats,
                )
                if path in {"brak_szans", "brak_ugody_poza_ramami"}:
                    _dodaj_pakiet(
                        due_packets, completions, completion_id, cohort_month,
                        cohort_month, branch_path, "analiza_ugody",
                        cases * settlement_analysis_minutes, cohort_stats,
                    )
                if path in {
                    "automatyczne_ramy_brak_ugody",
                    "brak_ugody_poza_ramami",
                }:
                    _dodaj_pakiet(
                        due_packets, completions, completion_id, cohort_month,
                        cohort_month, branch_path, "nieudana_proba_ugody",
                        cases * failed_offer_minutes, cohort_stats,
                    )
                _dodaj_pakiet(
                    due_packets, completions, completion_id, cohort_month,
                    cohort_month, branch_path, "proces",
                    cases * process_minutes, cohort_stats,
                )
                _dodaj_pakiet(
                    due_packets, completions, completion_id, cohort_month,
                    cohort_month, branch_path, "praca_dodatkowa_p",
                    cases * extra_minutes, cohort_stats,
                )
                if second_instance:
                    _dodaj_pakiet(
                        due_packets, completions, completion_id, first_judgment,
                        cohort_month, branch_path, "ii_instancja",
                        cases * second_instance_minutes, cohort_stats,
                    )
    return cohort_stats


def _uwolnij_ii(pending: list[WorkPacket], completions: list[Completion], month: int) -> list[WorkPacket]:
    """Przenosi do kolejki tylko nową część II instancji odblokowaną po I."""
    released = []
    for packet in pending:
        if month < packet.due_month:
            continue
        completion = completions[packet.completion_id]
        total = completion.stage_total_minutes["ii_instancja"]
        already_released = total - packet.minutes_remaining
        unlocked = total * _postep_etapow(completion, bez_ii=True)
        minutes = min(packet.minutes_remaining, max(unlocked - already_released, 0.0))
        if minutes > TOLERANCJA:
            released.append(WorkPacket(month, packet.cohort_month, packet.path,
                                       packet.stage, minutes, packet.completion_id, "EH"))
            packet.minutes_remaining -= minutes
    pending[:] = [p for p in pending if p.minutes_remaining > TOLERANCJA]
    return released


def _dolacz_do_kolejki(queue: deque[list[WorkPacket]], packets: list[WorkPacket]) -> None:
    if not packets:
        return
    if queue and queue[-1][0].due_month == packets[0].due_month:
        queue[-1].extend(packets)
    else:
        queue.append(packets)


def _postep_etapow(completion: Completion, *, bez_ii: bool = False) -> float:
    return min((min(completion.stage_executed_minutes[stage] / total, 1.0)
                for stage, total in completion.stage_total_minutes.items()
                if total > 0 and not (bez_ii and stage == "ii_instancja")), default=1.0)


def _dostepne_minuty(packet: WorkPacket, completions: list[Completion]) -> float:
    if packet.stage != "ii_instancja":
        return packet.minutes_remaining
    c = completions[packet.completion_id]
    # Ułamki grupy mogą wejść do II instancji dopiero po pełnej I instancji.
    unlocked = c.stage_total_minutes[packet.stage] * _postep_etapow(c, bez_ii=True)
    return min(packet.minutes_remaining, max(unlocked - c.stage_executed_minutes[packet.stage], 0.0))


def _wykonaj_prace(
    queue: deque[list[WorkPacket]], completions: list[Completion], available_minutes: float,
) -> float:
    """FIFO dostępnych pakietów; proporcjonalny przydział w tej samej dacie.

    Zablokowana II instancja nie zatrzymuje pracy stanowiącej jej warunek.
    Ponowny przebieg wykorzystuje moc zwolnioną po wykonaniu tych warunków.
    """
    executed_parts = []
    remaining_capacity = available_minutes
    while remaining_capacity > TOLERANCJA:
        pass_executed = 0.0
        for bucket in list(queue):
            eligible = [_dostepne_minuty(p, completions) for p in bucket]
            work = fsum(eligible)
            if work <= TOLERANCJA:
                continue
            fraction = min(remaining_capacity / work, 1.0)
            pieces = []
            for packet, minutes in zip(bucket, eligible):
                executed = minutes * fraction
                packet.minutes_remaining = max(packet.minutes_remaining - executed, 0.0)
                completions[packet.completion_id].stage_executed_minutes[packet.stage] += executed
                pieces.append(executed)
            executed = fsum(pieces)
            executed_parts.append(executed)
            pass_executed += executed
            remaining_capacity = max(remaining_capacity - executed, 0.0)
            if all(p.minutes_remaining <= TOLERANCJA for p in bucket):
                queue.remove(bucket)
            if remaining_capacity <= TOLERANCJA:
                break
            # Wykonanie zwykłej pracy mogło odblokować starszą II instancję.
            break
        if pass_executed <= TOLERANCJA:
            break
    return fsum(executed_parts)


def _przyrost_zakonczenia(completion: Completion, month: int) -> float:
    """Zwraca nowy ułamek grupy, który przeszedł wszystkie wymagane etapy.

    Ułamki opisują w pełni zakończone oczekiwane sprawy, a nie częściową zapłatę
    za pojedynczą niezakończoną sprawę. Termin nominalny nadal blokuje wynik.
    """
    if month < completion.nominal_month or completion.recognized_fraction >= 1.0:
        return 0.0
    progress = min(
        (
            1.0 if isclose(completion.stage_executed_minutes[stage], total, rel_tol=1e-12, abs_tol=0.0)
            else max(0.0, min(completion.stage_executed_minutes[stage] / total, 1.0))
            for stage, total in completion.stage_total_minutes.items()
            if total > 0.0
        ),
        default=1.0,
    )
    increment = max(progress - completion.recognized_fraction, 0.0)
    completion.recognized_fraction += increment
    return increment


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
    outcome_lags = (
        (shares["zakonczone_ugoda"], czas["miesiace_do_ugody"]),
        (shares["bez_ugody"] - ii_share, czas["miesiace_do_wyroku_i"]),
        (ii_share, czas["miesiace_do_wyroku_i"] + czas["miesiace_wyrok_i_do_ii"]),
    )
    active_lags = [lag for share, lag in outcome_lags if share > TOLERANCJA]
    if not active_lags:
        return None
    return 1 + max(active_lags) + czas["opoznienie_platnosci_miesiace"]


def podsumuj_finanse_kontraktu(rows: list[dict]) -> dict:
    """Jawne uzgodnienie całego horyzontu; wszystkie składniki pochodzą z miesięcy."""
    columns = ("Koszt wynagrodzeń EH", "Koszt wynagrodzeń ugód", "Koszty ogólne aktywnych spraw",
               "Koszt sekretariatu aktywnych spraw", "Łączny koszt miesięczny", "Przychód razem",
               "Wynik miesięczny przed podatkiem", "Sprawy naliczające koszt w miesiącu")
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
) -> dict:
    """Symuluje ciągły napływ, kolejkę pracy, przychody i koszt obsady."""
    if parametry is None:
        parametry = domyslne_parametry()
    czas = _parametry_czasowe(parametry_czasowe)
    waliduj_parametry(parametry)
    lifecycle = _dane_przeplywu(parametry)
    capacity = oblicz_pojemnosc_miesieczna(parametry, lifecycle, pracownicy=pracownicy)
    costs = _koszty_kontraktu(koszty_kontraktu)
    horizon = czas["horyzont_miesiace"]
    monthly_inflow = miesieczny_naplyw(lifecycle["ogolem"]["liczba_spraw"])
    due_packets: dict[int, list[WorkPacket]] = defaultdict(list)
    completions: list[Completion] = []
    queues = {role: deque() for role in ROLE}
    pending_ii: list[WorkPacket] = []
    payments: dict[int, dict[str, float]] = defaultdict(
        lambda: {"ugoda": 0.0, "wyrok": 0.0}
    )
    cohort_validations = []
    rows = []
    cumulative_inflow = 0.0
    cumulative_completed = 0.0
    cumulative_result = 0.0
    completed_delay_weight = 0.0
    completed_cases_for_delay = 0.0
    maximum_capacity_delay = 0
    total_due_minutes = 0.0
    total_executed_minutes = 0.0

    for month in range(1, horizon + 1):
        billable_active_cases = max(cumulative_inflow - cumulative_completed, 0.0) + monthly_inflow
        cohort_stats = _dodaj_kohorte(
            month, lifecycle, parametry, czas, due_packets, completions
        )
        cohort_validations.append(cohort_stats)
        cumulative_inflow += monthly_inflow

        planned_packets = due_packets.pop(month, [])
        pending_ii.extend(p for p in planned_packets if p.stage == "ii_instancja")
        new_packets = [p for p in planned_packets if p.stage != "ii_instancja"]
        role_work = {}
        # Najpierw ugody, potem EH: I instancja uwzględnia też wymaganą pracę ugód.
        for role in ("UGODY", "EH"):
            queue = queues[role]
            start = fsum(p.minutes_remaining for bucket in queue for p in bucket)
            packets = [p for p in new_packets if p.role == role]
            if role == "EH":
                packets += _uwolnij_ii(pending_ii, completions, month)
            new = fsum(p.minutes_remaining for p in packets)
            _dolacz_do_kolejki(queue, packets)
            available = capacity["role"][role]["netto_minuty"]
            executed = _wykonaj_prace(queue, completions, available)
            if role == "EH":
                # Zwykła praca wykonana teraz może odblokować II instancję
                # jeszcze w tym miesiącu. Koszt i limit godzin nie zmieniają się.
                released = _uwolnij_ii(pending_ii, completions, month)
                new += fsum(p.minutes_remaining for p in released)
                _dolacz_do_kolejki(queue, released)
                executed += _wykonaj_prace(queue, completions, max(available - executed, 0.0))
            end = fsum(p.minutes_remaining for bucket in queue for p in bucket)
            if not isclose(start + new - executed, end, rel_tol=1e-10, abs_tol=1e-6):
                raise RuntimeError(f"Kolejka {role} nie zachowuje minut.")
            role_work[role] = {"start": start, "new": new, "executed": executed, "end": end}
        backlog_start_minutes = fsum(w["start"] for w in role_work.values())
        new_due_minutes = fsum(w["new"] for w in role_work.values())
        executed_minutes = fsum(w["executed"] for w in role_work.values())
        total_available_work_minutes = backlog_start_minutes + new_due_minutes
        total_due_minutes += new_due_minutes
        total_executed_minutes += executed_minutes
        direct_capacity = capacity["pojemnosc_na_sprawy_minuty"]

        settlements = 0.0
        first_instance_endings = 0.0
        second_instance_endings = 0.0
        for completion in completions:
            increment = _przyrost_zakonczenia(completion, month)
            if increment > 0.0:
                completed_cases = completion.cases * increment
                cumulative_completed += completed_cases
                capacity_delay = month - completion.nominal_month
                completed_delay_weight += capacity_delay * completed_cases
                completed_cases_for_delay += completed_cases
                maximum_capacity_delay = max(maximum_capacity_delay, capacity_delay)
                if completion.outcome == "ugoda":
                    settlements += completed_cases
                    revenue_type = "ugoda"
                elif completion.outcome == "i":
                    first_instance_endings += completed_cases
                    revenue_type = "wyrok"
                else:
                    second_instance_endings += completed_cases
                    revenue_type = "wyrok"
                payment_month = month + czas["opoznienie_platnosci_miesiace"]
                payments[payment_month][revenue_type] += completion.revenue * increment

        settlement_revenue = payments[month]["ugoda"]
        judgment_revenue = payments[month]["wyrok"]
        revenue = settlement_revenue + judgment_revenue
        overhead_cost = billable_active_cases * costs["ogolne_na_aktywna_sprawe"]
        secretariat_cost = billable_active_cases * costs["sekretariat_na_aktywna_sprawe"]
        wage_cost = capacity["miesieczny_koszt_wynagrodzen"]
        operation_cost = wage_cost + overhead_cost + secretariat_cost
        monthly_result = revenue - operation_cost
        cumulative_result += monthly_result
        backlog_end_minutes_month = fsum(
            packet.minutes_remaining for queue in queues.values() for bucket in queue for packet in bucket
        )
        if not isclose(
            backlog_start_minutes + new_due_minutes - executed_minutes,
            backlog_end_minutes_month,
            rel_tol=1e-10,
            abs_tol=1e-6,
        ):
            raise RuntimeError("Miesięczne rozliczenie backlogu nie jest domknięte.")
        used_minutes = capacity["czynnosci_dzienne_minuty"] + executed_minutes
        if used_minutes > capacity["pojemnosc_brutto_minuty"] + TOLERANCJA:
            raise RuntimeError("Wykonano pracę ponad limit płatnych godzin FTE.")
        unused_minutes = max(capacity["pojemnosc_brutto_minuty"] - used_minutes, 0.0)
        utilization = (
            used_minutes / capacity["pojemnosc_brutto_minuty"] * 100
            if capacity["pojemnosc_brutto_minuty"] > TOLERANCJA
            else None
        )
        active_cases = max(cumulative_inflow - cumulative_completed, 0.0)
        rows.append(
            {
                "Miesiąc": month,
                "Nowe sprawy": monthly_inflow,
                "II instancja oczekująca na pracę I (h)": fsum(p.minutes_remaining for p in pending_ii) / 60,
                "Aktywne sprawy": active_cases,
                "Aktywne sprawy na koniec miesiąca": active_cases,
                "Sprawy naliczające koszt w miesiącu": billable_active_cases,
                **{f"{label} {role} (h)": role_work[role][key] / 60
                   for role in ROLE for label, key in (("Backlog początek", "start"), ("Nowa praca", "new"), ("Wykonana praca", "executed"), ("Backlog", "end"))},
                **{f"Pojemność {role} (h)": capacity["role"][role]["netto_minuty"] / 60 for role in ROLE},
                "Ugody zakończone": settlements,
                "Zakończenia po I instancji": first_instance_endings,
                "Zakończenia po II instancji": second_instance_endings,
                "Przychód z ugód": settlement_revenue,
                "Przychód z wyroków": judgment_revenue,
                "Przychód razem": revenue,
                "Pojemność brutto (h)": capacity["pojemnosc_brutto_minuty"] / 60,
                "Czynności dzienne (h)": capacity["czynnosci_dzienne_minuty"] / 60,
                "Dostępna pojemność na sprawy (h)": direct_capacity / 60,
                "Backlog na początku (h)": backlog_start_minutes / 60,
                "Nowa praca (h)": new_due_minutes / 60,
                "Praca oczekująca (h)": total_available_work_minutes / 60,
                "Wykonana praca (h)": executed_minutes / 60,
                "Wykorzystane płatne godziny": used_minutes / 60,
                "Backlog na koniec (h)": backlog_end_minutes_month / 60,
                "Wykorzystanie pojemności (%)": utilization,
                "Niewykorzystana pojemność (h)": unused_minutes / 60,
                "Koszt wynagrodzeń EH": capacity["role"]["EH"]["wynagrodzenia"],
                "Koszt wynagrodzeń ugód": capacity["role"]["UGODY"]["wynagrodzenia"],
                "Koszty ogólne aktywnych spraw": overhead_cost,
                "Koszt sekretariatu aktywnych spraw": secretariat_cost,
                "Miesięczny koszt wynagrodzeń": wage_cost,
                "Łączny koszt miesięczny": operation_cost,
                "Wynik miesięczny przed podatkiem": monthly_result,
                "Wynik skumulowany przed podatkiem": cumulative_result,
            }
        )

    backlog_end_minutes = rows[-1]["Backlog na koniec (h)"] * 60
    if not isclose(
        total_executed_minutes + backlog_end_minutes,
        total_due_minutes,
        rel_tol=1e-10,
        abs_tol=1e-6,
    ):
        raise RuntimeError("Kolejka pracy nie zachowuje wszystkich należnych minut.")
    if not isclose(
        cumulative_inflow - cumulative_completed,
        rows[-1]["Aktywne sprawy"],
        rel_tol=1e-10,
        abs_tol=1e-6,
    ):
        raise RuntimeError("Liczba aktywnych spraw nie uzgadnia się z przepływem.")

    future_minutes = fsum(p.minutes_remaining for bucket in due_packets.values() for p in bucket)
    blocked_ii_minutes = fsum(p.minutes_remaining for p in pending_ii)
    future_minutes += blocked_ii_minutes
    all_cohort_minutes = fsum(c["direct_minutes"] for c in cohort_validations)
    if not isclose(total_executed_minutes + backlog_end_minutes + future_minutes,
                   all_cohort_minutes, rel_tol=1e-10, abs_tol=1e-6):
        raise RuntimeError("Praca wykonana, zaległa i przyszła nie uzgadnia się z kohortami.")

    cohort_reference = {
        "przychod": lifecycle["ogolem"]["przychod"] / 12,
        "bezposrednie_minuty": lifecycle["bezposrednie_minuty_spraw"] / 12,
        "liczba_spraw": lifecycle["ogolem"]["liczba_spraw"] / 12,
    }
    if cohort_validations:
        first_cohort = cohort_validations[0]
        for name, built_key in (
            ("przychod", "revenue"),
            ("bezposrednie_minuty", "direct_minutes"),
            ("liczba_spraw", "cases"),
        ):
            if not isclose(
                first_cohort[built_key],
                cohort_reference[name],
                rel_tol=1e-10,
                abs_tol=1e-6,
            ):
                raise RuntimeError(f"Miesięczna kohorta nie uzgadnia pola {name}.")

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
                and blisko(row["Sprawy naliczające koszt w miesiącu"], last_twelve[0]["Sprawy naliczające koszt w miesiącu"])
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
    current_capacity_delay = max(
        (horizon - bucket[0].due_month for queue in queues.values() for bucket in queue), default=0
    )
    startup_deficit = any(row["Wynik skumulowany przed podatkiem"] < -TOLERANCJA
                          for row in rows[:min(nominal_maturity_month or horizon, len(rows))])

    return {
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
