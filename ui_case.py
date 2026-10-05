"""Prezentacja ekonomiki oczekiwanej sprawy i kohorty w Streamlit."""

import pandas as pd
import streamlit as st

from analysis import (
    analiza_wrazliwosci,
    analizuj_progi,
    ekonomika_ugod,
    ranking_progow,
    wartosc_skrocenia_czynnosci,
)
from model import KATEGORIE_SPRAW, oblicz_model


def _kwota(wartosc: float) -> str:
    return f"{wartosc:,.2f}".replace(",", " ").replace(".", ",") + " zł"


def _procent(wartosc: float) -> str:
    return f"{wartosc:.2f}".replace(".", ",") + "%"


def _liczba(wartosc: float, miejsca: int = 1) -> str:
    return f"{wartosc:,.{miejsca}f}".replace(",", " ").replace(".", ",")


def _formatuj_parametr(wartosc: float | None, jednostka: str) -> str:
    if wartosc is None:
        return "—"
    if jednostka == "p.p.":
        return f"{wartosc:.2f}%".replace(".", ",")
    if jednostka == "spraw":
        return f"{wartosc:.0f} spraw"
    if jednostka == "min":
        return f"{wartosc:.1f} min".replace(".", ",")
    if jednostka == "zł/h":
        return f"{wartosc:.2f} zł/h".replace(".", ",")
    if jednostka == "zł":
        return _kwota(wartosc)
    return _liczba(wartosc, 2)


def _formatuj_zmiane(wartosc: float | None, jednostka: str) -> str:
    if wartosc is None:
        return "—"
    znak = "+" if wartosc > 0 else ""
    if jednostka == "p.p.":
        return f"{znak}{wartosc:.2f} p.p.".replace(".", ",")
    return f"{znak}{_formatuj_parametr(wartosc, jednostka)}"


def _renderuj_strukture(wyniki: dict) -> None:
    ogolem = wyniki["ogolem"]
    sprawy = ogolem["liczba_spraw"]

    st.subheader("Struktura ekonomiki")
    przychod, koszt = st.columns(2, gap="large")
    with przychod:
        st.markdown("#### Skąd powstaje przychód")
        tabela_przychodu = pd.DataFrame(
            [
                {
                    "Źródło": "Ugody",
                    "Łącznie": ogolem["przychod_ugody"],
                    "Na sprawę": ogolem["przychod_ugody"] / sprawy if sprawy else 0.0,
                },
                {
                    "Źródło": "Wyroki",
                    "Łącznie": ogolem["przychod_wyroki"],
                    "Na sprawę": ogolem["przychod_wyroki"] / sprawy if sprawy else 0.0,
                },
                {
                    "Źródło": "Razem",
                    "Łącznie": ogolem["przychod"],
                    "Na sprawę": ogolem["sredni_przychod"],
                },
            ]
        )
        st.dataframe(
            tabela_przychodu,
            hide_index=True,
            width="stretch",
            column_config={
                "Łącznie": st.column_config.NumberColumn(format="%.2f zł"),
                "Na sprawę": st.column_config.NumberColumn(format="%.2f zł"),
            },
        )
    with koszt:
        st.markdown("#### Z czego składa się koszt zasobu")
        tabela_kosztu = pd.DataFrame(
            [
                {
                    "Składnik": "Narzut kosztów ogólnych",
                    "Stawka": wyniki["narzut_kosztow_ogolnych_na_godzine"],
                    "Łącznie": wyniki["koszt_narzutu_ogolnego_lifecycle"],
                    "Na sprawę": wyniki["koszt_narzutu_ogolnego_lifecycle"] / sprawy if sprawy else 0.0,
                },
                {
                    "Składnik": "Wynagrodzenie",
                    "Stawka": wyniki["wynagrodzenie_pracownika_na_godzine"],
                    "Łącznie": wyniki["koszt_wynagrodzen_lifecycle"],
                    "Na sprawę": wyniki["koszt_wynagrodzen_lifecycle"] / sprawy if sprawy else 0.0,
                },
                {
                    "Składnik": "Razem",
                    "Stawka": wyniki["koszt_zasobu_na_godzine"],
                    "Łącznie": wyniki["koszt_lifecycle_razem"],
                    "Na sprawę": ogolem["sredni_koszt"],
                },
            ]
        )
        st.dataframe(
            tabela_kosztu,
            hide_index=True,
            width="stretch",
            column_config={
                "Stawka": st.column_config.NumberColumn(format="%.2f zł/h"),
                "Łącznie": st.column_config.NumberColumn(format="%.2f zł"),
                "Na sprawę": st.column_config.NumberColumn(format="%.2f zł"),
            },
        )

    czas = st.columns(3, gap="large")
    czas[0].metric(
        "Bezpośredni czas / sprawę",
        f"{_liczba(wyniki['bezposrednie_minuty_spraw'] / sprawy / 60 if sprawy else 0.0, 2)} h",
    )
    czas[1].metric(
        "Płatny czas zasobu / sprawę",
        f"{_liczba(wyniki['laczne_godziny_zasobu_lifecycle'] / sprawy if sprawy else 0.0, 2)} h",
    )
    czas[2].metric(
        "Czynności dzienne kohorty",
        f"{_liczba(wyniki['czynnosci_dzienne_lifecycle_godziny'], 1)} h",
        help=(
            "Czynności dzienne mieszczą się w płatnym dniu pracy i zwiększają "
            "czas zasobu potrzebny do wykonania pracy bezpośredniej."
        ),
    )


