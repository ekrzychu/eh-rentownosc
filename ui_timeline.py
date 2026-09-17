"""Warstwa prezentacji ciągłego modelu czasowego w Streamlit."""

import pandas as pd
import streamlit as st

from timeline import (
    domyslne_parametry_czasowe,
    oblicz_model_czasowy,
    porownaj_obsade,
)


def _kwota(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " zł"


def _liczba(value: float, places: int = 1) -> str:
    return f"{value:,.{places}f}".replace(",", " ").replace(".", ",")


def _procent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%".replace(".", ",")


def _miesiac(value: int | None) -> str:
    return f"Miesiąc {value}" if value is not None else "Brak w horyzoncie"


def renderuj_widok_czasowy(parametry: dict) -> None:
    """Renderuje wyłącznie wybraną analizę czasu i pojemności."""
    st.subheader("Kiedy zaczniemy zarabiać?")
    st.caption(
        "Ciągły model operacyjny pokazuje miesięczny napływ, koszt utrzymywanej "
        "obsady, backlog pracy oraz moment uzyskania przychodów."
    )

    defaults = domyslne_parametry_czasowe()
    with st.expander("Założenia czasowe"):
        settings_columns = st.columns(3, wrap=True)
        with settings_columns[0]:
            settlement_months = st.number_input(
                "Od wpływu sprawy do ugody",
                min_value=0,
                max_value=120,
                value=defaults["miesiace_do_ugody"],
                step=1,
                help="Najwcześniejszy nominalny termin ugody, w miesiącach.",
            )
            payment_delay = st.number_input(
                "Opóźnienie płatności",
                min_value=0,
                max_value=120,
                value=defaults["opoznienie_platnosci_miesiace"],
                step=1,
                help="Liczba miesięcy od faktycznego zakończenia do zapłaty.",
            )
        with settings_columns[1]:
            first_instance_months = st.number_input(
                "Od wpływu do wyroku I instancji",
                min_value=0,
                max_value=120,
                value=defaults["miesiace_do_wyroku_i"],
                step=1,
                help="Najwcześniejszy nominalny termin wyroku I instancji.",
            )
            horizon = st.number_input(
                "Horyzont analizy",
                min_value=12,
                max_value=120,
                value=defaults["horyzont_miesiace"],
                step=1,
                help="Liczba miesięcy ciągłego działania objętych symulacją.",
            )
        with settings_columns[2]:
            second_instance_months = st.number_input(
                "Od I do II instancji",
                min_value=0,
                max_value=120,
                value=defaults["miesiace_wyrok_i_do_ii"],
                step=1,
                help="Najwcześniejszy dodatkowy czas dla spraw w II instancji.",
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

    if capacity["status_pojemnosci"] == "Niewystarczająca":
        st.warning(
            "Przy obecnym napływie portfel narasta szybciej, niż zespół może go "
            "obsłużyć. Backlog będzie rosnąć w długim okresie."
        )
    if capacity["brak_pojemnosci_na_sprawy"]:
        st.error(
            "Czynności dzienne zużywają całą pojemność zespołu. "
            "Brak dostępnego czasu na bezpośrednią obsługę spraw."
        )

    primary = st.columns(4, wrap=True)
    primary[0].metric("Break-even skumulowany", kpi["break_even_skumulowany"])
    primary[0].caption(kpi["status_break_even"])
    primary[1].metric(
        "Pierwszy dodatni miesiąc", _miesiac(kpi["pierwszy_dodatni_miesiac"])
    )
    primary[2].metric(
        "Najgłębszy deficyt",
        _kwota(kpi["najglebszy_deficyt_skumulowany"]),
        f"miesiąc {kpi['miesiac_najglebszego_deficytu']}",
        delta_color="off",
    )
    primary[3].metric("Status pojemności", capacity["status_pojemnosci"])

    secondary = st.columns(6, wrap=True)
    secondary[0].metric("Roczny napływ", f"{_liczba(summary['roczny_naplyw'], 0)} spraw")
    secondary[1].metric(
        "Średni napływ / miesiąc",
        f"{_liczba(summary['sredni_naplyw_miesieczny'], 2)} spraw",
    )
    secondary[2].metric("Aktywne sprawy", _liczba(summary["aktywne_sprawy"], 1))
    secondary[3].metric(
        "Backlog pracy", f"{_liczba(summary['backlog_koniec_godziny'], 1)} h"
    )
    secondary[4].metric(
        "Wykorzystanie pojemności",
        _procent(capacity["srednie_wykorzystanie_percent"]),
    )
    minimum_staff = capacity["minimalna_liczba_pracownikow_dla_stabilnosci"]
    secondary[5].metric(
        "Minimalna stabilna obsada",
        f"{minimum_staff} os." if minimum_staff is not None else "Nieosiągalna",
    )
    st.caption(
        f"Pojemność brutto: {_liczba(capacity['pojemnosc_brutto_minuty'] / 60, 1)} h/mies. · "
        f"czynności dzienne: {_liczba(capacity['czynnosci_dzienne_minuty'] / 60, 1)} h/mies. · "
        f"pojemność na sprawy: {_liczba(capacity['pojemnosc_na_sprawy_minuty'] / 60, 1)} h/mies. · "
        f"koszt zespołu: {_kwota(capacity['miesieczny_koszt_zespolu'])}/mies."
    )

    steady = st.columns(2, wrap=True)
    steady_monthly = kpi["wynik_miesieczny_w_stanie_stabilnym"]
    steady_annual = kpi["wynik_roczny_w_stanie_stabilnym"]
    steady[0].metric(
        "Wynik miesięczny w stanie stabilnym",
        _kwota(steady_monthly) if steady_monthly is not None else "Poza horyzontem",
    )
    steady[1].metric(
        "Wynik roczny w stanie stabilnym",
        _kwota(steady_annual) if steady_annual is not None else "Poza horyzontem",
    )
    if not summary["dojrzalosc_osiagnieta"]:
        st.caption(
            "Stan dojrzały nie został potwierdzony w wybranym horyzoncie lub "
            "pojemność jest strukturalnie niewystarczająca."
        )
    st.caption(
        "Break-even w czasie jest liczony przed podatkiem dochodowym. "
        "Model nie odwzorowuje jeszcze terminów płatności podatku."
    )

    table = pd.DataFrame(result["tabela_miesieczna"])
    st.subheader("Skumulowany wynik przed podatkiem")
    cumulative_chart = table.set_index("Miesiąc")[[
        "Wynik skumulowany przed podatkiem"
    ]].copy()
    cumulative_chart["Poziom zero"] = 0.0
    st.line_chart(cumulative_chart, height=340)

    st.subheader("Przychód i koszt miesięczny")
    st.line_chart(
        table.set_index("Miesiąc")[[
            "Przychód razem",
            "Koszt zespołu",
            "Wynik miesięczny przed podatkiem",
        ]],
        height=320,
    )

    st.subheader("Pojemność i backlog pracy")
    st.line_chart(
        table.set_index("Miesiąc")[[
            "Dostępna pojemność na sprawy (h)",
            "Zapotrzebowanie na pracę (h)",
            "Wykonana praca bezpośrednia (h)",
            "Backlog pracy (h)",
        ]],
        height=320,
    )

    with st.expander("Szczegóły miesiąc po miesiącu"):
        backlog_details = st.columns(3, wrap=True)
        backlog_details[0].metric(
            "Backlog na końcu",
            f"{_liczba(summary['backlog_koniec_godziny'], 1)} h",
        )
        backlog_details[1].metric(
            "Maksymalny backlog",
            f"{_liczba(summary['maksymalny_backlog_godziny'], 1)} h",
        )
        months_of_backlog = summary["miesiace_backlogu"]
        backlog_details[2].metric(
            "Miesiące backlogu",
            _liczba(months_of_backlog, 2)
            if months_of_backlog is not None else "Brak pojemności",
        )
        st.dataframe(
            table,
            hide_index=True,
            width="stretch",
            column_config={
                "Nowe sprawy": st.column_config.NumberColumn(format="%.2f"),
                "Aktywne sprawy": st.column_config.NumberColumn(format="%.2f"),
                "Ugody zakończone": st.column_config.NumberColumn(format="%.2f"),
                "Zakończenia po I instancji": st.column_config.NumberColumn(format="%.2f"),
                "Zakończenia po II instancji": st.column_config.NumberColumn(format="%.2f"),
                "Przychód z ugód": st.column_config.NumberColumn(format="%.2f zł"),
                "Przychód z wyroków": st.column_config.NumberColumn(format="%.2f zł"),
                "Przychód razem": st.column_config.NumberColumn(format="%.2f zł"),
                "Koszt niewykorzystanej pojemności": st.column_config.NumberColumn(format="%.2f zł"),
                "Koszt zespołu": st.column_config.NumberColumn(format="%.2f zł"),
                "Wynik miesięczny przed podatkiem": st.column_config.NumberColumn(format="%.2f zł"),
                "Wynik skumulowany przed podatkiem": st.column_config.NumberColumn(format="%.2f zł"),
            },
        )

    with st.expander("Porównanie obsady"):
        st.caption(
            "Mniejsza obsada obniża miesięczny koszt, ale może opóźniać "
            "przychody. Większa obsada zwiększa pojemność i koszt niewykorzystanego czasu."
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
                    "Miesięczny koszt zespołu": st.column_config.NumberColumn(format="%.2f zł"),
                    "Wynik miesięczny w stanie stabilnym": st.column_config.NumberColumn(format="%.2f zł"),
                },
            )
