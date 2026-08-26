import pandas as pd
import streamlit as st

from analysis import (
    analiza_pojemnosci,
    analiza_wrazliwosci,
    analizuj_progi,
    definicje_parametrow,
    ekonomika_ugod,
    kluczowe_progi,
    ranking_progow,
    rekomendacje_deterministyczne,
    status_operacyjny,
    symuluj_pojedyncza_zmiane,
    wartosc_parametru,
    wartosc_skrocenia_czynnosci,
)
from model import (
    KATEGORIE_SPRAW,
    domyslne_parametry,
    oblicz_model,
    oblicz_udzialy_ugod,
    oblicz_wskazniki_ii_instancji,
)


st.set_page_config(page_title="Analiza rentowności", layout="wide")

st.markdown(
    """
    <style>
        .block-container {
            width: 100%;
            max-width: 1600px;
            padding: 2.5rem clamp(1.25rem, 2vw, 2.5rem) 4rem;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] {margin-bottom: 0.65rem;}
        [data-testid="stSidebar"] [data-testid="stNumberInput"] {margin-bottom: 0.5rem;}
        [data-testid="stMetric"] {padding-top: 0.3rem;}
        [data-testid="stMetricValue"] {white-space: nowrap;}

        @media (max-width: 1600px) {
            [data-testid="stMetricValue"] {
                font-size: 1.6rem;
                letter-spacing: -0.025em;
            }
            [data-testid="stAppViewContainer"] h1 {font-size: 2.25rem;}
        }

        @media (max-width: 1200px) {
            .block-container {padding-left: 1rem; padding-right: 1rem;}
            [data-testid="stMetricValue"] {font-size: 1.38rem;}
            [data-testid="stAppViewContainer"] h1 {font-size: 2rem;}
        }
        .summary-card {
            background: rgba(49, 51, 63, 0.06);
            border-left: 3px solid rgba(49, 51, 63, 1);
            border-radius: 0.3rem;
            margin: 0.75rem 0 0.25rem;
            padding: 0.65rem 0.8rem;
        }
        .summary-card__label {font-size: 0.8rem; color: rgba(250, 250, 250, 0.78);}
        .summary-card__value {font-size: 1rem; font-weight: 600; margin-top: 0.1rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def kwota(wartosc: float) -> str:
    return f"{wartosc:,.2f}".replace(",", " ").replace(".", ",") + " zł"


def procent(wartosc: float) -> str:
    return f"{wartosc:.2f}".replace(".", ",") + "%"


def liczba(wartosc: float, miejsca: int = 1) -> str:
    return f"{wartosc:,.{miejsca}f}".replace(",", " ").replace(".", ",")


def karta_podsumowania(etykieta: str, wartosc: str) -> None:
    st.markdown(
        f'<div class="summary-card"><div class="summary-card__label">{etykieta}</div>'
        f'<div class="summary-card__value">{wartosc}</div></div>',
        unsafe_allow_html=True,
    )


def tabela_podsumowania(podsumowanie: dict) -> pd.DataFrame:
    dane = [
        ("Liczba spraw", f"{podsumowanie['liczba_spraw']:,}".replace(",", " ")),
        ("Przychód", kwota(podsumowanie["przychod"])),
        ("Koszt", kwota(podsumowanie["koszt"])),
        ("Wynik", kwota(podsumowanie["wynik"])),
        ("Średni przychód na sprawę", kwota(podsumowanie["sredni_przychod"])),
        ("Średni koszt na sprawę", kwota(podsumowanie["sredni_koszt"])),
        ("Średni wynik na sprawę", kwota(podsumowanie["sredni_wynik"])),
    ]
    return pd.DataFrame(dane, columns=["Pozycja", "Wartość"])


def formatuj_parametr(wartosc: float | None, jednostka: str) -> str:
    if wartosc is None:
        return "—"
    if jednostka == "p.p.":
        return f"{wartosc:.2f}%".replace(".", ",")
    if jednostka == "spraw":
        return f"{wartosc:.0f} spraw"
    if jednostka == "osób":
        return f"{wartosc:.0f} os."
    if jednostka == "min":
        return f"{wartosc:.1f} min".replace(".", ",")
    if jednostka == "zł/h":
        return f"{wartosc:.2f} zł/h".replace(".", ",")
    if jednostka == "zł":
        return kwota(wartosc)
    return liczba(wartosc, 2)


def formatuj_zmiane(wartosc: float | None, jednostka: str) -> str:
    if wartosc is None:
        return "—"
    znak = "+" if wartosc > 0 else ""
    if jednostka == "spraw":
        return f"{znak}{wartosc:.0f} spraw"
    if jednostka == "osób":
        return f"{znak}{wartosc:.0f} os."
    if jednostka == "min":
        return f"{znak}{wartosc:.1f} min".replace(".", ",")
    return f"{znak}{wartosc:.2f} {jednostka}".replace(".", ",")


def pokaz_kluczowa_granice(
    pozycja: dict,
    cel_spelniony: bool,
    etykieta_obecna: str,
    etykieta_bufora: str,
    etykieta_wymagana: str,
    komunikat_nieosiagalny: str,
) -> None:
    st.write(f"{etykieta_obecna}: **{formatuj_parametr(pozycja['obecnie'], pozycja['jednostka'])}**")
    if not pozycja["osiagalne"]:
        if cel_spelniony:
            st.write("Cel jest utrzymany w całym badanym zakresie tego parametru.")
        else:
            st.write(komunikat_nieosiagalny)
        return
    etykieta = etykieta_bufora if cel_spelniony else etykieta_wymagana
    st.write(f"{etykieta}: **{formatuj_parametr(pozycja['granica'], pozycja['jednostka'])}**")
    st.write(
        f"{'Bufor' if cel_spelniony else 'Wymagana zmiana'}: "
        f"**{formatuj_zmiane(pozycja['zmiana'], pozycja['jednostka'])}**"
    )
    if pozycja["wykonalne_operacyjnie"] is False:
        komunikat = (
            "Granica finansowa przekracza pojemność zespołu."
            if pozycja["wplywa_na_pojemnosc"]
            else "Zmiana nie wpływa na obciążenie; obecny portfel nadal przekracza pojemność zespołu."
        )
        st.caption(f"⚠ {komunikat}")


domyslne = domyslne_parametry()
st.title("Analiza rentowności dla spraw EH")
st.caption("Interaktywny model kosztów, przychodów i rentowności.")
st.write("")

with st.sidebar:
    st.header("Założenia")

    with st.expander("Portfel", expanded=True):
        liczba_spraw = st.number_input("Liczba spraw rocznie", min_value=0, value=domyslne["liczba_spraw"], step=1)
        prog_wps = st.number_input("Próg WPS", min_value=0.0, value=float(domyslne["prog_wps"]), step=500.0)
        fin_percent = st.number_input(
            "Średnia kwota wyroku / ugody (% WPS)", min_value=0.0, max_value=100.0,
            value=domyslne["fin_percent"], step=0.1, format="%.1f",
            help="Np. 70% oznacza, że średnia kwota wyroku/ugody wynosi 70% WPS, czyli jest o 30% niższa od pierwotnego WPS.",
        )
        niski_wps = st.number_input("Średni WPS poniżej progu", min_value=0.0, value=float(domyslne["niski_wps"]), step=100.0)
        wysoki_wps = st.number_input("Średni WPS od progu wzwyż", min_value=0.0, value=float(domyslne["wysoki_wps"]), step=100.0)
        udzial_ii_instancji_percent = st.number_input(
            "Liczba spraw II Instancji (%)",
            min_value=0.0, max_value=100.0,
            value=domyslne["udzial_ii_instancji_percent"], step=0.1, format="%.1f",
            help="Procent spraw niezakończonych ugodą, które wymagają obsługi w II instancji.",
        )
        odmowa_do_podsumowania = st.session_state.get(
            "kategoryczna_odmowa_percent", domyslne["kategoryczna_odmowa_percent"]
        )
        ramy_do_podsumowania = st.session_state.get(
            "automatyczne_ramy_percent", domyslne["automatyczne_ramy_percent"]
        )
        if odmowa_do_podsumowania + ramy_do_podsumowania <= 100 + 1e-9:
            udzialy_do_podsumowania = oblicz_udzialy_ugod(
                odmowa_do_podsumowania,
                ramy_do_podsumowania,
                st.session_state.get("szansa_na_ugode_percent", domyslne["szansa_na_ugode_percent"]),
                st.session_state.get("zawarte_ugody_percent", domyslne["zawarte_ugody_percent"]),
            )
            wskazniki_ii_sidebar = oblicz_wskazniki_ii_instancji(
                liczba_spraw, udzialy_do_podsumowania, udzial_ii_instancji_percent,
                domyslne["obsluga_ii_instancji_minuty"],
            )
            karta_podsumowania("Sprawy bez ugody", f"{procent(udzialy_do_podsumowania['bez_ugody'])} całego portfela")
            karta_podsumowania("Sprawy w II instancji", f"{procent(wskazniki_ii_sidebar['udzial_ii_instancji_w_portfelu'])} całego portfela")
            karta_podsumowania("Oczekiwana liczba spraw w II instancji", liczba(wskazniki_ii_sidebar["oczekiwana_liczba_spraw_ii_instancji"], 1))

    with st.expander("Ugody"):
        kategoryczna_odmowa_percent = st.number_input(
            "Kategoryczna odmowa (%)", min_value=0.0, max_value=100.0,
            value=domyslne["kategoryczna_odmowa_percent"], step=0.1, format="%.1f",
            key="kategoryczna_odmowa_percent",
        )
        automatyczne_ramy_percent = st.number_input(
            "Automatyczne ramy (%)", min_value=0.0, max_value=100.0,
            value=domyslne["automatyczne_ramy_percent"], step=0.1, format="%.1f",
            key="automatyczne_ramy_percent",
        )
        if kategoryczna_odmowa_percent + automatyczne_ramy_percent > 100 + 1e-9:
            st.error("Suma kategorycznej odmowy i automatycznych ram nie może przekraczać 100%.")
            st.stop()

        szansa_na_ugode_percent = st.number_input(
            "Szansa na ugodę poza ramami (% pozostałych spraw)",
            min_value=0.0, max_value=100.0,
            value=domyslne["szansa_na_ugode_percent"], step=0.1, format="%.1f",
            key="szansa_na_ugode_percent",
        )
        st.caption("Podział spraw z szansą na ugodę poza ramami")
        zawarte_ugody_percent = st.number_input(
            "Zawarte ugody (% spraw z szansą na ugodę poza ramami)",
            min_value=0.0, max_value=100.0,
            value=domyslne["zawarte_ugody_percent"], step=0.1, format="%.1f",
            key="zawarte_ugody_percent",
        )
        karta_podsumowania("Brak ugody", procent(100.0 - zawarte_ugody_percent))
        udzialy_ugod = oblicz_udzialy_ugod(
            kategoryczna_odmowa_percent,
            automatyczne_ramy_percent,
            szansa_na_ugode_percent,
            zawarte_ugody_percent,
        )
        brak_szans_percent = 100.0 - szansa_na_ugode_percent
        karta_podsumowania("Pozostałe sprawy", procent(udzialy_ugod["pozostale_sprawy"]))
        karta_podsumowania(
            "Brak szans na ugodę (% pozostałych spraw)", procent(brak_szans_percent)
        )
        st.caption("W tym:")
        st.write(
            "Szansa na ugodę poza ramami: "
            f"**{procent(udzialy_ugod['szansa_poza_ramami'])} całego portfela**"
        )
        st.write(
            "Brak szans na ugodę: "
            f"**{procent(udzialy_ugod['brak_szans'])} całego portfela**"
        )
        st.write(
            "Szansa poza ramami → zawarte ugody: "
            f"**{procent(udzialy_ugod['zawarte_poza_ramami'])} całego portfela**"
        )
        st.write(
            "Szansa poza ramami → brak ugody: "
            f"**{procent(udzialy_ugod['brak_ugody_poza_ramami'])} całego portfela**"
        )
        karta_podsumowania(
            "Łączny udział spraw zakończonych ugodą",
            procent(udzialy_ugod["zakonczone_ugoda"]),
        )
        karta_podsumowania(
            "Łączny udział spraw bez ugody", procent(udzialy_ugod["bez_ugody"])
        )

    with st.expander("Koszt pracy"):
        koszt_staly = st.number_input("Koszt stały na godzinę", min_value=0.0, value=domyslne["koszt_staly_na_godzine"], step=1.0)
        wynagrodzenie_pracownika = st.number_input("Wynagrodzenie pracownika na godzinę", min_value=0.0, value=domyslne["wynagrodzenie_pracownika_na_godzine"], step=1.0)
        liczba_pracownikow = st.number_input(
            "Liczba pracowników", min_value=0,
            value=int(domyslne["liczba_pracownikow"]), step=1,
        )
        liczba_dni_pracy_w_roku = st.number_input(
            "Liczba dni pracy w roku", min_value=0,
            value=int(domyslne["liczba_dni_pracy_w_roku"]), step=1,
        )
        karta_podsumowania("Łączny koszt godziny", kwota(koszt_staly + wynagrodzenie_pracownika))

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
        karta_podsumowania("Czynności procesowe", f"{sum(procesowe_czynnosci.values())} min")
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
        karta_podsumowania("Czynności ugodowe", f"{sum(ugodowe_czynnosci.values())} min")
        st.divider()
        st.caption("II instancja")
        obsluga_ii_instancji_minuty = st.number_input(
            "Obsługa sprawy w II instancji",
            min_value=0,
            value=int(domyslne["obsluga_ii_instancji_minuty"]),
            step=5,
            help="Dodatkowy czas pracy dla spraw bez ugody, które wymagają obsługi w II instancji.",
        )
        wskazniki_ii_czas = oblicz_wskazniki_ii_instancji(
            liczba_spraw, udzialy_ugod, udzial_ii_instancji_percent, obsluga_ii_instancji_minuty
        )
        karta_podsumowania(
            "Oczekiwany dodatkowy czas II instancji",
            f"{liczba(wskazniki_ii_czas['ii_instancja_minuty_na_sprawe_portfela'], 2)} min na sprawę portfela",
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
        karta_podsumowania(
            "Czynności dzienne",
            f"{sum(codzienne_czynnosci.values())} min / pracownik / dzień",
        )

    with st.expander("Specyfika spraw"):
        st.caption("Udział rodzajów spraw")
        udzialy = {
            "P1": st.number_input("Udział P1 (%)", min_value=0.0, max_value=100.0, value=domyslne["udzialy_rodzajow"]["P1"], step=0.1, format="%.1f"),
            "P2": st.number_input("Udział P2 (%)", min_value=0.0, max_value=100.0, value=domyslne["udzialy_rodzajow"]["P2"], step=0.1, format="%.1f"),
            "P3": st.number_input("Udział P3 (%)", min_value=0.0, max_value=100.0, value=domyslne["udzialy_rodzajow"]["P3"], step=0.1, format="%.1f"),
        }
        st.divider()
        st.caption("Podział według WPS")
        wysoki_wps_procent = st.number_input("Udział spraw z WPS od progu wzwyż (%)", min_value=0.0, max_value=100.0, value=domyslne["wysoki_wps_procent"], step=0.1, format="%.1f")
        karta_podsumowania("Udział spraw z WPS poniżej progu", procent(100.0 - wysoki_wps_procent))

if abs(sum(udzialy.values()) - 100) > 1e-9:
    st.error(f"Udziały P1, P2 i P3 muszą sumować się do 100%. Aktualna suma: {procent(sum(udzialy.values()))}.")
    st.stop()
if niski_wps >= prog_wps:
    st.error("Średni WPS poniżej progu musi być mniejszy od progu WPS.")
    st.stop()
if wysoki_wps < prog_wps:
    st.error("Średni WPS od progu wzwyż musi być co najmniej równy progowi WPS.")
    st.stop()

parametry = {
    "liczba_spraw": liczba_spraw, "prog_wps": prog_wps, "fin_percent": fin_percent,
    "niski_wps": niski_wps, "wysoki_wps": wysoki_wps,
    "koszt_staly_na_godzine": koszt_staly, "wynagrodzenie_pracownika_na_godzine": wynagrodzenie_pracownika,
    "liczba_pracownikow": liczba_pracownikow, "liczba_dni_pracy_w_roku": liczba_dni_pracy_w_roku,
    "wspolne_czynnosci": wspolne_czynnosci, "procesowe_czynnosci": procesowe_czynnosci,
    "ugodowe_czynnosci": ugodowe_czynnosci, "analiza_mozliwosci_ugody": analiza_mozliwosci_ugody,
    "codzienne_czynnosci": codzienne_czynnosci, "dodatkowe_minuty": dodatkowe,
    "udzialy_rodzajow": udzialy, "wysoki_wps_procent": wysoki_wps_procent,
    "kategoryczna_odmowa_percent": kategoryczna_odmowa_percent,
    "automatyczne_ramy_percent": automatyczne_ramy_percent,
    "szansa_na_ugode_percent": szansa_na_ugode_percent,
    "zawarte_ugody_percent": zawarte_ugody_percent,
    "udzial_ii_instancji_percent": udzial_ii_instancji_percent,
    "obsluga_ii_instancji_minuty": obsluga_ii_instancji_minuty,
}
wyniki = oblicz_model(parametry)
ogolem = wyniki["ogolem"]

kpi = st.columns(4, gap="medium")
kpi[0].metric("Przychód", kwota(ogolem["przychod"]))
kpi[1].metric("Koszt", kwota(ogolem["koszt"]))
kpi[2].metric("Zysk / strata", kwota(ogolem["wynik"]))
kpi[3].metric("Marża", procent(ogolem["marza"]))

pojemnosc = wyniki["pojemnosc"]
if pojemnosc["brak_czasu_na_sprawy"]:
    st.warning(
        "Czynności dzienne zajmują cały standardowy dzień pracy lub więcej. "
        "Nie pozostaje czas na bezpośrednią obsługę spraw."
    )
elif pojemnosc["przekroczona"]:
    st.warning(
        "Przy obecnej liczbie pracowników portfel wymaga więcej czasu pracy, "
        "niż jest dostępne w ciągu roku.\n\n"
        f"Wymagany czas obsługi spraw: **{liczba(pojemnosc['bezposrednie_minuty_spraw'] / 60)} h**  \n"
        f"Dostępny czas obsługi spraw: **{liczba(max(0.0, pojemnosc['pojemnosc_spraw_minuty']) / 60)} h**"
    )

st.divider()
st.header("Podział według WPS")
st.caption("Porównanie wyników dla spraw poniżej progu oraz od progu wzwyż.")
niski, wysoki = st.columns(2, gap="large")
with niski:
    st.subheader(f"WPS poniżej progu ({prog_wps:,.0f} zł)".replace(",", " "))
    st.dataframe(tabela_podsumowania(wyniki["wps_niski"]), hide_index=True, width="stretch")
with wysoki:
    st.subheader(f"WPS od progu wzwyż ({prog_wps:,.0f} zł)".replace(",", " "))
    st.dataframe(tabela_podsumowania(wyniki["wps_wysoki"]), hide_index=True, width="stretch")

st.divider()
st.header("Porównanie P1 / P2 / P3")
opis_1, opis_2, opis_3 = st.columns(3, gap="medium")
opis_1.caption(f"**P1** — {KATEGORIE_SPRAW['P1']}")
opis_2.caption(f"**P2** — {KATEGORIE_SPRAW['P2']}")
opis_3.caption(f"**P3** — {KATEGORIE_SPRAW['P3']}")
st.write("")

podzial_tabela = pd.DataFrame([
    {"Rodzaj": rodzaj, "Liczba spraw": sum(wartosci.values()), "WPS od progu wzwyż": wartosci["wysoki_wps"], "WPS poniżej progu": wartosci["niski_wps"]}
    for rodzaj, wartosci in wyniki["podzial_spraw"].items()
])
with st.expander("Wyliczony podział portfela"):
    st.dataframe(podzial_tabela, hide_index=True, width="stretch")
    st.caption(f"Łącznie: {ogolem['liczba_spraw']} spraw · WPS od progu wzwyż: {wyniki['wps_wysoki']['liczba_spraw']} · WPS poniżej progu: {wyniki['wps_niski']['liczba_spraw']}")

def wiersz_laczny(rodzaj: str, dane: dict) -> dict:
    liczba = dane["liczba_spraw"]
    return {
        "Rodzaj": rodzaj,
        "Zakres WPS": "Łącznie",
        "Opis": KATEGORIE_SPRAW[rodzaj],
        "Liczba spraw": liczba,
        "Udział w portfelu": liczba / ogolem["liczba_spraw"] * 100 if ogolem["liczba_spraw"] else 0.0,
        "Bezpośredni czas jednej sprawy (h)": (wyniki["srednie_minuty_sciezki_ugody"] + dodatkowe[rodzaj]) / 60,
        "Koszt jednej sprawy": dane["sredni_koszt"],
        "Łączny przychód": dane["przychod"],
        "Łączny koszt": dane["koszt"],
        "Łączny wynik": dane["wynik"],
        "Średni wynik na sprawie": dane["sredni_wynik"],
    }


def wiersz_grupy(grupa: dict, zakres_wps: str) -> dict:
    liczba = grupa["liczba"]
    return {
        "Rodzaj": grupa["rodzaj"],
        "Zakres WPS": zakres_wps,
        "Opis": "",
        "Liczba spraw": liczba,
        "Udział w portfelu": liczba / ogolem["liczba_spraw"] * 100 if ogolem["liczba_spraw"] else 0.0,
        "Bezpośredni czas jednej sprawy (h)": grupa["laczne_minuty"] / 60,
        "Koszt jednej sprawy": grupa["koszt"],
        "Łączny przychód": grupa["laczny_przychod"],
        "Łączny koszt": grupa["laczny_koszt"],
        "Łączny wynik": grupa["laczny_wynik"],
        "Średni wynik na sprawie": grupa["wynik_jednostkowy"],
    }


rodzaje_ogolem = pd.DataFrame([
    wiersz_laczny(rodzaj, dane)
    for rodzaj, dane in wyniki["rodzaje"].items()
])
pokaz_podzial_wps = st.toggle("Pokaż podział według WPS", value=False)

if pokaz_podzial_wps:
    grupy = {(grupa["rodzaj"], grupa["grupa_wps"]): grupa for grupa in wyniki["grupy"]}
    wiersze = []
    for rodzaj, dane in wyniki["rodzaje"].items():
        wiersze.append(wiersz_laczny(rodzaj, dane))
        wiersze.append(wiersz_grupy(grupy[(rodzaj, "niski_wps")], "Poniżej progu"))
        wiersze.append(wiersz_grupy(grupy[(rodzaj, "wysoki_wps")], "Od progu wzwyż"))
    tabela_rodzaje = pd.DataFrame(wiersze)
else:
    tabela_rodzaje = rodzaje_ogolem

st.dataframe(
    tabela_rodzaje, hide_index=True, width="stretch",
    column_config={
        "Udział w portfelu": st.column_config.NumberColumn(format="%.1f%%"),
        "Bezpośredni czas jednej sprawy (h)": st.column_config.NumberColumn(format="%.2f"),
        "Koszt jednej sprawy": st.column_config.NumberColumn(format="%.2f zł"),
        "Łączny przychód": st.column_config.NumberColumn(format="%.2f zł"),
        "Łączny koszt": st.column_config.NumberColumn(format="%.2f zł"),
        "Łączny wynik": st.column_config.NumberColumn(format="%.2f zł"),
        "Średni wynik na sprawie": st.column_config.NumberColumn(format="%.2f zł"),
    },
)

st.divider()
st.header("Wykresy")
kolumna_1, kolumna_2 = st.columns(2, gap="large")
with kolumna_1:
    st.subheader("Przychód, koszt i wynik")
    st.bar_chart(pd.DataFrame({"Kwota": [ogolem["przychod"], ogolem["koszt"], ogolem["wynik"]]}, index=["Przychód", "Koszt", "Wynik"]), height=300)
with kolumna_2:
    st.subheader("Wynik według rodzaju sprawy")
    st.bar_chart(rodzaje_ogolem.set_index("Rodzaj")[["Łączny wynik"]], height=300)
st.subheader("Średni wynik na sprawę według WPS")
st.bar_chart(pd.DataFrame({"Średni wynik": [wyniki["wps_niski"]["sredni_wynik"], wyniki["wps_wysoki"]["sredni_wynik"]]}, index=["WPS poniżej progu", "WPS od progu wzwyż"]), height=260)

st.divider()
st.header("Centrum rentowności i decyzji")
st.caption("Analiza wpływu parametrów, granic rentowności i możliwości poprawy wyniku.")
status_biezacy = status_operacyjny(wyniki)
if not status_biezacy["wykonalne"]:
    wykorzystanie_tekst = (
        procent(status_biezacy["wykorzystanie"])
        if status_biezacy["wykorzystanie"] is not None
        else "brak dostępnej pojemności"
    )
    st.warning(
        "Obecny portfel przekracza pojemność zespołu. "
        f"Wykorzystanie pojemności: **{wykorzystanie_tekst}**. "
        "Ocena finansowa i wykonalność operacyjna są prezentowane oddzielnie."
    )
tab_prog, tab_wrazliwosc, tab_ugody, tab_portfel, tab_symulator, tab_rekomendacje = st.tabs([
    "Próg i bufor", "Wrażliwość", "Ugody", "Portfel i pojemność", "Symulator", "Rekomendacje",
])

with tab_prog:
    stan, cel, status_celu = st.columns([1, 1.25, 1], gap="large")
    stan.metric("Obecna marża", procent(ogolem["marza"]))
    with cel:
        docelowa_marza = st.number_input(
            "Minimalna akceptowalna marża (%)", min_value=0.0, max_value=100.0,
            value=0.0, step=0.5, format="%.1f", key="docelowa_marza",
        )
    roznica_do_celu = ogolem["marza"] - docelowa_marza
    status_celu.metric(
        "Status celu",
        "Cel osiągnięty" if roznica_do_celu >= -1e-7 else f"Brakuje {liczba(abs(roznica_do_celu), 1)} p.p.",
    )
    with st.spinner("Wyznaczanie granic dla bieżących założeń..."):
        analiza_progow = analizuj_progi(parametry, docelowa_marza)
        kluczowe = kluczowe_progi(parametry, docelowa_marza, analiza_progow)

    st.subheader(f"Kluczowe granice dla marży {liczba(docelowa_marza, 1)}%")
    gorna_lewa, gorna_prawa = st.columns(2, gap="large")
    with gorna_lewa:
        st.markdown("#### Czas")
        prog_czasu = kluczowe["sredni_czas_bezposredni"]
        st.write(f"Obecny średni bezpośredni czas: **{liczba(prog_czasu['obecnie'] / 60, 2)} h na sprawę**")
        if not prog_czasu["osiagalne"]:
            if kluczowe["cel_spelniony"]:
                st.write("Cel jest utrzymany w całym badanym zakresie średniego czasu.")
            else:
                st.write("Samo skrócenie bezpośredniej obsługi spraw nie wystarczy do osiągnięcia celu.")
        else:
            etykieta_czasu = "Maksymalny średni czas" if kluczowe["cel_spelniony"] else "Wymagany średni czas"
            st.write(f"{etykieta_czasu}: **{liczba(prog_czasu['granica'] / 60, 2)} h na sprawę**")
            st.write(
                f"{'Bufor' if kluczowe['cel_spelniony'] else 'Wymagana zmiana'}: "
                f"**{formatuj_zmiane(prog_czasu['zmiana'], 'min')} na sprawę**"
            )
            if prog_czasu["wykonalne_operacyjnie"] is False:
                st.caption("⚠ Granica finansowa przekracza pojemność zespołu.")
    with gorna_prawa:
        st.markdown("#### Koszt")
        st.markdown("##### Koszt stały / h")
        pokaz_kluczowa_granice(
            kluczowe["koszt_staly"], kluczowe["cel_spelniony"], "Obecnie",
            "Maksymalnie dla celu", "Wymagany poziom",
            "Sama zmiana kosztu stałego nie wystarczy do osiągnięcia celu.",
        )
        st.markdown("##### Wynagrodzenie pracownika / h")
        pokaz_kluczowa_granice(
            kluczowe["wynagrodzenie"], kluczowe["cel_spelniony"], "Obecnie",
            "Maksymalnie dla celu", "Wymagany poziom",
            "Sama zmiana wynagrodzenia godzinowego nie wystarczy do osiągnięcia celu.",
        )
    dolna_lewa, dolna_prawa = st.columns(2, gap="large")
    with dolna_lewa:
        st.markdown("#### FIN")
        pokaz_kluczowa_granice(
            kluczowe["fin"], kluczowe["cel_spelniony"], "Obecny FIN",
            "Maksymalny FIN dla celu", "Wymagany FIN",
            "Sama zmiana FIN nie wystarczy do osiągnięcia celu.",
        )
    with dolna_prawa:
        st.markdown("#### Ugody")
        pokaz_kluczowa_granice(
            kluczowe["zawarte_ugody"], kluczowe["cel_spelniony"],
            "Obecna skuteczność wśród spraw z szansą poza ramami",
            "Minimalnie dla celu", "Wymagana skuteczność",
            "Sama zmiana skuteczności ugód nie wystarczy do osiągnięcia celu.",
        )
        st.write(
            "Łączny udział całego portfela zakończony ugodą: "
            f"**{procent(wyniki['udzialy_ugod']['zakonczone_ugoda'])}**"
        )

    st.subheader("Pełna analiza granic")
    if analiza_progow["cel_spelniony"]:
        st.success(f"Portfel utrzymuje co najmniej {procent(docelowa_marza)} marży. Granice pokazują, jak daleko mogą pogorszyć się pojedyncze parametry.")
        kolumna_zmiany = "Dostępny bufor"
    else:
        st.warning("Portfel nie posiada obecnie bufora dla wybranego poziomu marży. Poniżej pokazano zmianę wymaganą do osiągnięcia celu.")
        kolumna_zmiany = "Wymagana zmiana"
    tabela_progow = []
    for pozycja in analiza_progow["pozycje"]:
        if pozycja["osiagalne"]:
            granica = formatuj_parametr(pozycja["granica"], pozycja["jednostka"])
            zmiana = formatuj_zmiane(pozycja["zmiana"], pozycja["jednostka"])
        else:
            granica = "Brak granicy w zakresie" if analiza_progow["cel_spelniony"] else "Niewystarczające jako pojedyncza zmiana"
            zmiana = "—"
        if pozycja["wykonalne_operacyjnie"] is None:
            wykonalnosc = "—"
        elif not pozycja["wplywa_na_pojemnosc"]:
            wykonalnosc = "Bez wpływu — stan wykonalny" if pozycja["wykonalne_operacyjnie"] else "Bez wpływu — pojemność przekroczona"
        else:
            wykonalnosc = "Wykonalne" if pozycja["wykonalne_operacyjnie"] else "Przekroczona pojemność"
        tabela_progow.append({"Parametr": pozycja["parametr"], "Grupa": pozycja["kategoria"], "Obecnie": formatuj_parametr(pozycja["obecnie"], pozycja["jednostka"]), "Granica finansowa": granica, kolumna_zmiany: zmiana, "Wykonalność przy granicy": wykonalnosc})
    st.dataframe(pd.DataFrame(tabela_progow), hide_index=True, width="stretch", height=520)
    if analiza_progow["cel_spelniony"]:
        st.subheader("Najmniejsze wykonalne bufory")
        wybrane_progi = ranking_progow(analiza_progow, "bufor")
    else:
        st.subheader("Najkrótsze wykonalne drogi do celu")
        wybrane_progi = ranking_progow(analiza_progow, "wymagana_zmiana")
    if wybrane_progi:
        for pozycja in wybrane_progi:
            st.write(
                f"**{pozycja['parametr']}**: {formatuj_parametr(pozycja['obecnie'], pozycja['jednostka'])} "
                f"→ {formatuj_parametr(pozycja['granica'], pozycja['jednostka'])} "
                f"({formatuj_zmiane(pozycja['zmiana'], pozycja['jednostka'])})"
            )
    else:
        st.write("Brak pojedynczych zmian, które jednocześnie spełniają cel finansowy i mieszczą się w pojemności zespołu.")

with tab_wrazliwosc:
    st.subheader("Analiza wrażliwości")
    st.caption("Ranking pokazuje wpływ jednej standardowej, korzystnej zmiany przy pozostałych założeniach bez zmian.")
    wrazliwosc = analiza_wrazliwosci(parametry)
    tabela_wrazliwosci = pd.DataFrame([{
        "Parametr": x["Parametr"], "Kategoria": x["Kategoria"],
        "Wynik obecny": x["Wynik obecny"],
        "Korzystna zmiana": formatuj_zmiane(x["Zmiana testowa"], x["Jednostka"]),
        "Wynik po poprawie": x["Wynik po poprawie"],
        "Wpływ korzystny": x["Wpływ na wynik roczny"],
        "Wykonalne operacyjnie": "Tak" if x["Wykonalne operacyjnie"] else "Nie",
        "Wykorzystanie po poprawie": x["Wykorzystanie po poprawie"],
        "Niekorzystna zmiana": formatuj_zmiane(x["Zmiana niekorzystna"], x["Jednostka"]),
        "Wynik po pogorszeniu": x["Wynik po pogorszeniu"],
        "Wpływ niekorzystny": x["Wpływ niekorzystny"],
        "Kierunek poprawy": x["Kierunek poprawy"],
    } for x in wrazliwosc])
    st.dataframe(tabela_wrazliwosci, hide_index=True, width="stretch", height=460, column_config={
        "Wynik obecny": st.column_config.NumberColumn(format="%.2f zł"),
        "Wynik po poprawie": st.column_config.NumberColumn(format="%.2f zł"),
        "Wpływ korzystny": st.column_config.NumberColumn(format="%.2f zł"),
        "Wynik po pogorszeniu": st.column_config.NumberColumn(format="%.2f zł"),
        "Wpływ niekorzystny": st.column_config.NumberColumn(format="%.2f zł"),
        "Wykorzystanie po poprawie": st.column_config.NumberColumn(format="%.1f%%"),
    })
    top_wplyw = tabela_wrazliwosci.head(10).set_index("Parametr")[["Wpływ korzystny"]]
    st.bar_chart(top_wplyw, height=320)

    st.subheader("Wartość skrócenia czynności")
    wartosc_minuty = wartosc_skrocenia_czynnosci(parametry)
    st.dataframe(pd.DataFrame(wartosc_minuty), hide_index=True, width="stretch", height=460, column_config={
        "Wpływ skrócenia o 1 min": st.column_config.NumberColumn(format="%.2f zł"),
        "Wpływ skrócenia o 10 min": st.column_config.NumberColumn(format="%.2f zł"),
    })

with tab_ugody:
    st.subheader("Ekonomika ugód")
    ekonomika = ekonomika_ugod(parametry)
    st.caption("Czasy ścieżek nie obejmują dodatkowego czasu P1/P2/P3 ani czynności dziennych pracowników.")
    st.dataframe(pd.DataFrame(ekonomika["sciezki"]), hide_index=True, width="stretch", column_config={
        "Efektywny udział portfela": st.column_config.NumberColumn(format="%.2f%%"),
        "Czas podstawowy ścieżki": st.column_config.NumberColumn(format="%.1f min"),
        "Oczekiwany czas II instancji": st.column_config.NumberColumn(format="%.1f min"),
        "Łączny oczekiwany czas ścieżki": st.column_config.NumberColumn(format="%.1f min"),
        "Oczekiwana liczba spraw": st.column_config.NumberColumn(format="%.1f"),
    })
    st.subheader("Wartość ekonomiczna ścieżek")
    st.dataframe(pd.DataFrame(ekonomika["porownania"]), hide_index=True, width="stretch", column_config={
        "Różnica minut na sprawę": st.column_config.NumberColumn(format="%.1f min"),
        "Różnica PLN na sprawę": st.column_config.NumberColumn(format="%.2f zł"),
        "Wpływ roczny przy obecnym udziale": st.column_config.NumberColumn(format="%.2f zł"),
    })
    st.subheader("Opłacalność prób ugodowych poza ramami")
    u1, u2, u3 = st.columns(3)
    u1.metric("Obecna skuteczność", procent(ekonomika["obecna_skutecznosc"]))
    u2.metric("Minimalna opłacalna skuteczność", procent(ekonomika["minimalna_skutecznosc"]) if ekonomika["minimalna_skutecznosc"] is not None else "Nieosiągalna")
    u3.metric("Bufor", f"{ekonomika['bufor_skutecznosci']:+.2f} p.p.".replace(".", ",") if ekonomika["bufor_skutecznosci"] is not None else "—")
    st.subheader("Wartość poprawy skuteczności")
    st.dataframe(pd.DataFrame([{
        "Zmiana": f"+{x['Zmiana']:.1f} p.p.".replace(".", ","),
        "Wpływ na wynik roczny": x["Wpływ na wynik roczny"],
        "Wykonalne operacyjnie": "Tak" if x["Wykonalne operacyjnie"] else "Nie",
        "Wykorzystanie pojemności": x["Wykorzystanie pojemności"],
    } for x in ekonomika["wartosc_poprawy"]]), hide_index=True, width="stretch", column_config={
        "Wpływ na wynik roczny": st.column_config.NumberColumn(format="%.2f zł"),
        "Wykorzystanie pojemności": st.column_config.NumberColumn(format="%.1f%%"),
    })
    s1, s2 = st.columns(2)
    s1.metric("Wpływ obecnej strategii prób ugodowych", kwota(ekonomika["strategia_wplyw_pln"]))
    s2.metric("Wpływ strategii na czas", f"{ekonomika['strategia_wplyw_godzin']:+.1f} h".replace(".", ","))
    status_bez_prob = ekonomika["strategia_bez_prob_status"]
    st.caption(
        "Scenariusz bez prób ugodowych poza ramami: "
        f"{'wykonalny operacyjnie' if status_bez_prob['wykonalne'] else 'przekracza pojemność zespołu'}; "
        f"wykorzystanie {procent(status_bez_prob['wykorzystanie']) if status_bez_prob['wykorzystanie'] is not None else 'niedostępne'}."
    )

with tab_portfel:
    st.subheader("Portfel i pojemność zespołu")
    pojemnosc_analiza = analiza_pojemnosci(parametry)
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Liczba pracowników", str(pojemnosc_analiza["liczba_pracownikow"]))
    p2.metric("Dni pracy w roku", str(pojemnosc_analiza["dni_pracy"]))
    p3.metric("Dostępne godziny brutto", liczba(pojemnosc_analiza["godziny_brutto"], 1))
    p4.metric("Godziny czynności dziennych", liczba(pojemnosc_analiza["godziny_dzienne"], 1))
    p5, p6, p7, p8 = st.columns(4)
    p5.metric("Dostępne godziny na sprawy", liczba(pojemnosc_analiza["godziny_na_sprawy"], 1))
    p6.metric("Wymagane godziny obsługi", liczba(pojemnosc_analiza["godziny_wymagane"], 1))
    p7.metric("Wykorzystanie pojemności", procent(pojemnosc_analiza["wykorzystanie"]) if pojemnosc_analiza["wykorzystanie"] is not None else "Brak pojemności")
    p8.metric("Wolna pojemność", f"{liczba(pojemnosc_analiza['wolne_godziny'], 1)} h")
    st.write(f"Minimalna liczba pracowników dla obecnego portfela: **{pojemnosc_analiza['minimalni_pracownicy'] if pojemnosc_analiza['minimalni_pracownicy'] is not None else 'powyżej badanego zakresu'}**")
    if pojemnosc_analiza["maksymalne_sprawy"] is None:
        powod = pojemnosc_analiza["powod_braku_maksimum"]
        if powod == "brak_pojemnosci":
            st.write("Czynności dzienne przekraczają dostępną pojemność jeszcze przed rozpoczęciem obsługi spraw.")
        elif powod == "zerowy_czas_sprawy":
            st.write("Nie można wyznaczyć skończonej granicy liczby spraw przy zerowym czasie bezpośrednim.")
        else:
            st.write("Granica liczby spraw znajduje się poza bezpiecznym zakresem analizy.")
    else:
        st.write(f"Maksymalna liczba spraw rocznie przy obecnej obsadzie: **{pojemnosc_analiza['maksymalne_sprawy']}**")
        if pojemnosc_analiza["dodatkowe_sprawy"]:
            st.write(f"Dodatkowa dostępna pojemność: **{pojemnosc_analiza['dodatkowe_sprawy']} spraw**")
        else:
            st.warning("Brak wolnej pojemności przy obecnej obsadzie.")

    st.subheader("Rentowność a wolumen")
    wolumeny = pd.DataFrame(pojemnosc_analiza["wolumeny"])
    st.dataframe(wolumeny, hide_index=True, width="stretch", column_config={
        "Przychód": st.column_config.NumberColumn(format="%.2f zł"), "Koszt": st.column_config.NumberColumn(format="%.2f zł"),
        "Wynik": st.column_config.NumberColumn(format="%.2f zł"), "Marża": st.column_config.NumberColumn(format="%.2f%%"),
        "Wykorzystanie pojemności": st.column_config.NumberColumn(format="%.1f%%"),
    })
    st.line_chart(wolumeny.set_index("Liczba spraw")[["Wynik"]], height=300)
    if pojemnosc_analiza["minimalny_rentowny_wolumen"] is None:
        st.write("Wykonalny zakres pojemności nie zawiera rentownego wolumenu.")
    else:
        st.write(f"Rentowny zakres w granicach pojemności: **{pojemnosc_analiza['minimalny_rentowny_wolumen']}–{pojemnosc_analiza['maksymalny_rentowny_wolumen']} spraw rocznie**")

    st.subheader("Rentowność segmentów")
    segmenty = pd.DataFrame(pojemnosc_analiza["segmenty"])
    st.dataframe(segmenty, hide_index=True, width="stretch", column_config={
        "Przychód na sprawę": st.column_config.NumberColumn(format="%.2f zł"), "Koszt na sprawę": st.column_config.NumberColumn(format="%.2f zł"),
        "Wynik na sprawę": st.column_config.NumberColumn(format="%.2f zł"), "Marża": st.column_config.NumberColumn(format="%.2f%%"),
        "Łączny wynik": st.column_config.NumberColumn(format="%.2f zł"),
    })
    if pojemnosc_analiza["segmenty"]:
        st.write(f"Najbardziej rentowny segment: **{pojemnosc_analiza['segmenty'][0]['Segment']}**")
        st.write(f"Najmniej rentowny segment: **{pojemnosc_analiza['segmenty'][-1]['Segment']}**")

with tab_symulator:
    st.subheader("Symulator pojedynczej zmiany")
    st.caption("Pozostałe parametry pozostają bez zmian. Symulator nie zmienia wartości w panelu bocznym.")
    definicje = definicje_parametrow(parametry)
    definicje_po_id = {x["id"]: x for x in definicje}
    wybrany_id = st.selectbox("Parametr", options=list(definicje_po_id), format_func=lambda x: definicje_po_id[x]["nazwa"])
    if wybrany_id is None:
        st.error("Brak dostępnych parametrów do symulacji.")
        st.stop()
    definicja = definicje_po_id[wybrany_id]
    obecna_wartosc = wartosc_parametru(parametry, wybrany_id)
    if definicja["typ"] == "calkowita":
        nowa_wartosc = st.number_input("Nowa wartość", min_value=int(definicja["min"]), max_value=int(definicja["max"]), value=int(obecna_wartosc), step=1)
    else:
        nowa_wartosc = st.number_input("Nowa wartość", min_value=float(definicja["min"]), max_value=float(definicja["max"]), value=float(obecna_wartosc), step=float(definicja["krok"]))
    symulacja = symuluj_pojedyncza_zmiane(parametry, wybrany_id, nowa_wartosc)
    tabela_symulacji = []
    for nazwa in symulacja["obecnie"]:
        obecna = symulacja["obecnie"][nazwa]
        scenariuszowa = symulacja["scenariusz"][nazwa]
        roznica = symulacja["roznica"][nazwa]
        if nazwa in ("Marża", "Wykorzystanie pojemności"):
            formatuj = lambda x: procent(x) if x is not None else "—"
        elif nazwa == "Godziny pracy":
            formatuj = lambda x: f"{liczba(x, 2)} h" if x is not None else "—"
        else:
            formatuj = lambda x: kwota(x) if x is not None else "—"
        tabela_symulacji.append({"Wskaźnik": nazwa, "Obecnie": formatuj(obecna), "Scenariusz": formatuj(scenariuszowa), "Różnica": formatuj(roznica)})
    st.dataframe(pd.DataFrame(tabela_symulacji), hide_index=True, width="stretch")
    if symulacja["status_operacyjny"]["wykonalne"]:
        st.success("Scenariusz mieści się w dostępnej pojemności zespołu.")
    else:
        st.warning("Scenariusz przekracza dostępną pojemność zespołu.")
    wykorzystanie_symulacji = symulacja["status_operacyjny"]["wykorzystanie"]
    st.write(
        "Wykorzystanie pojemności w scenariuszu: "
        f"**{procent(wykorzystanie_symulacji) if wykorzystanie_symulacji is not None else 'brak dostępnej pojemności'}**"
    )

with tab_rekomendacje:
    st.subheader("Rekomendacje wynikające z modelu")
    rekomendacje = rekomendacje_deterministyczne(wrazliwosc, analiza_progow, ekonomika, pojemnosc_analiza)
    st.markdown("#### Dźwignie operacyjne i zarządcze")
    if rekomendacje["najwiekszy_wplyw"]:
        for numer, dzwignia in enumerate(rekomendacje["najwiekszy_wplyw"], 1):
            st.write(f"{numer}. **{dzwignia['Parametr']}** ({formatuj_zmiane(dzwignia['Zmiana testowa'], dzwignia['Jednostka'])}): {kwota(dzwignia['Wpływ na wynik roczny'])} rocznie")
    else:
        st.write("Brak dodatnich standardowych zmian, które mieszczą się w obecnej pojemności zespołu.")
    st.markdown("#### Czynniki zewnętrzne i strukturalne")
    if rekomendacje["czynniki_zewnetrzne"]:
        for czynnik in rekomendacje["czynniki_zewnetrzne"]:
            st.write(f"**{czynnik['Parametr']}** ({formatuj_zmiane(czynnik['Zmiana testowa'], czynnik['Jednostka'])}): {kwota(czynnik['Wpływ na wynik roczny'])} rocznie")
    else:
        st.write("Brak dodatnich, wykonalnych operacyjnie zmian w tej grupie.")
    if rekomendacje["najslabszy_segment"]:
        st.markdown("#### Najsłabszy i najsilniejszy segment")
        st.write(f"Najsłabszy: **{rekomendacje['najslabszy_segment']['Segment']}** — {kwota(rekomendacje['najslabszy_segment']['Wynik na sprawę'])} na sprawę")
        st.write(f"Najsilniejszy: **{rekomendacje['najsilniejszy_segment']['Segment']}** — {kwota(rekomendacje['najsilniejszy_segment']['Wynik na sprawę'])} na sprawę")
    st.markdown("#### Ugody")
    if ekonomika["minimalna_skutecznosc"] is None:
        st.write("Próby ugodowe poza ramami nie osiągają przewagi czasowej w badanym zakresie skuteczności.")
    else:
        st.write(f"Obecna skuteczność: **{procent(ekonomika['obecna_skutecznosc'])}**; minimalna opłacalna: **{procent(ekonomika['minimalna_skutecznosc'])}**; wpływ strategii: **{kwota(ekonomika['strategia_wplyw_pln'])} rocznie**.")
    st.markdown("#### Pojemność")
    if pojemnosc_analiza["wykorzystanie"] is None:
        st.write("Brak dostępnej pojemności na bezpośrednią obsługę spraw.")
    elif pojemnosc_analiza["wykorzystanie"] > 100:
        st.write(f"Wykorzystanie wynosi **{procent(pojemnosc_analiza['wykorzystanie'])}**. Minimalna wymagana obsada: **{pojemnosc_analiza['minimalni_pracownicy']} pracowników**.")
    else:
        st.write(f"Wykorzystanie wynosi **{procent(pojemnosc_analiza['wykorzystanie'])}**; wolna pojemność to około **{pojemnosc_analiza['dodatkowe_sprawy']} spraw**.")
    if analiza_progow["cel_spelniony"]:
        st.markdown("#### Najmniejsze wykonalne bufory rentowności")
        progi_rekomendacji = rekomendacje["najmniejsze_bufory"]
    else:
        st.markdown("#### Najkrótsze wykonalne drogi do celu")
        progi_rekomendacji = rekomendacje["najkrotsze_drogi"]
    if progi_rekomendacji:
        for pozycja in progi_rekomendacji:
            st.write(f"**{pozycja['parametr']}**: granica {formatuj_parametr(pozycja['granica'], pozycja['jednostka'])}, zmiana {formatuj_zmiane(pozycja['zmiana'], pozycja['jednostka'])}")
    else:
        st.write("Brak pojedynczych, wykonalnych operacyjnie zmian dla wybranego celu marży.")
