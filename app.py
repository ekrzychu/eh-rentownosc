import pandas as pd
import streamlit as st

from model import (
    DODATKOWE_MINUTY,
    KATEGORIE_SPRAW,
    PODSTAWOWE_CZYNNOSCI,
    domyslne_parametry,
    oblicz_model,
    oblicz_prog_czasu,
    oblicz_prog_fin,
    oblicz_prog_kosztu_stalego,
    oblicz_prog_wynagrodzenia_pracownika,
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
        ("Średni przychód / sprawa", kwota(podsumowanie["sredni_przychod"])),
        ("Średni koszt / sprawa", kwota(podsumowanie["sredni_koszt"])),
        ("Średni wynik / sprawa", kwota(podsumowanie["sredni_wynik"])),
    ]
    return pd.DataFrame(dane, columns=["Pozycja", "Wartość"])


def pokaz_prog_kosztu(tytul: str, dane: dict) -> None:
    st.markdown(f"#### {tytul}")
    if not dane["mozliwe"]:
        st.write("Nie można osiągnąć rentowności wyłącznie przez redukcję tej pozycji. Nawet przy wartości 0 zł/h portfel nadal generowałby stratę.")
        return
    st.write(f"Obecnie: **{kwota(dane['obecnie'])}/h**")
    st.write(f"Próg rentowności: **{kwota(dane['prog'])}/h**")
    if dane["wymagana_redukcja"]:
        udzial = dane["wymagana_redukcja"] / dane["obecnie"] * 100 if dane["obecnie"] else 0.0
        st.write(f"Wymagana redukcja: **{kwota(dane['wymagana_redukcja'])}/h ({procent(udzial)})**")
    else:
        st.write("Portfel jest już rentowny przy obecnych założeniach.")


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

    with st.expander("Koszt pracy"):
        koszt_staly = st.number_input("Koszt stały na godzinę", min_value=0.0, value=domyslne["koszt_staly_na_godzine"], step=1.0)
        wynagrodzenie_pracownika = st.number_input("Wynagrodzenie pracownika na godzinę", min_value=0.0, value=domyslne["wynagrodzenie_pracownika_na_godzine"], step=1.0)
        karta_podsumowania("Łączny koszt godziny", kwota(koszt_staly + wynagrodzenie_pracownika))

    with st.expander("Czas pracy"):
        st.caption("Czynności podstawowe")
        czynnosci = {
            nazwa: st.number_input(nazwa, min_value=0, value=minuty, step=5)
            for nazwa, minuty in PODSTAWOWE_CZYNNOSCI.items()
        }
        st.divider()
        st.caption("Dodatkowy czas według rodzaju sprawy")
        dodatkowe = {
            rodzaj: st.number_input(f"Dodatkowy czas {rodzaj} (min)", min_value=0, value=minuty, step=5)
            for rodzaj, minuty in DODATKOWE_MINUTY.items()
        }
        minuty_podstawowe = sum(czynnosci.values())
        karta_podsumowania("Podstawowy czas", f"{minuty_podstawowe} min / {minuty_podstawowe / 60:.2f} h")
        karta_podsumowania("Podstawowy koszt obsługi sprawy", kwota((koszt_staly + wynagrodzenie_pracownika) * minuty_podstawowe / 60))

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
    "podstawowe_czynnosci": czynnosci, "dodatkowe_minuty": dodatkowe,
    "udzialy_rodzajow": udzialy, "wysoki_wps_procent": wysoki_wps_procent,
}
wyniki = oblicz_model(parametry)
ogolem = wyniki["ogolem"]

kpi = st.columns(4, gap="medium")
kpi[0].metric("Przychód", kwota(ogolem["przychod"]))
kpi[1].metric("Koszt", kwota(ogolem["koszt"]))
kpi[2].metric("Zysk / strata", kwota(ogolem["wynik"]))
kpi[3].metric("Marża", procent(ogolem["marza"]))

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
        "Czas jednej sprawy (h)": (wyniki["podstawowe_minuty"] + dodatkowe[rodzaj]) / 60,
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
        "Czas jednej sprawy (h)": grupa["laczne_minuty"] / 60,
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
        "Czas jednej sprawy (h)": st.column_config.NumberColumn(format="%.2f"),
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
st.subheader("Średni wynik na sprawie według WPS")
st.bar_chart(pd.DataFrame({"Średni wynik": [wyniki["wps_niski"]["sredni_wynik"], wyniki["wps_wysoki"]["sredni_wynik"]]}, index=["WPS poniżej progu", "WPS od progu wzwyż"]), height=260)

st.divider()
st.header("Próg rentowności")
st.caption("Co należy zmienić, aby portfel był rentowny przy obecnych założeniach.")
czas, koszt, efektywnosc = st.columns(3, gap="large")
with czas:
    st.subheader("Czas")
    prog_czasu = oblicz_prog_czasu(parametry)
    st.write(f"Obecny średni czas: **{prog_czasu['obecny_sredni_czas']:.2f} h / sprawa**")
    if not prog_czasu["mozliwe"]:
        st.write("Nie można osiągnąć rentowności wyłącznie poprzez skrócenie czasu w fizycznie możliwym zakresie.")
    elif prog_czasu["juz_rentowny"]:
        st.write("Portfel jest już rentowny przy obecnych założeniach. Wymagana redukcja czasu: **0 min**.")
    else:
        st.write(f"Wymagane skrócenie: **{prog_czasu['redukcja_minut_na_sprawe']:.0f} min / sprawa**")
        st.write(f"Docelowy średni czas: **{prog_czasu['docelowy_sredni_czas']:.2f} h / sprawa**")
with koszt:
    st.subheader("Koszt")
    pokaz_prog_kosztu("Koszt stały na godzinę", oblicz_prog_kosztu_stalego(parametry))
    st.divider()
    pokaz_prog_kosztu("Wynagrodzenie pracownika", oblicz_prog_wynagrodzenia_pracownika(parametry))
with efektywnosc:
    st.subheader("Efektywność")
    prog_fin = oblicz_prog_fin(parametry)
    st.write(f"Obecny FIN: **{procent(fin_percent)} WPS**")
    if not prog_fin["mozliwe"]:
        st.write("Nie można osiągnąć rentowności wyłącznie poprzez poprawę FIN. Nawet przy FIN = 0% WPS portfel pozostaje nierentowny.")
    elif prog_fin["rentowny_w_calym_zakresie"]:
        st.write("Rentowność jest utrzymana w całym dopuszczalnym zakresie FIN (do 100% WPS).")
    else:
        roznica = prog_fin["prog"] - fin_percent
        st.write(f"Maksymalny FIN przy rentowności: **{procent(prog_fin['prog'])} WPS**")
        if roznica < 0:
            st.write(f"Wymagana poprawa: **{roznica:.2f} p.p.**")
        else:
            st.write("Portfel jest już rentowny przy obecnym FIN.")
