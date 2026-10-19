"""Warstwa prezentacji ciągłego modelu czasowego w Streamlit."""

import altair as alt
import pandas as pd
import streamlit as st

from timeline import (
    GODZINY_ETATU_MIESIECZNIE,
    domyslne_parametry_czasowe,
    oblicz_model_czasowy,
    _koszty_kontraktu,
)


def _kwota(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " zł"


def _kwota_skrocona(value: float) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000:
        places = 2 if absolute < 10_000_000 else 1
        formatted = f"{value / 1_000_000:.{places}f}".replace(".", ",")
        return f"{formatted} mln zł"
    if absolute >= 1_000:
        formatted = f"{value / 1_000:.1f}".replace(".", ",")
        return f"{formatted} tys. zł"
    return f"{value:.0f}".replace(".", ",") + " zł"


def _liczba(value: float, places: int = 1) -> str:
    return f"{value:,.{places}f}".replace(",", " ").replace(".", ",")


def _procent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%".replace(".", ",")


def _miesiac(value: int | None) -> str:
    return f"Miesiąc {value}" if value is not None else "Brak"


def _financial_break_even_value(kpi: dict) -> tuple[str, str]:
    """Formatuje surowe odzyskanie deficytu, bez warunku pojemności."""
    status = kpi["pierwsze_przeciecie_status"]
    if status == "osiagniety":
        return (
            f"Miesiąc {kpi['pierwsze_przeciecie_miesiac']}",
            "Pierwszy powrót wyniku skumulowanego z deficytu do co najmniej zera.",
        )
    if status == "od_poczatku":
        return "Od początku", "W horyzoncie nie wystąpił początkowy deficyt."
    return "Brak", "Deficyt nie został odzyskany w analizowanym horyzoncie."


def _x_axis(horizon: int) -> alt.X:
    return alt.X(
        "Miesiąc:Q",
        title="Miesiąc",
        scale=alt.Scale(domain=[1, horizon], nice=False),
        axis=alt.Axis(tickMinStep=1, tickCount=min(12, horizon)),
    )


def _cumulative_chart(table: pd.DataFrame, horizon: int, break_even: int | None):
    line = (
        alt.Chart(table)
        .mark_line(color="#2563eb", strokeWidth=2.5)
        .encode(
            x=_x_axis(horizon),
            y=alt.Y(
                "Wynik skumulowany przed podatkiem:Q",
                title="Wynik skumulowany (zł)",
            ),
            tooltip=[
                alt.Tooltip("Miesiąc:Q", format=".0f"),
                alt.Tooltip("Wynik skumulowany przed podatkiem:Q", format=",.2f"),
            ],
        )
    )
    zero = (
        alt.Chart(pd.DataFrame({"Poziom": [0]}))
        .mark_rule(color="#6b7280", strokeDash=[5, 4], opacity=0.7)
        .encode(y=alt.Y("Poziom:Q"))
    )
    chart = line + zero
    if break_even is not None:
        point_data = table[table["Miesiąc"] == break_even]
        point = (
            alt.Chart(point_data)
            .mark_point(color="#16a34a", filled=True, size=90)
            .encode(
                x=_x_axis(horizon),
                y=alt.Y("Wynik skumulowany przed podatkiem:Q"),
                tooltip=[
                    alt.Tooltip("Miesiąc:Q", format=".0f"),
                    alt.Tooltip(
                        "Wynik skumulowany przed podatkiem:Q", format=",.2f"
                    ),
                ],
            )
        )
        chart += point
    return chart.properties(height=330)


def _finance_chart(table: pd.DataFrame, horizon: int):
    melted = table[["Miesiąc", "Przychód razem", "Łączny koszt miesięczny"]].melt(
        "Miesiąc", var_name="Pozycja", value_name="Kwota"
    )
    melted["Pozycja"] = melted["Pozycja"].replace(
        {"Przychód razem": "Przychód", "Łączny koszt miesięczny": "Koszt kontraktu"}
    )
    return (
        alt.Chart(melted)
        .mark_line(strokeWidth=2.2)
        .encode(
            x=_x_axis(horizon),
            y=alt.Y("Kwota:Q", title="Kwota miesięczna (zł)"),
            color=alt.Color(
                "Pozycja:N",
                title=None,
                scale=alt.Scale(
                    domain=["Przychód", "Koszt kontraktu"],
                    range=["#16a34a", "#dc2626"],
                ),
            ),
            tooltip=[
                alt.Tooltip("Miesiąc:Q", format=".0f"),
                alt.Tooltip("Pozycja:N"),
                alt.Tooltip("Kwota:Q", format=",.2f"),
            ],
        )
        .properties(height=280)
    )


def _capacity_charts(table: pd.DataFrame, horizon: int):
    backlog = (
        alt.Chart(table)
        .mark_line(color="#dc2626", strokeWidth=2.3)
        .encode(
            x=_x_axis(horizon),
            y=alt.Y("Backlog na koniec (h):Q", title="Backlog (h)"),
            tooltip=[
                alt.Tooltip("Miesiąc:Q", format=".0f"),
                alt.Tooltip("Backlog na koniec (h):Q", format=",.1f"),
                alt.Tooltip("Nowa praca (h):Q", format=",.1f"),
                alt.Tooltip("Praca oczekująca (h):Q", format=",.1f"),
                alt.Tooltip("Wykonana praca (h):Q", format=",.1f"),
            ],
        )
        .properties(height=220, title="Backlog pracy")
    )
    utilization = (
        alt.Chart(table)
        .mark_line(color="#7c3aed", strokeWidth=2.3)
        .encode(
            x=_x_axis(horizon),
            y=alt.Y(
                "Wykorzystanie pojemności (%):Q",
                title="Wykorzystanie (%)",
                scale=alt.Scale(domain=[0, 105], nice=False),
            ),
            tooltip=[
                alt.Tooltip("Miesiąc:Q", format=".0f"),
                alt.Tooltip("Wykorzystanie pojemności (%):Q", format=".1f"),
            ],
        )
        .properties(height=190, title="Wykorzystanie pojemności")
    )
    full_capacity = (
        alt.Chart(pd.DataFrame({"Poziom": [100]}))
        .mark_rule(color="#6b7280", strokeDash=[5, 4], opacity=0.6)
        .encode(y=alt.Y("Poziom:Q"))
    )
    return backlog, utilization + full_capacity


def _ustawienie(klucz: str, etykieta: str, domyslna, **opcje):
    """Zachowuje założenia kontraktu po przełączeniu pomiędzy panelami."""
    zapisane = st.session_state.setdefault("zalozenia_kontraktu", {})
    widget = "kontrakt_" + klucz
    if widget not in st.session_state:
        st.session_state[widget] = zapisane.get(klucz, domyslna)

    def zapisz():
        st.session_state["zalozenia_kontraktu"] = {
            **st.session_state["zalozenia_kontraktu"], klucz: st.session_state[widget]
        }

    return st.number_input(etykieta, key=widget, on_change=zapisz, **opcje)


def renderuj_widok_czasowy(parametry: dict, *, pracownicy: list[dict] | None = None) -> None:
    st.header("Kontrakt w czasie")
    st.caption(
        "Koszt kontraktu obejmuje indywidualne wynagrodzenia za przydzielone godziny "
        "oraz koszty spraw z faktycznie wykonaną pracą w miesiącu. Oba panele korzystają z tej samej obsady; "
        "kontrakt płaci indywidualne stawki za przydzielone godziny."
    )
    st.caption(
        "Przyjęcie EH poprzedza ugody lub proces. Po odrzuceniu ugody proces trafia do EH "
        "od kolejnego miesiąca; II instancja od miesiąca po wyroku I. "
        "Zegary formalne startują od pierwszej pracy odpowiedniego etapu. "
        "Etap zerowy wymaga dostępnej roli i jest inicjowany bez opłaty za pracę."
    )
    st.subheader("Koszty kontraktu")
    defaults_cost = _koszty_kontraktu(None)
    cost_columns = st.columns(2)
    with cost_columns[0]:
        overhead = _ustawienie("ogolne_na_aktywna_sprawe",
            "Koszty ogólne / sprawę z wykonaną pracą / mies.", defaults_cost["ogolne_na_aktywna_sprawe"],
            min_value=0.0, step=1.0)
    with cost_columns[1]:
        secretariat = _ustawienie("sekretariat_na_aktywna_sprawe",
            "Koszt sekretariatu / sprawę z wykonaną pracą / mies.", defaults_cost["sekretariat_na_aktywna_sprawe"],
            min_value=0.0, step=1.0)
    st.caption("Koszty naliczane są wyłącznie za miesiące, w których rzeczywiście wykonano pracę nad sprawą. "
               "Kilka etapów lub obu prawników w jednym miesiącu oznacza jedną opłatę. "
               "Kolejka, oczekiwanie formalne i opóźnienie płatności nie naliczają opłat.")
    time_parameters = {}
    with st.expander("Założenia czasowe"):
        labels = {
            "miesiace_do_ugody": "Od rozpoczęcia pracy ugodowej do ugody (mies.)",
            "miesiace_do_wyroku_i": "Od rozpoczęcia procesu do wyroku I instancji (mies.)",
            "miesiace_wyrok_i_do_ii": "Od rozpoczęcia pracy II instancji do wyroku (mies.)",
            "opoznienie_platnosci_miesiace": "Opóźnienie płatności (mies.)",
            "horyzont_miesiace": "Horyzont analizy (mies.)",
        }
        columns = st.columns(3)
        for i, (key, default) in enumerate(domyslne_parametry_czasowe().items()):
            with columns[i % 3]:
                time_parameters[key] = int(_ustawienie(key, labels[key], default,
                    min_value=12 if key == "horyzont_miesiace" else 0, max_value=360, step=1))
    costs = {"ogolne_na_aktywna_sprawe": overhead, "sekretariat_na_aktywna_sprawe": secretariat}
    try:
        result = oblicz_model_czasowy(parametry, time_parameters, pracownicy=pracownicy,
                                      koszty_kontraktu=costs)
    except ValueError as error:
        st.error(str(error))
        return
    kpi, capacity, summary = result["kpi"], result["pojemnosc"], result["podsumowanie"]
    horizon = time_parameters["horyzont_miesiace"]
    if capacity["status_pojemnosci"] == "Niewystarczająca":
        st.warning("Co najmniej jedna rola ma za małą pojemność. Backlog rośnie; trwała rentowność nie jest potwierdzona.")
    top = st.columns(2, gap="large")
    top[0].metric("Status kontraktu", kpi["status_kontraktu"])
    value, help_text = _financial_break_even_value(kpi)
    top[1].metric("Break-even finansowy", value, help=help_text)
    financial = st.columns(2)
    deficit_label = "Największy deficyt" if kpi["najglebszy_deficyt_potwierdzony"] else f"Najniższy wynik do {horizon} mies."
    financial[0].metric(deficit_label, _kwota_skrocona(kpi["najglebszy_deficyt_skumulowany"]),
                        help=_kwota(kpi["najglebszy_deficyt_skumulowany"]))
    financial[1].metric(f"Wynik po {horizon} mies.", _kwota_skrocona(kpi["wynik_skumulowany_na_koniec_horyzontu"]))
    if kpi["wynik_nadal_narasta"]:
        st.caption("Skumulowany wynik ma trwały trend spadkowy.")
    ops = st.columns(3)
    ops[0].metric("Obsada", f"{len(capacity['pracownicy'])} os.")
    ops[1].metric("Backlog", f"{_liczba(summary['backlog_koniec_godziny'])} h")
    ops[2].metric("Status operacyjny", capacity["status_pojemnosci"])
    st.write(f"Ocena trwałości: **{kpi['status_break_even']}**.")
    st.caption(
        "Deficyt rozruchowy: " + ("tak" if result["diagnoza"]["deficyt_rozruchowy"] else "nie")
        + ". Wyniki i break-even są liczone przed podatkiem dochodowym."
    )
    last = result["tabela_miesieczna"][-1]
    table = pd.DataFrame(result["tabela_miesieczna"])
    st.subheader("Skumulowany wynik przed podatkiem")
    st.altair_chart(_cumulative_chart(table, horizon, kpi["pierwsze_przeciecie_miesiac"]), width="stretch")
    chart = st.segmented_control("Dodatkowy wykres", ("Finanse miesięczne", "Pojemność i backlog"), default="Finanse miesięczne")
    if chart == "Finanse miesięczne":
        st.altair_chart(_finance_chart(table, horizon), width="stretch")
    else:
        for visual in _capacity_charts(table, horizon):
            st.altair_chart(visual, width="stretch")
        st.line_chart(table.set_index("Miesiąc")[["Backlog EH (h)", "Backlog UGODY (h)"]])
    with st.expander("Pojemność zespołu"):
        for role, label in (("EH", "EH"), ("UGODY", "ugód")):
            pool = capacity["role"][role]
            st.markdown(f"**Prawnicy {label} · {pool['status']}**")
            c = st.columns(3)
            c[0].metric(f"Wymagana pojemność {label}", f"{_liczba(pool['popyt_minuty'] / 60, 2)} h/mies.")
            c[1].metric(f"Dostępna pojemność {label}", f"{_liczba(pool['netto_minuty'] / 60, 2)} h/mies.")
            c[2].metric(f"Niedobór pojemności {label}", f"{_liczba(pool['niedobor_minuty'] / 60, 2)} h/mies.")
            st.caption(f"Czynności dzienne: {_liczba(pool['dzienne_minuty'] / 60, 2)} h/mies. · "
                       f"Backlog: {_liczba(last[f'Backlog {role} (h)'], 2)} h")
        st.caption("Pojemność jest rozłączna według ról. Każdy pracownik wnosi 167 h × przydział / 100; "
                   "czynności dzienne pomniejszają zasób jednego wybranego prawnika EH raz dla projektu. Niewykorzystany czas jest płatny.")
    with st.expander("Szczegóły modelu"):
        st.metric("Stan stabilny", summary["status_stanu_stabilnego"])
        stable = kpi["wynik_miesieczny_w_stanie_stabilnym"]
        st.write("Wynik w stanie stabilnym: " + (f"**{_kwota(stable)}/mies.**" if stable is not None else "**Niepotwierdzony**"))
        st.caption("Potwierdzenie wymaga pełnych 12 miesięcy stabilnego przepływu obu ról, zakończeń, "
                   "spraw otwartych, pracy i wszystkich kosztów. Krótki rozruch nie potwierdza dojrzałej rentowności.")
        st.metric("Pierwszy dodatni miesiąc", _miesiac(kpi["pierwszy_dodatni_miesiac"]))
    cases = st.columns(3)
    cases[0].metric("Sprawy otwarte", _liczba(last["Sprawy otwarte"], 2))
    cases[1].metric("Sprawy oczekujące na pracę", _liczba(last["Sprawy oczekujące na pracę"], 2))
    cases[2].metric("Sprawy, nad którymi pracowano w miesiącu", _liczba(last["Sprawy, nad którymi pracowano w miesiącu"], 2))
    st.caption("Sprawy otwarte obejmują kolejki i oczekiwanie na wynik formalny. "
               "Przyszła II instancja jest pracą oczekującą na wcześniejszy wyrok, a nie zaległą pracą. "
               "Czynności dzienne wykonuje raz cały projekt w zasobie EH; są już opłacone w wynagrodzeniach.")
    if capacity["role"]["EH"]["dzienne_niewykonane_minuty"] > 0:
        st.warning("Brak pojedynczego pracownika EH z przydziałem wystarczającym na wszystkie czynności dzienne. "
                   f"Niewykonana część: {_liczba(capacity['role']['EH']['dzienne_niewykonane_minuty'] / 60, 3)} h/mies.")
    with st.expander(f"Rozliczenie kontraktu za {horizon} mies.", expanded=False):
        totals = result["podsumowanie_finansowe"]
        labels = {"Wynagrodzenia EH": "Łączne wynagrodzenia EH",
                  "Wynagrodzenia ugód": "Łączne wynagrodzenia ugód",
                  "Koszty ogólne spraw, nad którymi pracowano": "Łączne koszty ogólne spraw z wykonaną pracą",
                  "Koszt sekretariatu spraw, nad którymi pracowano": "Łączny koszt sekretariatu spraw z wykonaną pracą",
                  "Łączny koszt miesięczny": "Łączny koszt kontraktu",
                  "Przychód razem": "Łączny przychód kontraktu",
                  "Wynik miesięczny przed podatkiem": "Wynik kontraktu przed podatkiem"}
        st.dataframe(pd.DataFrame([{"Pozycja": label, "Kwota": totals[key]} for key, label in labels.items()]),
                     hide_index=True, width="stretch", column_config={"Kwota": st.column_config.NumberColumn(format="%.2f zł")})
        flows = {"Sprawomiesiące faktycznej pracy": totals["Sprawy, nad którymi pracowano w miesiącu"],
                 "Sprawy oczekujące na formalne zakończenie": last["Sprawy oczekujące na formalne zakończenie"],
                 "Sprawy zakończone w horyzoncie": result["walidacja"]["laczne_zakonczenia_spraw"],
                 "Sprawy otwarte na koniec horyzontu": summary["aktywne_sprawy"],
                 "Backlog EH (h)": last["Backlog EH (h)"], "Backlog ugód (h)": last["Backlog UGODY (h)"],
                 "Praca przyszła i zablokowana (h)": result["walidacja"]["praca_przyszla_minuty"] / 60}
        st.dataframe(pd.DataFrame([{"Wielkość": key, "Wartość": value} for key, value in flows.items()]),
                     hide_index=True, width="stretch")
        st.caption(f"Koszty ogólne: {_liczba(totals['Sprawy, nad którymi pracowano w miesiącu'], 6)} sprawomiesiąca × "
                   f"{_kwota(overhead)} = {_kwota(totals['Koszty ogólne spraw, nad którymi pracowano'])}. "
                   "Sprawy otwarte mogą oczekiwać na formalne zakończenie bez pracy i opłat. "
                   "Dlatego ich liczba może przekraczać liczbę spraw, nad którymi pracowano.")
    with st.expander("Miesięczne szczegóły finansowe", expanded=False):
        financial_columns = ["Miesiąc", "Sprawy, nad którymi pracowano w miesiącu", "Przychód z ugód", "Przychód z wyroków", "Przychód razem",
            "Wynagrodzenia EH", "Wynagrodzenia ugód", "Koszty ogólne spraw, nad którymi pracowano",
            "Koszt sekretariatu spraw, nad którymi pracowano", "Łączny koszt miesięczny",
            "Wynik miesięczny przed podatkiem", "Wynik skumulowany przed podatkiem"]
        st.dataframe(table[financial_columns], hide_index=True, width="stretch")
    with st.expander("Miesięczne przepływy i pojemność"):
        st.dataframe(table.drop(columns=["Aktywne sprawy"]).rename(columns={"Ugody zakończone": "Zakończone ugodą", "Zakończenia po I instancji": "Zakończone w I instancji", "Zakończenia po II instancji": "Zakończone w II instancji", "Backlog UGODY (h)": "Backlog ugód (h)"}), hide_index=True, width="stretch")
    st.caption("Zakończone ugodą, zakończone w I instancji i zakończone w II instancji "
               "pokazano osobno w przepływach miesięcznych. Formalne zakończenie nie musi oznaczać płatności w tym samym miesiącu.")
    st.caption("Zmiany obsady analizuj przez jawne ustawienia pracowników. Wymagana pojemność według ról "
               "zastępuje pojedynczą minimalną liczbę etatów, która nie opisuje zróżnicowanego zespołu.")