def _renderuj_dzwignie(parametry: dict) -> list[dict]:
    st.subheader("Najważniejsze dźwignie")
    st.caption(
        "Każda zmiana jest liczona osobno. Wpływów nie należy sumować bez "
        "ponownego przeliczenia całego scenariusza."
    )
    wrazliwosc = analiza_wrazliwosci(parametry, zmiana_percent=10.0)
    top = [wiersz for wiersz in wrazliwosc if wiersz["Wpływ korzystny"] > 0][:5]
    if top:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Dźwignia": x["Parametr"],
                        "Kierunek": x["Kierunek poprawy"],
                        "Testowana zmiana": x["Korzystna zmiana (%)"],
                        "Wpływ na wynik kohorty": x["Wpływ korzystny"],
                        "Zmiana marży": x["Wpływ korzystny na marżę"],
                    }
                    for x in top
                ]
            ),
            hide_index=True,
            width="stretch",
            column_config={
                "Testowana zmiana": st.column_config.NumberColumn(format="%+.1f%%"),
                "Wpływ na wynik kohorty": st.column_config.NumberColumn(format="%.2f zł"),
                "Zmiana marży": st.column_config.NumberColumn(format="%+.2f p.p."),
            },
        )
    else:
        st.info("Brak dodatniego wpływu pojedynczej zmiany w badanym zakresie.")

    wartosc_czasu = wartosc_skrocenia_czynnosci(parametry)
    st.markdown("#### Gdzie minuta oszczędności ma największą wartość")
    st.dataframe(
        pd.DataFrame(wartosc_czasu[:5]),
        hide_index=True,
        width="stretch",
        column_config={
            "Wpływ skrócenia o 1 min": st.column_config.NumberColumn(format="%.2f zł"),
            "Wpływ skrócenia o 10 min": st.column_config.NumberColumn(format="%.2f zł"),
        },
    )
    return wrazliwosc


def _renderuj_ugody(parametry: dict) -> None:
    ekonomika = ekonomika_ugod(parametry)
    st.caption(
        "Ta analiza pokazuje osobno wpływ ugód na przychód oraz na wymagany czas zasobu."
    )
    st.dataframe(
        pd.DataFrame(ekonomika["przychod_wedlug_zakonczenia"]),
        hide_index=True,
        width="stretch",
        column_config={
            "Oczekiwany udział": st.column_config.NumberColumn(format="%.2f%%"),
            "Oczekiwana liczba spraw": st.column_config.NumberColumn(format="%.2f"),
            "Oczekiwany przychód": st.column_config.NumberColumn(format="%.2f zł"),
        },
    )
    st.markdown("##### Czas i wartość ścieżek")
    st.dataframe(
        pd.DataFrame(ekonomika["porownania"]),
        hide_index=True,
        width="stretch",
        column_config={
            "Różnica minut na sprawę": st.column_config.NumberColumn(format="%.1f min"),
            "Różnica PLN na sprawę": st.column_config.NumberColumn(format="%.2f zł"),
            "Wpływ roczny przy obecnym udziale": st.column_config.NumberColumn(format="%.2f zł"),
        },
    )
    prog = ekonomika["minimalna_skutecznosc"]
    st.write(
        "Minimalna opłacalna skuteczność prób ugodowych poza ramami: "
        f"**{_procent(prog) if prog is not None else 'nieosiągalna'}**."
    )


