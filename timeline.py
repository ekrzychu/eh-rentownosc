"""Ciągły, pojemnościowy model ekonomii operacyjnej w czasie.

``oblicz_model`` pozostaje jedynym źródłem ekonomii lifecycle kohorty
referencyjnej. Ten moduł tworzy co miesiąc proporcjonalną kohortę, układa jej
pracę w kolejce FIFO i pobiera pełny koszt dostarczonej obsady. Koszt okresowy
nie jest zatem uzgadniany z kosztem pracy zużytej przez pojedynczą kohortę.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from math import ceil, fsum, isclose

from config import wczytaj_defaults

from model import (
    MINUTY_DNIA_PRACY,
    SCIEZKI_BEZ_UGODY,
    SCIEZKI_UGODOWE,
    domyslne_parametry,
    oblicz_model,
    waliduj_parametry,
)


GODZINY_ETATU_MIESIECZNIE = wczytaj_defaults()["organizacja"]["godziny_etatu_miesiecznie"]
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


def oblicz_pojemnosc_miesieczna(
    parametry: dict, lifecycle: dict | None = None
) -> dict:
    """Oblicza dostarczoną pojemność, koszt i stabilność systemu."""
    waliduj_parametry(parametry)
    if lifecycle is None:
        lifecycle = oblicz_model(parametry)
    pracownicy = parametry["liczba_pracownikow"]
    dzienne_na_pracownika = sum(parametry["codzienne_czynnosci"].values())
    brutto_godziny = pracownicy * GODZINY_ETATU_MIESIECZNIE
    brutto_minuty = brutto_godziny * 60
    ekwiwalent_dni_miesiecznie = GODZINY_ETATU_MIESIECZNIE / (MINUTY_DNIA_PRACY / 60)
    dzienne_godziny_na_pracownika = (
        ekwiwalent_dni_miesiecznie * dzienne_na_pracownika / 60
    )
    dzienne_minuty = (
        pracownicy * dzienne_godziny_na_pracownika * 60
    )
    netto_minuty = max(brutto_minuty - dzienne_minuty, 0.0)
    popyt_minuty = lifecycle["bezposrednie_minuty_spraw"] / 12
    koszt_godziny_zasobu = (
        parametry["koszt_staly_na_godzine"]
        + parametry["wynagrodzenie_pracownika_na_godzine"]
    )
    miesieczny_narzut_ogolny = (
        brutto_godziny * parametry["koszt_staly_na_godzine"]
    )
    miesieczne_wynagrodzenia = (
        brutto_godziny * parametry["wynagrodzenie_pracownika_na_godzine"]
    )
    miesieczny_koszt_obsady = miesieczny_narzut_ogolny + miesieczne_wynagrodzenia
    tolerancja = max(TOLERANCJA, popyt_minuty * 1e-9)
    if popyt_minuty < netto_minuty - tolerancja:
        status = "Stabilna"
    elif abs(popyt_minuty - netto_minuty) <= tolerancja:
        status = "Na granicy"
    else:
        status = "Niewystarczająca"
    return {
        "pojemnosc_brutto_minuty": brutto_minuty,
        "czynnosci_dzienne_minuty": dzienne_minuty,
        "pojemnosc_na_sprawy_minuty": netto_minuty,
        "miesieczny_popyt_minuty": popyt_minuty,
        "godziny_etatu_miesiecznie": GODZINY_ETATU_MIESIECZNIE,
        "ekwiwalent_dni_pracy_miesiecznie": ekwiwalent_dni_miesiecznie,
        "czynnosci_dzienne_na_pracownika_godziny": dzienne_godziny_na_pracownika,
        "koszt_zasobu_na_godzine": koszt_godziny_zasobu,
        "koszt_jednego_fte_miesiecznie": (
            GODZINY_ETATU_MIESIECZNIE * koszt_godziny_zasobu
        ),
        "miesieczny_narzut_kosztow_ogolnych": miesieczny_narzut_ogolny,
        "miesieczny_koszt_wynagrodzen": miesieczne_wynagrodzenia,
        "miesieczny_koszt_obsady": miesieczny_koszt_obsady,
        "status_pojemnosci": status,
        "brak_pojemnosci_na_sprawy": dzienne_minuty >= brutto_minuty - TOLERANCJA,
    }


def minimalna_liczba_pracownikow_dla_stabilnosci(
    parametry: dict, lifecycle: dict | None = None
) -> int | None:
    """Zwraca najmniejszą całkowitą obsadę bez strukturalnego deficytu mocy."""
    waliduj_parametry(parametry)
    if lifecycle is None:
        lifecycle = oblicz_model(parametry)
    popyt = lifecycle["bezposrednie_minuty_spraw"] / 12
    if popyt <= TOLERANCJA:
        return 0
    dzienne = sum(parametry["codzienne_czynnosci"].values())
    netto_na_pracownika = (
        GODZINY_ETATU_MIESIECZNIE * 60
        - GODZINY_ETATU_MIESIECZNIE / (MINUTY_DNIA_PRACY / 60) * dzienne
    )
    if netto_na_pracownika <= TOLERANCJA:
        return None
    return max(1, ceil((popyt - TOLERANCJA) / netto_na_pracownika))


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
    )
    due_packets[due_month].append(packet)
    completion = completions[completion_id]
    completion.stage_total_minutes[stage] = (
        completion.stage_total_minutes.get(stage, 0.0) + minutes_value
    )
    completion.stage_executed_minutes.setdefault(stage, 0.0)
    cohort_stats["direct_minutes"] += minutes_value


def _rozloz_pakiet(
    due_packets: dict[int, list[WorkPacket]],
    completions: list[Completion],
    completion_id: int,
    start_month: int,
    end_month: int,
    cohort_month: int,
    path: str,
    stage: str,
    minutes_value: float,
    cohort_stats: dict,
) -> None:
    number_of_months = end_month - start_month + 1
    if number_of_months <= 0:
        raise ValueError("Nieprawidłowy przedział alokacji pracy.")
    part = minutes_value / number_of_months
    for due_month in range(start_month, end_month + 1):
        _dodaj_pakiet(
            due_packets,
            completions,
            completion_id,
            due_month,
            cohort_month,
            path,
            stage,
            part,
            cohort_stats,
        )


def _dodaj_kohorte(
    cohort_month: int,
    lifecycle: dict,
    parametry: dict,
    czas: dict,
    due_packets: dict[int, list[WorkPacket]],
    completions: list[Completion],
) -> dict:
    """Tworzy miesięczną kohortę jako 1/12 kohorty referencyjnej."""
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
                due_packets, completions, completion_id, nominal,
                cohort_month, path, "zawarcie_ugody",
                cases * settlement_minutes, cohort_stats,
            )
            _rozloz_pakiet(
                due_packets, completions, completion_id, cohort_month, nominal,
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
                    attempt_month = min(
                        cohort_month + czas["miesiace_do_ugody"], first_judgment
                    )
                    _dodaj_pakiet(
                        due_packets, completions, completion_id, attempt_month,
                        cohort_month, branch_path, "nieudana_proba_ugody",
                        cases * failed_offer_minutes, cohort_stats,
                    )
                process_start = (
                    cohort_month + 1
                    if czas["miesiace_do_wyroku_i"] > 0
                    else first_judgment
                )
                _rozloz_pakiet(
                    due_packets, completions, completion_id, process_start,
                    first_judgment, cohort_month, branch_path, "proces",
                    cases * process_minutes, cohort_stats,
                )
                _rozloz_pakiet(
                    due_packets, completions, completion_id, cohort_month, nominal,
                    cohort_month, branch_path, "praca_dodatkowa_p",
                    cases * extra_minutes, cohort_stats,
                )
                if second_instance:
                    second_start = (
                        first_judgment + 1
                        if czas["miesiace_wyrok_i_do_ii"] > 0
                        else first_judgment
                    )
                    _rozloz_pakiet(
                        due_packets, completions, completion_id, second_start,
                        nominal, cohort_month, branch_path, "ii_instancja",
                        cases * second_instance_minutes, cohort_stats,
                    )
    return cohort_stats


def _wykonaj_prace(
    queue: deque[list[WorkPacket]],
    completions: list[Completion],
    available_minutes: float,
) -> float:
    """FIFO między datami; równy ułamek pozostałej pracy wewnątrz daty."""
    executed_parts = []
    remaining_capacity = available_minutes
    while queue and remaining_capacity > TOLERANCJA:
        # Najstarszy miesiąc wymagalności ma pierwszeństwo przed kolejnym.
        bucket = queue[0]
        remaining_work = fsum(packet.minutes_remaining for packet in bucket)
        fraction = min(remaining_capacity / remaining_work, 1.0)
        bucket_executed = []
        # Każdy pakiet tej samej daty dostaje proporcjonalny udział pojemności.
        for packet in bucket:
            executed = packet.minutes_remaining * fraction
            packet.minutes_remaining -= executed
            completion = completions[packet.completion_id]
            completion.stage_executed_minutes[packet.stage] += executed
            bucket_executed.append(executed)
        executed = fsum(bucket_executed)
        executed_parts.append(executed)
        remaining_capacity = max(remaining_capacity - executed, 0.0)
        if fraction == 1.0:
            queue.popleft()
        else:
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
    liczba_spraw: float,
    wynik_jednostkowy_przed_podatkiem: float,
    liczba_pracownikow: int,
    minimalna_stabilna_obsada: int | None,
    wynik_miesieczny_minimalnej_stabilnej_obsady: float | None,
    wynik_miesieczny_biezacej_obsady: float | None,
    status_pojemnosci: str,
) -> dict:
    """Klasyfikuje kontrakt na podstawie wykonalnej ekonomiki obsady."""
    if status_pojemnosci not in {"Stabilna", "Na granicy", "Niewystarczająca"}:
        raise ValueError("Nieznany status pojemności.")

    ekonomika_sprawy_dodatnia = wynik_jednostkowy_przed_podatkiem > TOLERANCJA
    rentowna_stabilna_obsada = (
        minimalna_stabilna_obsada is not None
        and wynik_miesieczny_minimalnej_stabilnej_obsady is not None
        and wynik_miesieczny_minimalnej_stabilnej_obsady > TOLERANCJA
    )

    if liczba_spraw <= TOLERANCJA:
        etykieta = "Brak napływu spraw"
    elif not ekonomika_sprawy_dodatnia:
        etykieta = "Nierentowna ekonomika sprawy"
    elif not rentowna_stabilna_obsada:
        etykieta = "Brak rentownej stabilnej obsady"
    elif liczba_pracownikow < minimalna_stabilna_obsada:
        etykieta = "Rentowny, wymaga większej obsady"
    elif (
        wynik_miesieczny_biezacej_obsady is not None
        and wynik_miesieczny_biezacej_obsady > TOLERANCJA
    ):
        etykieta = "Rentowny i stabilny"
    else:
        etykieta = "Stabilny, ale obsada zbyt kosztowna"

    return {
        "etykieta": etykieta,
        "ekonomika_sprawy_dodatnia": ekonomika_sprawy_dodatnia,
        "status_pojemnosci": status_pojemnosci,
        "minimalna_stabilna_obsada": minimalna_stabilna_obsada,
        "wynik_miesieczny_minimalnej_stabilnej_obsady": (
            wynik_miesieczny_minimalnej_stabilnej_obsady
        ),
        "wynik_miesieczny_biezacej_obsady": (
            wynik_miesieczny_biezacej_obsady
            if status_pojemnosci != "Niewystarczająca"
            and minimalna_stabilna_obsada is not None
            and liczba_pracownikow >= minimalna_stabilna_obsada
            else None
        ),
    }


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


def oblicz_model_czasowy(
    parametry: dict | None = None, parametry_czasowe: dict | None = None
) -> dict:
    """Symuluje ciągły napływ, kolejkę pracy, przychody i koszt obsady."""
    if parametry is None:
        parametry = domyslne_parametry()
    czas = _parametry_czasowe(parametry_czasowe)
    lifecycle = oblicz_model(parametry)
    capacity = oblicz_pojemnosc_miesieczna(parametry, lifecycle)
    minimum_staff = minimalna_liczba_pracownikow_dla_stabilnosci(
        parametry, lifecycle
    )
    horizon = czas["horyzont_miesiace"]
    monthly_inflow = miesieczny_naplyw(lifecycle["ogolem"]["liczba_spraw"])
    due_packets: dict[int, list[WorkPacket]] = defaultdict(list)
    completions: list[Completion] = []
    queue: deque[list[WorkPacket]] = deque()
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
        cohort_stats = _dodaj_kohorte(
            month, lifecycle, parametry, czas, due_packets, completions
        )
        cohort_validations.append(cohort_stats)
        cumulative_inflow += monthly_inflow

        new_packets = due_packets.pop(month, [])
        backlog_start_minutes = fsum(
            packet.minutes_remaining for bucket in queue for packet in bucket
        )
        new_due_minutes = fsum(packet.minutes_remaining for packet in new_packets)
        total_available_work_minutes = backlog_start_minutes + new_due_minutes
        total_due_minutes += new_due_minutes
        if new_packets:
            queue.append(new_packets)
        direct_capacity = capacity["pojemnosc_na_sprawy_minuty"]
        executed_minutes = _wykonaj_prace(queue, completions, direct_capacity)
        total_executed_minutes += executed_minutes

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
        overhead_cost = capacity["miesieczny_narzut_kosztow_ogolnych"]
        wage_cost = capacity["miesieczny_koszt_wynagrodzen"]
        operation_cost = capacity["miesieczny_koszt_obsady"]
        monthly_result = revenue - operation_cost
        cumulative_result += monthly_result
        backlog_end_minutes_month = fsum(
            packet.minutes_remaining for bucket in queue for packet in bucket
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
                "Aktywne sprawy": active_cases,
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
                "Koszt niewykorzystanej pojemności": (
                    unused_minutes
                    / 60
                    * capacity["koszt_zasobu_na_godzine"]
                ),
                "Miesięczny narzut kosztów ogólnych": overhead_cost,
                "Miesięczny koszt wynagrodzeń": wage_cost,
                "Miesięczny koszt obsady": operation_cost,
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
    current_staff_monthly_result = (
        target_monthly_revenue - capacity["miesieczny_koszt_obsady"]
        if capacity["status_pojemnosci"] != "Niewystarczająca"
        and minimum_staff is not None
        and parametry["liczba_pracownikow"] >= minimum_staff
        else None
    )
    minimum_team_monthly_cost = (
        minimum_staff
        * GODZINY_ETATU_MIESIECZNIE
        * capacity["koszt_zasobu_na_godzine"]
        if minimum_staff is not None
        else None
    )
    mature_result_at_minimum_staff = (
        target_monthly_revenue - minimum_team_monthly_cost
        if minimum_team_monthly_cost is not None
        else None
    )
    case_count = lifecycle["ogolem"]["liczba_spraw"]
    unit_result = (
        lifecycle["ogolem"]["wynik_przed_podatkiem"] / case_count
        if case_count
        else 0.0
    )
    contract_status = klasyfikuj_status_kontraktu(
        liczba_spraw=case_count,
        wynik_jednostkowy_przed_podatkiem=unit_result,
        liczba_pracownikow=parametry["liczba_pracownikow"],
        minimalna_stabilna_obsada=minimum_staff,
        wynik_miesieczny_minimalnej_stabilnej_obsady=(
            mature_result_at_minimum_staff
        ),
        wynik_miesieczny_biezacej_obsady=current_staff_monthly_result,
        status_pojemnosci=capacity["status_pojemnosci"],
    )
    last_twelve = rows[-12:] if len(rows) >= 12 else []
    mature_revenue = (
        sum(row["Przychód razem"] for row in last_twelve) / 12
        if last_twelve else None
    )
    mature_demand = (
        sum(row["Nowa praca (h)"] * 60 for row in last_twelve) / 12
        if last_twelve else None
    )
    maturity_reached = (
        nominal_maturity_month is not None
        and capacity["status_pojemnosci"] != "Niewystarczająca"
        and horizon >= nominal_maturity_month + 11
        and mature_revenue is not None
        and mature_demand is not None
        and isclose(mature_revenue, target_monthly_revenue, rel_tol=1e-9, abs_tol=1e-6)
        and isclose(mature_demand, target_monthly_demand, rel_tol=1e-9, abs_tol=1e-6)
    )
    steady_monthly_result = (
        mature_revenue - capacity["miesieczny_koszt_obsady"]
        if maturity_reached and mature_revenue is not None
        else None
    )
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
    backlog_months = (
        backlog_end_minutes / capacity["pojemnosc_na_sprawy_minuty"]
        if capacity["pojemnosc_na_sprawy_minuty"] > TOLERANCJA
        else (0.0 if backlog_end_minutes <= TOLERANCJA else None)
    )
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
    current_capacity_delay = (
        max(horizon - queue[0][0].due_month, 0) if queue else 0
    )
    lifecycle_resource_hours = lifecycle["laczne_godziny_zasobu_lifecycle"]
    supplied_annual_hours = capacity["pojemnosc_brutto_minuty"] / 60 * 12
    annual_capacity_balance = supplied_annual_hours - lifecycle_resource_hours
    unused_capacity_cost_total = sum(
        row["Koszt niewykorzystanej pojemności"] for row in rows
    )
    startup_deficit = any(
        row["Wynik skumulowany przed podatkiem"] < -TOLERANCJA
        for row in rows[: min(nominal_maturity_month or horizon, len(rows))]
    )
    lifecycle_total_cost = lifecycle["koszt_lifecycle_razem"]
    temporal_annual_cost = capacity["miesieczny_koszt_obsady"] * 12
    reconciliation_difference = temporal_annual_cost - lifecycle_total_cost
    expected_reconciliation_difference = (
        annual_capacity_balance * capacity["koszt_zasobu_na_godzine"]
    )
    if not isclose(
        reconciliation_difference,
        expected_reconciliation_difference,
        rel_tol=1e-10,
        abs_tol=1e-6,
    ):
        raise RuntimeError("Koszty lifecycle i czasowe nie uzgadniają się.")

    return {
        "parametry_czasowe": czas,
        "tabela_miesieczna": rows,
        "pojemnosc": {
            **capacity,
            "minimalna_liczba_pracownikow_dla_stabilnosci": minimum_staff,
            "srednie_wykorzystanie_percent": average_utilization,
            "biezace_wykorzystanie_percent": current_utilization,
            "ostatnie_12_miesiecy_wykorzystanie_percent": recent_utilization,
        },
        "kpi": {
            "status_kontraktu": contract_status["etykieta"],
            "status_kontraktu_skladniki": contract_status,
            "wynik_miesieczny_biezacej_obsady": current_staff_monthly_result,
            "wynik_miesieczny_minimalnej_stabilnej_obsady": (
                mature_result_at_minimum_staff
            ),
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
            "koszt_niewykorzystanej_pojemnosci_horyzont": unused_capacity_cost_total,
            "strukturalny_niedobor_pojemnosci": (
                capacity["status_pojemnosci"] == "Niewystarczająca"
            ),
            "marza_lifecycle_przed_podatkiem": lifecycle["ogolem"][
                "marza_przed_podatkiem"
            ],
            "roczny_przychod_lifecycle": lifecycle["ogolem"]["przychod"],
            "roczne_wymagane_godziny_zasobu": lifecycle_resource_hours,
            "dostarczane_godziny_zespolu_rocznie": supplied_annual_hours,
            "bilans_pojemnosci_rocznie_godziny": annual_capacity_balance,
            "wynik_miesieczny_przy_minimalnej_obsadzie": (
                mature_result_at_minimum_staff
            ),
            "koszt_lifecycle_roczny": lifecycle_total_cost,
            "koszt_operacji_czasowy_roczny": temporal_annual_cost,
            "roznica_kosztu_czasowy_minus_lifecycle": reconciliation_difference,
            "koszt_niewykorzystanej_pojemnosci_rocznie": max(
                expected_reconciliation_difference, 0.0
            ),
        },
        "walidacja": {
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
            "praca_wykonana_minuty": total_executed_minutes,
            "backlog_minuty": backlog_end_minutes,
            "laczny_naplyw_spraw": cumulative_inflow,
            "laczne_zakonczenia_spraw": cumulative_completed,
            "aktywne_sprawy": rows[-1]["Aktywne sprawy"],
        },
    }


def porownaj_obsade(
    parametry: dict,
    parametry_czasowe: dict | None = None,
    maksymalna_liczba_pracownikow: int | None = None,
) -> list[dict]:
    """Porównuje warianty obsady bez automatycznego wyboru najlepszego."""
    czas = _parametry_czasowe(parametry_czasowe)
    lifecycle = oblicz_model(parametry)
    minimum = minimalna_liczba_pracownikow_dla_stabilnosci(parametry, lifecycle)
    if maksymalna_liczba_pracownikow is None:
        maksymalna_liczba_pracownikow = max(
            parametry["liczba_pracownikow"] + 3,
            (minimum + 2) if minimum is not None else 5,
            1,
        )
    maksymalna_liczba_pracownikow = min(max(maksymalna_liczba_pracownikow, 1), 20)
    rows = []
    for employees in range(1, maksymalna_liczba_pracownikow + 1):
        scenario_parameters = {**parametry, "liczba_pracownikow": employees}
        result = oblicz_model_czasowy(scenario_parameters, czas)
        first_positive = result["kpi"]["pierwszy_dodatni_miesiac"]
        rows.append(
            {
                "Liczba pracowników": employees,
                "Pojemność brutto (h/mies.)": result["pojemnosc"][
                    "pojemnosc_brutto_minuty"
                ] / 60,
                "Pojemność na sprawy (h/mies.)": result["pojemnosc"][
                    "pojemnosc_na_sprawy_minuty"
                ] / 60,
                "Status pojemności": result["pojemnosc"]["status_pojemnosci"],
                "Wykorzystanie": result["pojemnosc"][
                    "ostatnie_12_miesiecy_wykorzystanie_percent"
                ],
                "Backlog (h)": result["podsumowanie"][
                    "backlog_koniec_godziny"
                ],
                "Miesięczny narzut kosztów ogólnych": result["pojemnosc"][
                    "miesieczny_narzut_kosztow_ogolnych"
                ],
                "Miesięczne wynagrodzenia": result["pojemnosc"][
                    "miesieczny_koszt_wynagrodzen"
                ],
                "Miesięczny koszt obsady": result["pojemnosc"][
                    "miesieczny_koszt_obsady"
                ],
                "Pierwszy dodatni miesiąc": (
                    f"Miesiąc {first_positive}" if first_positive is not None else "Brak"
                ),
                "Break-even": result["kpi"]["break_even_skumulowany"],
                "Dojrzały wynik miesięczny": result["kpi"][
                    "wynik_miesieczny_w_stanie_stabilnym"
                ],
            }
        )
    return rows
