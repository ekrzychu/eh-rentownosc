"""Ciągły, pojemnościowy model ekonomii operacyjnej w czasie.

``oblicz_model`` pozostaje jedynym źródłem ekonomii lifecycle kohorty
referencyjnej. Ten moduł tworzy co miesiąc proporcjonalną kohortę, układa jej
pracę w kolejce FIFO i pobiera pełny koszt dostarczonej obsady. Koszt okresowy
nie jest zatem uzgadniany z kosztem pracy zużytej przez pojedynczą kohortę.
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from math import ceil, isclose

from model import MINUTY_DNIA_PRACY, domyslne_parametry, oblicz_model


SCIEZKI_UGODOWE = ("automatyczne_ramy", "zawarte_poza_ramami")
SCIEZKI_BEZ_UGODY = (
    "kategoryczna_odmowa",
    "brak_szans",
    "brak_ugody_poza_ramami",
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


@dataclass
class Completion:
    """Oczekiwany wynik ścieżki i zależny od wykonania pracy przychód."""

    cohort_month: int
    path: str
    outcome: str
    nominal_month: int
    cases: float
    revenue: float
    remaining_minutes: float = 0.0
    completed: bool = False
    actual_month: int | None = None


def domyslne_parametry_czasowe() -> dict:
    """Zwraca testowe założenia procesu dla ciągłej symulacji."""
    return {
        "miesiace_do_ugody": 6,
        "miesiace_do_wyroku_i": 9,
        "miesiace_wyrok_i_do_ii": 6,
        "opoznienie_platnosci_miesiace": 0,
        "horyzont_miesiace": 60,
    }


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


def oblicz_pojemnosc_miesieczna(
    parametry: dict, lifecycle: dict | None = None
) -> dict:
    """Oblicza dostarczoną pojemność, koszt i stabilność systemu."""
    if lifecycle is None:
        lifecycle = oblicz_model(parametry)
    pracownicy = parametry["liczba_pracownikow"]
    dni_rocznie = parametry["liczba_dni_pracy_w_roku"]
    dzienne_na_pracownika = sum(parametry["codzienne_czynnosci"].values())
    brutto_minuty = pracownicy * dni_rocznie * MINUTY_DNIA_PRACY / 12
    dzienne_minuty = pracownicy * dni_rocznie * dzienne_na_pracownika / 12
    netto_minuty = max(brutto_minuty - dzienne_minuty, 0.0)
    popyt_minuty = lifecycle["bezposrednie_minuty_spraw"] / 12
    koszt_godziny = lifecycle["koszt_godziny"]
    koszt_zespolu = brutto_minuty / 60 * koszt_godziny
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
        "koszt_godziny": koszt_godziny,
        "miesieczny_koszt_zespolu": koszt_zespolu,
        "status_pojemnosci": status,
        "brak_pojemnosci_na_sprawy": dzienne_minuty >= brutto_minuty - TOLERANCJA,
    }


def minimalna_liczba_pracownikow_dla_stabilnosci(
    parametry: dict, lifecycle: dict | None = None
) -> int | None:
    """Zwraca najmniejszą całkowitą obsadę bez strukturalnego deficytu mocy."""
    if lifecycle is None:
        lifecycle = oblicz_model(parametry)
    popyt = lifecycle["bezposrednie_minuty_spraw"] / 12
    if popyt <= TOLERANCJA:
        return 0
    dni = parametry["liczba_dni_pracy_w_roku"]
    dzienne = sum(parametry["codzienne_czynnosci"].values())
    netto_na_pracownika = dni * (MINUTY_DNIA_PRACY - dzienne) / 12
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
    completions[completion_id].remaining_minutes += minutes_value
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
                if path == "brak_ugody_poza_ramami":
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


def _status_break_even(
    break_even: dict, capacity_status: str, steady_monthly_result: float | None
) -> str:
    if capacity_status == "Niewystarczająca":
        return "Brak trwałego break-even przy obecnej obsadzie"
    if break_even["status"] == "nie_osiagnieto":
        return "Nie osiągnięto w horyzoncie"
    sustainable = (
        capacity_status == "Stabilna"
        and steady_monthly_result is not None
        and steady_monthly_result > TOLERANCJA
    )
    if break_even["status"] == "od_poczatku":
        return "Rentowna od początku" if sustainable else "Wynik nietrwały"
    return "Break-even trwały" if sustainable else "Przecięcie nietrwałe"


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
    queue: deque[WorkPacket] = deque()
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
        backlog_start_minutes = sum(packet.minutes_remaining for packet in queue)
        new_due_minutes = sum(packet.minutes_remaining for packet in new_packets)
        total_available_work_minutes = backlog_start_minutes + new_due_minutes
        total_due_minutes += new_due_minutes
        queue.extend(new_packets)
        direct_capacity = capacity["pojemnosc_na_sprawy_minuty"]
        remaining_capacity = direct_capacity
        executed_minutes = 0.0
        while queue and remaining_capacity > TOLERANCJA:
            packet = queue[0]
            executed = min(packet.minutes_remaining, remaining_capacity)
            packet.minutes_remaining -= executed
            completions[packet.completion_id].remaining_minutes -= executed
            executed_minutes += executed
            remaining_capacity -= executed
            if packet.minutes_remaining <= TOLERANCJA:
                queue.popleft()
            else:
                break
        total_executed_minutes += executed_minutes

        settlements = 0.0
        first_instance_endings = 0.0
        second_instance_endings = 0.0
        for completion in completions:
            if (
                not completion.completed
                and completion.nominal_month <= month
                and completion.remaining_minutes <= TOLERANCJA
            ):
                completion.completed = True
                completion.actual_month = month
                cumulative_completed += completion.cases
                capacity_delay = month - completion.nominal_month
                completed_delay_weight += capacity_delay * completion.cases
                completed_cases_for_delay += completion.cases
                maximum_capacity_delay = max(maximum_capacity_delay, capacity_delay)
                if completion.outcome == "ugoda":
                    settlements += completion.cases
                    revenue_type = "ugoda"
                elif completion.outcome == "i":
                    first_instance_endings += completion.cases
                    revenue_type = "wyrok"
                else:
                    second_instance_endings += completion.cases
                    revenue_type = "wyrok"
                payment_month = month + czas["opoznienie_platnosci_miesiace"]
                payments[payment_month][revenue_type] += completion.revenue

        settlement_revenue = payments[month]["ugoda"]
        judgment_revenue = payments[month]["wyrok"]
        revenue = settlement_revenue + judgment_revenue
        team_cost = capacity["miesieczny_koszt_zespolu"]
        monthly_result = revenue - team_cost
        cumulative_result += monthly_result
        backlog_end_minutes_month = sum(
            packet.minutes_remaining for packet in queue
        )
        if not isclose(
            backlog_start_minutes + new_due_minutes - executed_minutes,
            backlog_end_minutes_month,
            rel_tol=1e-10,
            abs_tol=1e-6,
        ):
            raise RuntimeError("Miesięczne rozliczenie backlogu nie jest domknięte.")
        used_minutes = capacity["czynnosci_dzienne_minuty"] + executed_minutes
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
                "Backlog na koniec (h)": backlog_end_minutes_month / 60,
                "Wykorzystanie pojemności (%)": utilization,
                "Niewykorzystana pojemność (h)": unused_minutes / 60,
                "Koszt niewykorzystanej pojemności": (
                    unused_minutes / 60 * capacity["koszt_godziny"]
                ),
                "Koszt zespołu": team_cost,
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

    break_even = wyznacz_break_even(
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
    nominal_maturity_month = (
        1
        + max(
            czas["miesiace_do_ugody"],
            czas["miesiace_do_wyroku_i"],
            czas["miesiace_do_wyroku_i"] + czas["miesiace_wyrok_i_do_ii"],
        )
        + czas["opoznienie_platnosci_miesiace"]
    )
    target_monthly_revenue = lifecycle["ogolem"]["przychod"] / 12
    target_monthly_demand = lifecycle["bezposrednie_minuty_spraw"] / 12
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
        capacity["status_pojemnosci"] != "Niewystarczająca"
        and horizon >= nominal_maturity_month + 11
        and mature_revenue is not None
        and mature_demand is not None
        and isclose(mature_revenue, target_monthly_revenue, rel_tol=1e-9, abs_tol=1e-6)
        and isclose(mature_demand, target_monthly_demand, rel_tol=1e-9, abs_tol=1e-6)
    )
    steady_monthly_result = (
        mature_revenue - capacity["miesieczny_koszt_zespolu"]
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
    break_even_sustainability = _status_break_even(
        break_even, capacity["status_pojemnosci"], steady_monthly_result
    )
    if capacity["status_pojemnosci"] == "Niewystarczająca":
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
    cumulative_still_falling = (
        capacity["status_pojemnosci"] == "Niewystarczająca"
        and len(rows) >= 2
        and rows[-1]["Wynik skumulowany przed podatkiem"]
        < rows[-2]["Wynik skumulowany przed podatkiem"] - TOLERANCJA
    )
    current_capacity_delay = (
        max(horizon - queue[0].due_month, 0) if queue else 0
    )
    lifecycle_resource_hours = lifecycle["laczne_godziny"]
    supplied_annual_hours = capacity["pojemnosc_brutto_minuty"] / 60 * 12
    annual_capacity_balance = supplied_annual_hours - lifecycle_resource_hours
    minimum_team_monthly_cost = (
        minimum_staff
        * parametry["liczba_dni_pracy_w_roku"]
        * MINUTY_DNIA_PRACY
        / 12
        / 60
        * capacity["koszt_godziny"]
        if minimum_staff is not None
        else None
    )
    mature_result_at_minimum_staff = (
        target_monthly_revenue - minimum_team_monthly_cost
        if minimum_team_monthly_cost is not None
        else None
    )
    unused_capacity_cost_total = sum(
        row["Koszt niewykorzystanej pojemności"] for row in rows
    )
    startup_deficit = any(
        row["Wynik skumulowany przed podatkiem"] < -TOLERANCJA
        for row in rows[: min(nominal_maturity_month, len(rows))]
    )

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
            "break_even_skumulowany": break_even["etykieta"],
            "break_even_status": break_even["status"],
            "break_even_miesiac": break_even["miesiac"],
            "status_break_even": break_even_sustainability,
            "pierwszy_dodatni_miesiac": first_positive,
            "najglebszy_deficyt_skumulowany": deepest[
                "Wynik skumulowany przed podatkiem"
            ],
            "miesiac_najglebszego_deficytu": deepest["Miesiąc"],
            "najglebszy_deficyt_potwierdzony": minimum_confirmed,
            "wynik_skumulowany_na_koniec_horyzontu": rows[-1][
                "Wynik skumulowany przed podatkiem"
            ],
            "wynik_nadal_narasta": cumulative_still_falling,
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
                "Pojemność netto (h/mies.)": result["pojemnosc"][
                    "pojemnosc_na_sprawy_minuty"
                ] / 60,
                "Status pojemności": result["pojemnosc"]["status_pojemnosci"],
                "Średnie wykorzystanie": result["pojemnosc"][
                    "ostatnie_12_miesiecy_wykorzystanie_percent"
                ],
                "Backlog po horyzoncie (h)": result["podsumowanie"][
                    "backlog_koniec_godziny"
                ],
                "Miesięczny koszt zespołu": result["pojemnosc"][
                    "miesieczny_koszt_zespolu"
                ],
                "Pierwszy dodatni miesiąc": (
                    f"Miesiąc {first_positive}" if first_positive is not None else "Brak"
                ),
                "Break-even skumulowany": result["kpi"]["break_even_skumulowany"],
                "Wynik miesięczny w stanie stabilnym": result["kpi"][
                    "wynik_miesieczny_w_stanie_stabilnym"
                ],
            }
        )
    return rows
