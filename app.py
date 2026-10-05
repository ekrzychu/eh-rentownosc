"""Interfejs wejściowy i nawigacja modelu rentowności EH."""

import streamlit as st

from model import domyslne_parametry, oblicz_model
from timeline import GODZINY_ETATU_MIESIECZNIE
from ui_case import renderuj_ekonomike_sprawy
from ui_timeline import renderuj_widok_czasowy


st.set_page_config(page_title="Analiza rentowności", layout="wide")
st.markdown(
    """
    <style>
        .block-container {width: 100%; max-width: 1600px; padding: 2.5rem clamp(1.25rem, 2vw, 2.5rem) 4rem;}
        [data-testid="stSidebar"] [data-testid="stExpander"] {margin-bottom: 0.65rem;}
        [data-testid="stSidebar"] [data-testid="stNumberInput"] {margin-bottom: 0.5rem;}
        [data-testid="stMetricValue"] {white-space: normal; overflow: visible; overflow-wrap: anywhere; line-height: 1.15;}
        @media (max-width: 1600px) {
            [data-testid="stMetricValue"] {font-size: 1.6rem; letter-spacing: -0.025em;}
            [data-testid="stAppViewContainer"] h1 {font-size: 2.25rem;}
        }
        @media (max-width: 1200px) {
            .block-container {padding-left: 1rem; padding-right: 1rem;}
            [data-testid="stMetricValue"] {font-size: 1.38rem;}
            [data-testid="stAppViewContainer"] h1 {font-size: 2rem;}
        }
    </style>
    """,
    unsafe_allow_html=True,
)


domyslne = domyslne_parametry()

