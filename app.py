"""Interfejs wejściowy i nawigacja modelu rentowności EH."""

import streamlit as st

from model import domyslne_parametry, oblicz_model
from timeline import GODZINY_ETATU_MIESIECZNIE
from staff import ROLE, ETYKIETY_ROL, przywroc_obsade
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
            help="Referencyjny narzut godzinowy wyłącznie w Ekonomice sprawy.",
        )
        wynagrodzenie_pracownika = st.number_input(
            "Wynagrodzenie pracownika / h", min_value=0.0,
            value=domyslne["wynagrodzenie_pracownika_na_godzine"], step=1.0,
        )
        koszt_sekretariatu = st.number_input(
            "Koszt sekretariatu / h", min_value=0.0,
            value=domyslne["koszt_sekretariatu_na_godzine"], step=1.0,
            help="Stawka wyłącznie dla jednorazowych czynności sekretariatu w Ekonomice sprawy.",
        )
        st.caption("Referencyjne stawki dotyczą pełnego cyklu sprawy, niezależnie od obsady kontraktu.")

    with st.expander("Obsada kontraktu"):
        liczba_pracownikow = int(st.number_input(
            "Liczba pracowników", min_value=0, value=int(domyslne["liczba_pracownikow"]), step=1,
            key="liczba_pracownikow",
        ))
        st.caption(
            "Początkowy skład to edytowalny przykład: prawnik EH i prawnik ugody. "
            "Przydział do projektu określa płatne godziny: 167 h × wykorzystanie. "
            "Niewykorzystana pojemność pozostaje opłacona."
        )
        zapisane = przywroc_obsade(st.session_state, liczba_pracownikow)

        def zapisz_osobe(indeks, pole, klucz):
            dane = dict(st.session_state["ustawienia_obsady"])
            dane[indeks] = {**dane[indeks], pole: st.session_state[klucz]}
            st.session_state["ustawienia_obsady"] = dane

        pracownicy = []
        for indeks, osoba in enumerate(zapisane):
            numer = indeks + 1
            st.markdown(f"**Pracownik {numer}**")
            for pole in ("rola", "stawka", "wykorzystanie_percent"):
                klucz = f"pracownik_{indeks}_{pole}"
                if klucz not in st.session_state:
                    st.session_state[klucz] = osoba[pole]
            rola = st.selectbox(
                "Rola:", ROLE, format_func=ETYKIETY_ROL.get, key=f"pracownik_{indeks}_rola",
                on_change=zapisz_osobe, args=(indeks, "rola", f"pracownik_{indeks}_rola"),
            )
            stawka = st.number_input(
                f"Wynagrodzenie pracownika {numer} (zł/h)", min_value=0.0, step=1.0,
                key=f"pracownik_{indeks}_stawka", on_change=zapisz_osobe,
                args=(indeks, "stawka", f"pracownik_{indeks}_stawka"),
            )
            wykorzystanie = st.number_input(
                f"Wykorzystanie pracownika {numer} w projekcie (%)", min_value=0.0, max_value=100.0,
                step=5.0, key=f"pracownik_{indeks}_wykorzystanie_percent", on_change=zapisz_osobe,
                args=(indeks, "wykorzystanie_percent", f"pracownik_{indeks}_wykorzystanie_percent"),
            )
            godziny_projektu = GODZINY_ETATU_MIESIECZNIE * wykorzystanie / 100
            tekst_godzin = f"{godziny_projektu:.2f}".replace(".", ",")
            tekst_plac = f"{godziny_projektu * stawka:.2f}".replace(".", ",")
            st.caption(f"Przydzielone godziny: {tekst_godzin} h/mies. · "
                       f"Wynagrodzenie projektu: {tekst_plac} zł/mies.")
            pracownicy.append({"rola": rola, "stawka": stawka, "wykorzystanie_percent": wykorzystanie})

    with st.expander("Czas pracy"):
        sekretariat_minuty = st.number_input(
            "Czynności sekretariatu (min/sprawę)", min_value=0.0,
            value=domyslne["sekretariat_minuty_na_sprawe"], step=1.0,
            help="Łącznie raz w cyklu sprawy. Nie zużywa pojemności prawników ani mnożnika czynności dziennych.",
        )
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
    "koszt_sekretariatu_na_godzine": koszt_sekretariatu,
    "sekretariat_minuty_na_sprawe": sekretariat_minuty,
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

st.title("Analiza rentowności dla spraw EH")
st.caption("Dwa odrębne rachunki kosztów: ekonomika pełnego cyklu sprawy oraz wynik kontraktu z indywidualną obsadą w czasie.")
widok = st.segmented_control(
    "Widok", ("Ekonomika sprawy", "Kontrakt w czasie"), default="Ekonomika sprawy"
)
st.divider()
if widok == "Kontrakt w czasie":
    renderuj_widok_czasowy(parametry, pracownicy=pracownicy)
else:
    try:
        wyniki = oblicz_model(parametry)
    except ValueError as error:
        st.error(str(error))
        st.stop()
    renderuj_ekonomike_sprawy(parametry, wyniki)
