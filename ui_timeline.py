"""Warstwa prezentacji ciągłego modelu czasowego w Streamlit."""

import altair as alt
import pandas as pd
import streamlit as st

from timeline import (
    domyslne_parametry_czasowe,
    oblicz_model_czasowy,
    porownaj_obsade,
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


def _break_even_value(kpi: dict, capacity: dict) -> tuple[str, str]:
    if "status_break_even" not in kpi and capacity["status_pojemnosci"] == "Niewystarczająca":
        return "Brak", "Brak trwałego break-even przy obecnej obsadzie."
    if kpi["break_even_status"] == "osiagniety":
        return f"Miesiąc {kpi['break_even_miesiac']}", kpi["status_break_even"]
    if kpi["break_even_status"] == "od_poczatku":
        return "Od początku", kpi["status_break_even"]
    return "Brak", kpi["status_break_even"]


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
    melted = table[["Miesiąc", "Przychód razem", "Miesięczny koszt operacji"]].melt(
        "Miesiąc", var_name="Pozycja", value_name="Kwota"
    )
    melted["Pozycja"] = melted["Pozycja"].replace(
        {"Przychód razem": "Przychód", "Miesięczny koszt operacji": "Koszt operacji"}
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
                    domain=["Przychód", "Koszt operacji"],
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


def renderuj_widok_czasowy(parametry: dict) -> None:
    """Renderuje wyłącznie wybraną analizę czasu i pojemności."""
    st.subheader("Kiedy zaczniemy zarabiać?")
    st.caption(
        "Ciągły model operacyjny łączy koszt utrzymywanej obsady z kolejką pracy, "
        "terminami zakończeń i wpływem przychodów."
    )

    defaults = domyslne_parametry_czasowe()
    with st.expander("Założenia czasowe", expanded=False):
        settings_columns = st.columns(3, wrap=True)
        with settings_columns[0]:
            settlement_months = st.number_input(
                "Od wpływu sprawy do ugody (mies.)",
                min_value=0,
                max_value=120,
                value=defaults["miesiace_do_ugody"],
                step=1,
            )
            payment_delay = st.number_input(
                "Opóźnienie płatności (mies.)",
                min_value=0,
                max_value=120,
                value=defaults["opoznienie_platnosci_miesiace"],
                step=1,
            )
        with settings_columns[1]:
            first_instance_months = st.number_input(
                "Od wpływu do wyroku I instancji (mies.)",
                min_value=0,
                max_value=120,
                value=defaults["miesiace_do_wyroku_i"],
                step=1,
            )
            horizon = st.number_input(
                "Horyzont analizy (mies.)",
                min_value=12,
                max_value=120,
                value=defaults["horyzont_miesiace"],
                step=1,
            )
        with settings_columns[2]:
            second_instance_months = st.number_input(
                "Od I do II instancji (mies.)",
                min_value=0,
                max_value=120,
                value=defaults["miesiace_wyrok_i_do_ii"],
                step=1,
            )
            st.metric(
                "Średni napływ miesięczny",
                f"{_liczba(parametry['liczba_spraw'] / 12, 2)} spraw",
            )

    time_parameters = {
        "miesiace_do_ugody": int(settlement_months),
        "miesiace_do_wyroku_i": int(first_instance_months),
        "miesiace_wyrok_i_do_ii": int(second_instance_months),
        "opoznienie_platnosci_miesiace": int(payment_delay),
        "horyzont_miesiace": int(horizon),
    }
    result = oblicz_model_czasowy(parametry, time_parameters)
    kpi = result["kpi"]
    capacity = result["pojemnosc"]
    summary = result["podsumowanie"]
    diagnosis = result["diagnoza"]

    if capacity["status_pojemnosci"] == "Niewystarczająca":
        st.warning(
            "Przy obecnym napływie portfel narasta szybciej, niż zespół może go "
            "obsłużyć. Backlog będzie rosnąć w długim okresie."
        )

    break_even_value, break_even_help = _break_even_value(kpi, capacity)
    minimum_staff = capacity["minimalna_liczba_pracownikow_dla_stabilnosci"]
    primary_top = st.columns(2, gap="large", wrap=True)
    primary_top[0].metric("Break-even", break_even_value, help=break_even_help)
    primary_top[1].metric(
        f"Wynik po {horizon} mies.",
        _kwota_skrocona(kpi["wynik_skumulowany_na_koniec_horyzontu"]),
        help=_kwota(kpi["wynik_skumulowany_na_koniec_horyzontu"]),
    )
    if kpi["wynik_nadal_narasta"]:
        primary_top[1].caption("Skumulowany wynik ma trwały trend spadkowy.")
    primary_bottom = st.columns(2, gap="large", wrap=True)
    primary_bottom[0].metric(
        "Backlog",
        f"{_liczba(summary['backlog_koniec_godziny'], 0)} h",
        help=f"Dokładnie {_liczba(summary['backlog_koniec_godziny'], 2)} h.",
    )
    primary_bottom[1].metric("Pojemność", capacity["status_pojemnosci"])
    if capacity["status_pojemnosci"] == "Na granicy":
        primary_bottom[1].caption("Wykonalna operacyjnie, ale bez bufora pojemności.")
    else:
        primary_bottom[1].caption(
            f"{parametry['liczba_pracownikow']} os. → potrzeba min. {minimum_staff}"
            if minimum_staff is not None
            else "Brak możliwej stabilnej obsady przy tych założeniach."
        )

    loss_reasons = [
        "rozruch: koszt przed dojrzeniem przychodów"
        if diagnosis["deficyt_rozruchowy"]
        else "rozruch: bez deficytu",
        (
            "niewykorzystana pojemność w horyzoncie: "
            f"{_kwota_skrocona(diagnosis['koszt_niewykorzystanej_pojemnosci_horyzont'])}"
        ),
        "niedobór strukturalny: tak"
        if diagnosis["strukturalny_niedobor_pojemnosci"]
        else "niedobór strukturalny: nie",
    ]
    st.caption("Diagnoza wyniku · " + " · ".join(loss_reasons))

    secondary = st.columns(3, wrap=True)
    secondary[0].metric("Aktywne sprawy", _liczba(summary["aktywne_sprawy"], 1))
    secondary[1].metric(
        "Bieżące wykorzystanie",
        _procent(capacity["biezace_wykorzystanie_percent"]),
        help=(
            "Wykorzystanie w ostatnim miesiącu; obejmuje czynności dzienne "
            "i wykonaną pracę nad sprawami."
        ),
    )
    secondary[2].metric(
        "Minimalna stabilna obsada",
        f"{minimum_staff} os." if minimum_staff is not None else "Nieosiągalna",
    )
    st.caption(
        f"Napływ: {_liczba(summary['roczny_naplyw'], 0)}/rok · "
        f"{_liczba(summary['sredni_naplyw_miesieczny'], 2)}/mies. · "
        "Break-even liczony przed podatkiem dochodowym; model nie odwzorowuje "
        "terminów płatności podatku."
    )

    table = pd.DataFrame(result["tabela_miesieczna"])
    st.subheader("Skumulowany wynik przed podatkiem")
    st.altair_chart(
        _cumulative_chart(table, int(horizon), kpi["break_even_miesiac"]),
        width="stretch",
    )

    additional_chart = st.segmented_control(
        "Dodatkowy wykres",
        ("Finanse miesięczne", "Pojemność i backlog"),
        default="Finanse miesięczne",
    )
    if additional_chart == "Finanse miesięczne":
        st.altair_chart(_finance_chart(table, int(horizon)), width="stretch")
    else:
        backlog_chart, utilization_chart = _capacity_charts(table, int(horizon))
        st.altair_chart(backlog_chart, width="stretch")
        st.altair_chart(utilization_chart, width="stretch")

    with st.expander("Pojemność zespołu", expanded=False):
        capacity_metrics = st.columns(3, wrap=True)
        capacity_metrics[0].metric(
            "Pojemność brutto",
            f"{_liczba(capacity['pojemnosc_brutto_minuty'] / 60, 1)} h/mies.",
        )
        capacity_metrics[1].metric(
            "Czynności dzienne",
            f"{_liczba(capacity['czynnosci_dzienne_minuty'] / 60, 1)} h/mies.",
        )
        capacity_metrics[2].metric(
            "Pojemność na sprawy",
            f"{_liczba(capacity['pojemnosc_na_sprawy_minuty'] / 60, 1)} h/mies.",
        )
        koszt_metrics = st.columns(3, wrap=True)
        koszt_metrics[0].metric(
            "Miesięczny koszt stały",
            _kwota(capacity["miesieczny_koszt_staly"]),
        )
        koszt_metrics[1].metric(
            "Miesięczny koszt pracowników",
            _kwota(capacity["miesieczny_koszt_pracownikow"]),
        )
        koszt_metrics[2].metric(
            "Miesięczny koszt operacji",
            _kwota(capacity["miesieczny_koszt_operacji"]),
        )

    with st.expander("Szczegóły modelu", expanded=False):
        detail_1 = st.columns(3, wrap=True)
        detail_1[0].metric(
            "Pierwszy dodatni miesiąc", _miesiac(kpi["pierwszy_dodatni_miesiac"])
        )
        detail_1[1].metric(
            "Historyczne minimum wyniku",
            _kwota_skrocona(kpi["najglebszy_deficyt_skumulowany"]),
            help=_kwota(kpi["najglebszy_deficyt_skumulowany"]),
        )
        detail_1[2].metric(
            "Średnie wykorzystanie całego horyzontu",
            _procent(capacity["srednie_wykorzystanie_percent"]),
        )
        st.caption(
            "Historyczne minimum jest potwierdzonym najgłębszym deficytem."
            if kpi["najglebszy_deficyt_potwierdzony"]
            else "Historyczne minimum przypada na koniec horyzontu i nie jest "
            "skończonym maksymalnym zapotrzebowaniem na finansowanie."
        )
        przeciecie_nietrwale = (
            " — nietrwałe"
            if kpi["pierwsze_przeciecie_status"] == "osiagniety"
            and kpi["break_even_status"] != "osiagniety"
            else ""
        )
        st.write(
            "Pierwsze surowe przecięcie zera wyniku skumulowanego: "
            f"**{kpi['pierwsze_przeciecie_skumulowane']}{przeciecie_nietrwale}**. "
            "Główny KPI pokazuje wyłącznie trwały break-even."
        )
        detail_2 = st.columns(3, wrap=True)
        detail_2[0].metric(
            "Wykorzystanie — ostatnie 12 mies.",
            _procent(capacity["ostatnie_12_miesiecy_wykorzystanie_percent"]),
        )
        detail_2[1].metric(
            "Bieżące opóźnienie pojemności",
            f"{summary['biezace_opoznienie_pojemnosci_miesiace']} mies.",
        )
        detail_2[2].metric("Stan stabilny", summary["status_stanu_stabilnego"])
        stable_result = kpi["wynik_miesieczny_w_stanie_stabilnym"]
        if stable_result is not None:
            st.write(
                "Wynik w stanie stabilnym: "
                f"**{_kwota(stable_result)}/mies.** · "
                f"**{_kwota(kpi['wynik_roczny_w_stanie_stabilnym'])}/rok**"
            )
        else:
            st.write(
                f"Wynik w stanie stabilnym: **{summary['status_stanu_stabilnego']}**"
            )

        balance = diagnosis["bilans_pojemnosci_rocznie_godziny"]
        balance_label = (
            "Niewykorzystana pojemność" if balance >= 0 else "Brakująca pojemność"
        )
        st.markdown("##### Uzgodnienie lifecycle i modelu czasowego")
        reconciliation = pd.DataFrame(
            [
                {
                    "Pozycja": "Marża lifecycle kohorty przed podatkiem",
                    "Wartość": _procent(diagnosis["marza_lifecycle_przed_podatkiem"]),
                },
                {
                    "Pozycja": "Koszt lifecycle kohorty",
                    "Wartość": _kwota(diagnosis["koszt_lifecycle_roczny"]),
                },
                {
                    "Pozycja": "Roczny koszt utrzymywanej operacji",
                    "Wartość": _kwota(diagnosis["koszt_operacji_czasowy_roczny"]),
                },
                {
                    "Pozycja": "Roczne wymagane godziny zasobu",
                    "Wartość": f"{_liczba(diagnosis['roczne_wymagane_godziny_zasobu'], 2)} h",
                },
                {
                    "Pozycja": "Dostarczane godziny zespołu",
                    "Wartość": f"{_liczba(diagnosis['dostarczane_godziny_zespolu_rocznie'], 2)} h/rok",
                },
                {
                    "Pozycja": f"{balance_label} rocznie",
                    "Wartość": f"{_liczba(abs(balance), 2)} h",
                },
            ]
        )
        st.dataframe(reconciliation, hide_index=True, width="stretch")
        minimum_result = diagnosis["wynik_miesieczny_przy_minimalnej_obsadzie"]
        if minimum_result is not None:
            st.caption(
                "Dojrzały wynik przy minimalnej stabilnej obsadzie: "
                f"{_kwota(minimum_result)}/mies."
            )

    with st.expander("Szczegóły miesiąc po miesiącu", expanded=False):
        tabela_do_wyswietlenia = table.drop(columns=["Koszt zespołu"], errors="ignore")
        st.dataframe(
            tabela_do_wyswietlenia,
            hide_index=True,
            width="stretch",
            column_config={
                "Nowe sprawy": st.column_config.NumberColumn(format="%.2f"),
                "Aktywne sprawy": st.column_config.NumberColumn(format="%.2f"),
                "Przychód z ugód": st.column_config.NumberColumn(format="%.2f zł"),
                "Przychód z wyroków": st.column_config.NumberColumn(format="%.2f zł"),
                "Przychód razem": st.column_config.NumberColumn(format="%.2f zł"),
                "Koszt niewykorzystanej pojemności": st.column_config.NumberColumn(format="%.2f zł"),
                "Miesięczny koszt stały": st.column_config.NumberColumn(format="%.2f zł"),
                "Miesięczny koszt pracowników": st.column_config.NumberColumn(format="%.2f zł"),
                "Miesięczny koszt operacji": st.column_config.NumberColumn(format="%.2f zł"),
                "Wynik miesięczny przed podatkiem": st.column_config.NumberColumn(format="%.2f zł"),
                "Wynik skumulowany przed podatkiem": st.column_config.NumberColumn(format="%.2f zł"),
            },
        )

    with st.expander("Porównanie obsady", expanded=False):
        st.caption(
            "Mniejsza obsada obniża koszt, ale może opóźniać przychody; większa "
            "obsada zwiększa pojemność oraz koszt niewykorzystanego czasu."
        )
        calculate_comparison = st.toggle(
            "Oblicz warianty obsady", value=False, key="oblicz_porownanie_obsady"
        )
        if calculate_comparison:
            comparison = pd.DataFrame(porownaj_obsade(parametry, time_parameters))
            st.dataframe(
                comparison,
                hide_index=True,
                width="stretch",
                column_config={
                    "Pojemność netto (h/mies.)": st.column_config.NumberColumn(format="%.1f h"),
                    "Średnie wykorzystanie": st.column_config.NumberColumn(format="%.1f%%"),
                    "Backlog po horyzoncie (h)": st.column_config.NumberColumn(format="%.1f h"),
                    "Miesięczny koszt operacji": st.column_config.NumberColumn(format="%.2f zł"),
                    "Wynik miesięczny w stanie stabilnym": st.column_config.NumberColumn(format="%.2f zł"),
                },
            )