with st.sidebar:
    st.header("Założenia")

    with st.expander("Kohorta i finanse", expanded=True):
        liczba_spraw = st.number_input(
            "Roczny napływ spraw", min_value=0, value=domyslne["liczba_spraw"], step=1,
            help="W ekonomice tworzy kohortę referencyjną, a w modelu czasowym napływa stale po 1/12 miesięcznie.",
        )
        prog_wps = st.number_input("Próg WPS", min_value=0.0, value=float(domyslne["prog_wps"]), step=500.0)
        niski_wps = st.number_input("Średni WPS poniżej progu", min_value=0.0, value=float(domyslne["niski_wps"]), step=100.0)
        wysoki_wps = st.number_input("Średni WPS od progu wzwyż", min_value=0.0, value=float(domyslne["wysoki_wps"]), step=100.0)
        srednia_kwota_ugody_percent = st.number_input(
            "Średnia kwota ugody (% WPS)", min_value=0.0, max_value=100.0,
            value=domyslne["srednia_kwota_ugody_percent"], step=0.1, format="%.1f",
        )
        srednia_kwota_wyroku_percent = st.number_input(
            "Średnia kwota wyroku (% WPS)", min_value=0.0, max_value=100.0,
            value=domyslne["srednia_kwota_wyroku_percent"], step=0.1, format="%.1f",
        )
        podatek_dochodowy_percent = st.number_input(
            "Podatek dochodowy (%)", min_value=0.0, max_value=100.0,
            value=domyslne["podatek_dochodowy_percent"], step=0.1, format="%.1f",
            help="Naliczany wyłącznie od dodatniego wyniku przed podatkiem.",
        )
        udzial_ii_instancji_percent = st.number_input(
            "Udział spraw bez ugody w II instancji (%)", min_value=0.0, max_value=100.0,
            value=domyslne["udzial_ii_instancji_percent"], step=0.1, format="%.1f",
        )

    with st.expander("Ugody"):
        kategoryczna_odmowa_percent = st.number_input(
            "Kategoryczna odmowa (%)", min_value=0.0, max_value=100.0,
            value=domyslne["kategoryczna_odmowa_percent"], step=0.1, format="%.1f",
        )
        automatyczne_ramy_percent = st.number_input(
            "Automatyczne ramy (% wszystkich spraw)", min_value=0.0, max_value=100.0,
            value=domyslne["automatyczne_ramy_percent"], step=0.1, format="%.1f",
        )
        skutecznosc_automatycznych_ram_percent = st.number_input(
            "Zawarte ugody w automatycznych ramach (%)",
            min_value=0.0,
            max_value=100.0,
            value=domyslne["skutecznosc_automatycznych_ram_percent"],
            step=0.1,
            format="%.1f",
            help=(
                "Jest to odsetek spraw objętych automatycznymi ramami, które "
                "faktycznie kończą się ugodą. Pozostałe sprawy przechodzą do procesu."
            ),
        )
        szansa_na_ugode_percent = st.number_input(
            "Szansa na ugodę poza ramami (% pozostałych spraw)", min_value=0.0, max_value=100.0,
            value=domyslne["szansa_na_ugode_percent"], step=0.1, format="%.1f",
        )
        zawarte_ugody_percent = st.number_input(
            "Zawarte ugody (% spraw z szansą poza ramami)", min_value=0.0, max_value=100.0,
            value=domyslne["zawarte_ugody_percent"], step=0.1, format="%.1f",
        )

    with st.expander("Koszt pracy"):
        koszt_staly = st.number_input(
            "Narzut kosztów ogólnych / h pracownika", min_value=0.0,
            value=domyslne["koszt_staly_na_godzine"], step=1.0,
            help="Średnia część kosztów ogólnych przypisana do płatnej godziny pracownika.",
        )
        wynagrodzenie_pracownika = st.number_input(
            "Wynagrodzenie pracownika / h", min_value=0.0,
            value=domyslne["wynagrodzenie_pracownika_na_godzine"], step=1.0,
        )
        liczba_pracownikow = st.number_input(
            "Liczba pracowników", min_value=0, value=int(domyslne["liczba_pracownikow"]), step=1,
        )
        st.caption(
            "Ekonomika sprawy wycenia zużyty czas zasobu. Kontrakt w czasie wycenia "
            f"pełne {GODZINY_ETATU_MIESIECZNIE:g} h każdego FTE miesięcznie."
        )

    with st.expander("Czas pracy"):
        st.caption("Czynności wspólne")
        wspolne_czynnosci = {
            nazwa: st.number_input(nazwa, min_value=0, value=minuty, step=5)
            for nazwa, minuty in domyslne["wspolne_czynnosci"].items()
        }
        st.divider()
        st.caption("Czynności procesowe")
        procesowe_czynnosci = {
            nazwa: st.number_input(nazwa, min_value=0, value=minuty, step=5)
            for nazwa, minuty in domyslne["procesowe_czynnosci"].items()
        }
        st.divider()
        st.caption("Czynności ugodowe")
        ugodowe_czynnosci = {
            nazwa: st.number_input(nazwa, min_value=0, value=minuty, step=5)
            for nazwa, minuty in domyslne["ugodowe_czynnosci"].items()
        }
        analiza_mozliwosci_ugody = st.number_input(
            "Analiza możliwości ugody", min_value=0,
            value=domyslne["analiza_mozliwosci_ugody"], step=5,
        )
        st.divider()
        obsluga_ii_instancji_minuty = st.number_input(
            "Obsługa sprawy w II instancji", min_value=0,
            value=int(domyslne["obsluga_ii_instancji_minuty"]), step=5,
        )
        st.divider()
        st.caption("Dodatkowy czas według rodzaju sprawy")
        dodatkowe = {
            rodzaj: st.number_input(f"Dodatkowy czas {rodzaj} (min)", min_value=0, value=minuty, step=5)
            for rodzaj, minuty in domyslne["dodatkowe_minuty"].items()
        }
        st.divider()
        st.caption("Czynności dzienne na pracownika")
        codzienne_czynnosci = {
            nazwa: st.number_input(nazwa, min_value=0, value=minuty, step=5)
            for nazwa, minuty in domyslne["codzienne_czynnosci"].items()
        }

    with st.expander("Specyfika spraw"):
        st.caption("Udział rodzajów spraw")
        udzialy = {
            rodzaj: st.number_input(
                f"Udział {rodzaj} (%)", min_value=0.0, max_value=100.0,
                value=domyslne["udzialy_rodzajow"][rodzaj], step=0.1, format="%.1f",
            )
            for rodzaj in ("P1", "P2", "P3")
        }
        st.divider()
        wysoki_wps_procent = st.number_input(
            "Udział spraw z WPS od progu wzwyż (%)", min_value=0.0, max_value=100.0,
            value=domyslne["wysoki_wps_procent"], step=0.1, format="%.1f",
        )