def _renderuj_segmenty(wyniki: dict) -> None:
    wiersze = []
    for grupa in wyniki["grupy"]:
        przychod = grupa["oczekiwane_wynagrodzenie"]
        wynik = grupa["wynik_jednostkowy_przed_podatkiem"]
        wiersze.append(
            {
                "Segment": f"{grupa['rodzaj']} / {'WPS poniżej progu' if grupa['grupa_wps'] == 'niski_wps' else 'WPS od progu wzwyż'}",
                "Opis": KATEGORIE_SPRAW[grupa["rodzaj"]],
                "Oczekiwana liczba spraw": grupa["liczba"],
                "Przychód / sprawę": przychod,
                "Koszt / sprawę": grupa["koszt_calkowity"],
                "Wynik / sprawę": wynik,
                "Marża przed podatkiem": wynik / przychod * 100 if przychod else 0.0,
            }
        )
    st.dataframe(
        pd.DataFrame(wiersze),
        hide_index=True,
        width="stretch",
        column_config={
            "Oczekiwana liczba spraw": st.column_config.NumberColumn(format="%.2f"),
            "Przychód / sprawę": st.column_config.NumberColumn(format="%.2f zł"),
            "Koszt / sprawę": st.column_config.NumberColumn(format="%.2f zł"),
            "Wynik / sprawę": st.column_config.NumberColumn(format="%.2f zł"),
            "Marża przed podatkiem": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )


def _renderuj_wps(wyniki: dict) -> None:
    dane = []
    for nazwa, etykieta in (
        ("wps_niski", "WPS poniżej progu"),
        ("wps_wysoki", "WPS od progu wzwyż"),
    ):
        grupa = wyniki[nazwa]
        dane.append(
            {
                "Zakres": etykieta,
                "Oczekiwana liczba spraw": grupa["liczba_spraw"],
                "Przychód": grupa["przychod"],
                "Koszt": grupa["koszt_calkowity"],
                "Wynik przed podatkiem": grupa["wynik_przed_podatkiem"],
                "Marża przed podatkiem": grupa["marza_przed_podatkiem"],
            }
        )
    st.dataframe(
        pd.DataFrame(dane),
        hide_index=True,
        width="stretch",
        column_config={
            "Oczekiwana liczba spraw": st.column_config.NumberColumn(format="%.2f"),
            "Przychód": st.column_config.NumberColumn(format="%.2f zł"),
            "Koszt": st.column_config.NumberColumn(format="%.2f zł"),
            "Wynik przed podatkiem": st.column_config.NumberColumn(format="%.2f zł"),
            "Marża przed podatkiem": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )


def _renderuj_wrazliwosc(wrazliwosc: list[dict]) -> None:
    tabela = pd.DataFrame(
        [
            {
                "Parametr": x["Parametr"],
                "Kategoria": x["Kategoria"],
                "Kierunek poprawy": x["Kierunek poprawy"],
                "Wpływ korzystny": x["Wpływ korzystny"],
                "Wpływ korzystny na marżę": x["Wpływ korzystny na marżę"],
                "Wpływ niekorzystny": x["Wpływ niekorzystny"],
                "Wpływ niekorzystny na marżę": x["Wpływ niekorzystny na marżę"],
            }
            for x in wrazliwosc
        ]
    )
    st.dataframe(
        tabela,
        hide_index=True,
        width="stretch",
        height=480,
        column_config={
            "Wpływ korzystny": st.column_config.NumberColumn(format="%.2f zł"),
            "Wpływ korzystny na marżę": st.column_config.NumberColumn(format="%+.2f p.p."),
            "Wpływ niekorzystny": st.column_config.NumberColumn(format="%.2f zł"),
            "Wpływ niekorzystny na marżę": st.column_config.NumberColumn(format="%+.2f p.p."),
        },
    )


def _renderuj_granice(parametry: dict) -> None:
    cel = st.number_input(
        "Minimalna akceptowalna marża po podatku (%)",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=0.5,
        key="case_docelowa_marza",
    )
    if not st.toggle("Oblicz bufory i granice", value=False, key="case_oblicz_granice"):
        st.caption("Obliczenie granic jest dostępne na żądanie, ponieważ wymaga wielu przeliczeń modelu.")
        return
    with st.spinner("Wyznaczanie granic dla bieżących założeń..."):
        progi = analizuj_progi(parametry, float(cel))
    typ = "bufor" if progi["cel_spelniony"] else "wymagana_zmiana"
    ranking = ranking_progow(
        progi,
        typ,
        limit=5,
        tylko_sterowalne=not progi["cel_spelniony"],
    )
    if ranking:
        st.markdown("##### Najważniejsze granice")
        for pozycja in ranking:
            st.write(
                f"**{pozycja['parametr']}**: "
                f"{_formatuj_parametr(pozycja['obecnie'], pozycja['jednostka'])} → "
                f"{_formatuj_parametr(pozycja['granica'], pozycja['jednostka'])} "
                f"({_formatuj_zmiane(pozycja['zmiana'], pozycja['jednostka'])})"
            )
    tabela = pd.DataFrame(
        [
            {
                "Parametr": x["parametr"],
                "Grupa": x["kategoria"],
                "Obecnie": _formatuj_parametr(x["obecnie"], x["jednostka"]),
                "Granica": _formatuj_parametr(x["granica"], x["jednostka"]),
                "Zmiana": _formatuj_zmiane(x["zmiana"], x["jednostka"]),
            }
            for x in progi["pozycje"]
        ]
    )
    st.dataframe(tabela, hide_index=True, width="stretch", height=520)


def renderuj_ekonomike_sprawy(parametry: dict, wyniki: dict | None = None) -> None:
    """Renderuje ekonomię jednostkową, dźwignie i analizy pogłębione."""
    if wyniki is None:
        wyniki = oblicz_model(parametry)
    ogolem = wyniki["ogolem"]
    sprawy = ogolem["liczba_spraw"]
    wynik_po_podatku_na_sprawe = ogolem["wynik_po_podatku"] / sprawy if sprawy else 0.0

    st.header("Ekonomika sprawy")
    st.caption(
        "Co tworzy przychód i koszt oczekiwanej sprawy oraz które kontrolowalne "
        "czynniki mają największą wartość ekonomiczną."
    )
    kpi = st.columns(4, gap="medium", wrap=True)
    kpi[0].metric("Przychód / sprawę", _kwota(ogolem["sredni_przychod"]))
    kpi[1].metric("Koszt / sprawę", _kwota(ogolem["sredni_koszt"]))
    kpi[2].metric("Wynik / sprawę", _kwota(wynik_po_podatku_na_sprawe))
    kpi[3].metric("Marża po podatku", _procent(ogolem["marza_po_podatku"]))

    with st.expander("Wartości całej kohorty", expanded=False):
        suma = st.columns(4, wrap=True)
        suma[0].metric("Oczekiwana liczba spraw", _liczba(sprawy, 1))
        suma[1].metric("Przychód", _kwota(ogolem["przychod"]))
        suma[2].metric("Koszt", _kwota(ogolem["koszt_calkowity"]))
        suma[3].metric("Wynik po podatku", _kwota(ogolem["wynik_po_podatku"]))

    _renderuj_strukture(wyniki)
    wrazliwosc = _renderuj_dzwignie(parametry)

    st.subheader("Analizy pogłębione")
    with st.expander("Ugody", expanded=False):
        _renderuj_ugody(parametry)
    with st.expander("P1 / P2 / P3", expanded=False):
        _renderuj_segmenty(wyniki)
    with st.expander("WPS", expanded=False):
        _renderuj_wps(wyniki)
    with st.expander("Wrażliwość", expanded=False):
        _renderuj_wrazliwosc(wrazliwosc)
    with st.expander("Bufory i granice rentowności", expanded=False):
        _renderuj_granice(parametry)
    with st.expander("Szczegóły finansowe i podatek", expanded=False):
        szczegoly = pd.DataFrame(
            [
                {"Pozycja": "Wynik przed podatkiem", "Wartość": ogolem["wynik_przed_podatkiem"]},
                {"Pozycja": "Podatek dochodowy", "Wartość": ogolem["podatek_dochodowy"]},
                {"Pozycja": "Wynik po podatku", "Wartość": ogolem["wynik_po_podatku"]},
            ]
        )
        st.dataframe(
            szczegoly,
            hide_index=True,
            width="stretch",
            column_config={"Wartość": st.column_config.NumberColumn(format="%.2f zł")},
        )
        st.caption(
            f"Podatek: {_procent(parametry['podatek_dochodowy_percent'])}. "
            "Jest naliczany wyłącznie od dodatniego wyniku przed podatkiem."
        )