if kategoryczna_odmowa_percent + automatyczne_ramy_percent > 100 + 1e-9:
    st.error("Suma kategorycznej odmowy i automatycznych ram nie może przekraczać 100%.")
    st.stop()
if abs(sum(udzialy.values()) - 100) > 1e-9:
    st.error(f"Udziały P1, P2 i P3 muszą sumować się do 100% (obecnie {sum(udzialy.values()):.1f}%).")
    st.stop()
if niski_wps >= prog_wps:
    st.error("Średni WPS poniżej progu musi być mniejszy od progu WPS.")
    st.stop()
if wysoki_wps < prog_wps:
    st.error("Średni WPS od progu wzwyż musi być co najmniej równy progowi WPS.")
    st.stop()

parametry = {
    "liczba_spraw": liczba_spraw, "prog_wps": prog_wps,
    "niski_wps": niski_wps, "wysoki_wps": wysoki_wps,
    "koszt_staly_na_godzine": koszt_staly,
    "wynagrodzenie_pracownika_na_godzine": wynagrodzenie_pracownika,
    "wspolne_czynnosci": wspolne_czynnosci,
    "procesowe_czynnosci": procesowe_czynnosci,
    "ugodowe_czynnosci": ugodowe_czynnosci,
    "analiza_mozliwosci_ugody": analiza_mozliwosci_ugody,
    "codzienne_czynnosci": codzienne_czynnosci,
    "dodatkowe_minuty": dodatkowe,
    "udzialy_rodzajow": udzialy,
    "wysoki_wps_procent": wysoki_wps_procent,
    "srednia_kwota_ugody_percent": srednia_kwota_ugody_percent,
    "srednia_kwota_wyroku_percent": srednia_kwota_wyroku_percent,
    "podatek_dochodowy_percent": podatek_dochodowy_percent,
    "kategoryczna_odmowa_percent": kategoryczna_odmowa_percent,
    "automatyczne_ramy_percent": automatyczne_ramy_percent,
    "skutecznosc_automatycznych_ram_percent": (
        skutecznosc_automatycznych_ram_percent
    ),
    "szansa_na_ugode_percent": szansa_na_ugode_percent,
    "zawarte_ugody_percent": zawarte_ugody_percent,
    "udzial_ii_instancji_percent": udzial_ii_instancji_percent,
    "obsluga_ii_instancji_minuty": obsluga_ii_instancji_minuty,
    "liczba_pracownikow": liczba_pracownikow,
}

try:
    wyniki = oblicz_model(parametry)
except ValueError as error:
    st.error(str(error))
    st.stop()

st.title("Analiza rentowności dla spraw EH")
st.caption("Dwa spojrzenia na ten sam model: ekonomika oczekiwanej sprawy oraz wykonalność i wynik kontraktu w czasie.")
widok = st.segmented_control(
    "Widok", ("Ekonomika sprawy", "Kontrakt w czasie"), default="Ekonomika sprawy"
)
st.divider()
if widok == "Kontrakt w czasie":
    renderuj_widok_czasowy(parametry)
else:
    renderuj_ekonomike_sprawy(parametry, wyniki)
