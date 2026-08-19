import pandas as pd
import streamlit as st

from model import DODATKOWE_MINUTY, KATEGORIE_SPRAW, PODSTAWOWE_CZYNNOSCI, domyslne_parametry, oblicz_model


st.set_page_config(page_title="Analiza rentowności", layout="wide")


def kwota(wartosc: float) -> str:
    return f"{wartosc:,.2f}".replace(",", " ").replace(".", ",") + " zł"


def procent(wartosc: float) -> str:
    return f"{wartosc:.2f}".replace(".", ",") + "%"


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


domyslne = domyslne_parametry()
st.title("Analiza rentowności prowadzenia spraw")
st.caption("Interaktywny model kosztów, przychodów i rentowności portfela spraw")

with st.sidebar:
    st.header("Główne założenia")
    st.subheader("Portfel")
    liczba_spraw = st.number_input("Liczba spraw rocznie", min_value=0, value=domyslne["liczba_spraw"], step=1)
    prog_wps = st.number_input("Próg WPS", min_value=0.0, value=float(domyslne["prog_wps"]), step=500.0)
    niski_wps = st.number_input("Średni WPS poniżej progu", min_value=0.0, value=float(domyslne["niski_wps"]), step=100.0)
    wysoki_wps = st.number_input("Średni WPS od progu wzwyż", min_value=0.0, value=float(domyslne["wysoki_wps"]), step=100.0)

    st.subheader("Rodzaje spraw")
    udzialy = {
        "P1": st.number_input("Udział P1 (%)", min_value=0.0, max_value=100.0, value=domyslne["udzialy_rodzajow"]["P1"], step=0.1, format="%.1f"),
        "P2": st.number_input("Udział P2 (%)", min_value=0.0, max_value=100.0, value=domyslne["udzialy_rodzajow"]["P2"], step=0.1, format="%.1f"),
        "P3": st.number_input("Udział P3 (%)", min_value=0.0, max_value=100.0, value=domyslne["udzialy_rodzajow"]["P3"], step=0.1, format="%.1f"),
    }

    st.subheader("Podział WPS")
    wysoki_wps_procent = st.number_input("Udział spraw z WPS od progu wzwyż (%)", min_value=0.0, max_value=100.0, value=domyslne["wysoki_wps_procent"], step=0.1, format="%.1f")
    niski_wps_procent = 100.0 - wysoki_wps_procent
    st.caption(f"Udział spraw z WPS poniżej progu: {procent(niski_wps_procent)}")

    st.subheader("Koszt pracy")
    koszt_staly = st.number_input("Koszt stały na godzinę", min_value=0.0, value=domyslne["koszt_staly_na_godzine"], step=1.0)
    wynagrodzenie_pracownika = st.number_input("Wynagrodzenie pracownika na godzinę", min_value=0.0, value=domyslne["wynagrodzenie_pracownika_na_godzine"], step=1.0)
    st.info(f"Łączny koszt godziny: **{kwota(koszt_staly + wynagrodzenie_pracownika)}**")

    with st.expander("Czas pracy nad sprawą"):
        czynnosci = {nazwa: st.number_input(nazwa, min_value=0, value=minuty, step=5) for nazwa, minuty in PODSTAWOWE_CZYNNOSCI.items()}
        dodatkowe = {rodzaj: st.number_input(f"Dodatkowy czas {rodzaj} (min)", min_value=0, value=minuty, step=5) for rodzaj, minuty in DODATKOWE_MINUTY.items()}
        minuty_podstawowe = sum(czynnosci.values())
        st.write(f"Suma: **{minuty_podstawowe} min / {minuty_podstawowe / 60:.2f} h**")
        st.write(f"Podstawowy koszt obsługi jednej sprawy: **{kwota((koszt_staly + wynagrodzenie_pracownika) * minuty_podstawowe / 60)}**")

suma_udzialow = sum(udzialy.values())
if abs(suma_udzialow - 100) > 1e-9:
    st.error(f"Udziały P1, P2 i P3 muszą sumować się do 100%. Aktualna suma: {procent(suma_udzialow)}.")
    st.stop()
if niski_wps >= prog_wps:
    st.error("Średni WPS poniżej progu musi być mniejszy od progu WPS.")
    st.stop()
if wysoki_wps < prog_wps:
    st.error("Średni WPS od progu wzwyż musi być co najmniej równy progowi WPS.")
    st.stop()

parametry = {
    "liczba_spraw": liczba_spraw, "prog_wps": prog_wps, "niski_wps": niski_wps, "wysoki_wps": wysoki_wps,
    "koszt_staly_na_godzine": koszt_staly, "wynagrodzenie_pracownika_na_godzine": wynagrodzenie_pracownika,
    "podstawowe_czynnosci": czynnosci, "dodatkowe_minuty": dodatkowe,
    "udzialy_rodzajow": udzialy, "wysoki_wps_procent": wysoki_wps_procent,
}
wyniki = oblicz_model(parametry)
ogolem = wyniki["ogolem"]

kpi = st.columns(4)
kpi[0].metric("Przychód", kwota(ogolem["przychod"]))
kpi[1].metric("Koszt", kwota(ogolem["koszt"]))
kpi[2].metric("Zysk / strata", kwota(ogolem["wynik"]))
kpi[3].metric("Marża", procent(ogolem["marza"]))

st.header("Podział według WPS")
niski, wysoki = st.columns(2)
with niski:
    st.subheader(f"WPS poniżej progu ({prog_wps:,.0f} zł)".replace(",", " "))
    st.dataframe(tabela_podsumowania(wyniki["wps_niski"]), hide_index=True, width="stretch")
with wysoki:
    st.subheader(f"WPS od progu wzwyż ({prog_wps:,.0f} zł)".replace(",", " "))
    st.dataframe(tabela_podsumowania(wyniki["wps_wysoki"]), hide_index=True, width="stretch")

st.header("Porównanie P1 / P2 / P3")
st.caption("P1 — koszty naprawy, uprzednie uzgodnienie kosztów | P2 — koszty najmu pojazdu zastępczego, zadośćuczynienie, nieruchomości | P3 — pozostałe sprawy")

podzial_tabela = pd.DataFrame([
    {"Rodzaj": rodzaj, "Liczba spraw": sum(wartosci.values()), "WPS od progu wzwyż": wartosci["wysoki_wps"], "WPS poniżej progu": wartosci["niski_wps"]}
    for rodzaj, wartosci in wyniki["podzial_spraw"].items()
])
with st.expander("Wyliczony podział portfela"):
    st.dataframe(podzial_tabela, hide_index=True, width="stretch")
    st.caption(f"Łącznie: {ogolem['liczba_spraw']} spraw | WPS od progu wzwyż: {wyniki['wps_wysoki']['liczba_spraw']} | WPS poniżej progu: {wyniki['wps_niski']['liczba_spraw']}")

rodzaje = pd.DataFrame([
    {"Rodzaj": rodzaj, "Opis": KATEGORIE_SPRAW[rodzaj], "Liczba spraw": dane["liczba_spraw"], "Udział w portfelu": dane["liczba_spraw"] / ogolem["liczba_spraw"] * 100 if ogolem["liczba_spraw"] else 0.0,
     "Czas jednej sprawy (h)": (wyniki["podstawowe_minuty"] + dodatkowe[rodzaj]) / 60, "Koszt jednej sprawy": dane["sredni_koszt"], "Łączny przychód": dane["przychod"], "Łączny koszt": dane["koszt"], "Łączny wynik": dane["wynik"], "Średni wynik na sprawie": dane["sredni_wynik"]}
    for rodzaj, dane in wyniki["rodzaje"].items()
])
st.dataframe(rodzaje, hide_index=True, width="stretch", column_config={
    "Udział w portfelu": st.column_config.NumberColumn(format="%.1f%%"), "Czas jednej sprawy (h)": st.column_config.NumberColumn(format="%.2f"),
    "Koszt jednej sprawy": st.column_config.NumberColumn(format="%.2f zł"), "Łączny przychód": st.column_config.NumberColumn(format="%.2f zł"),
    "Łączny koszt": st.column_config.NumberColumn(format="%.2f zł"), "Łączny wynik": st.column_config.NumberColumn(format="%.2f zł"), "Średni wynik na sprawie": st.column_config.NumberColumn(format="%.2f zł"),
})

wykres_ogolem = pd.DataFrame({"Kwota": [ogolem["przychod"], ogolem["koszt"], ogolem["wynik"]]}, index=["Przychód", "Koszt", "Wynik"])
kolumna_1, kolumna_2 = st.columns(2)
with kolumna_1:
    st.subheader("Przychód vs koszt vs wynik")
    st.bar_chart(wykres_ogolem)
with kolumna_2:
    st.subheader("Wynik według rodzaju sprawy")
    st.bar_chart(rodzaje.set_index("Rodzaj")[["Łączny wynik"]])

st.subheader("Średni wynik na sprawie według WPS")
st.bar_chart(pd.DataFrame({"Średni wynik": [wyniki["wps_niski"]["sredni_wynik"], wyniki["wps_wysoki"]["sredni_wynik"]]}, index=["WPS poniżej progu", "WPS od progu wzwyż"]))

with st.expander("Szczegóły kalkulacji"):
    st.write("FIN = WPS / 2")
    st.write("Dla WPS poniżej progu: 250 + min(0,20 × (WPS − FIN), 2 000)")
    st.write("Dla WPS od progu wzwyż: 500 + min(0,08 × (WPS − FIN), 5 000)")
    st.write(f"Koszt godziny: **{kwota(wyniki['koszt_godziny'])}**")
    st.write(f"Podstawowe minuty: **{wyniki['podstawowe_minuty']} min**")
    st.write(f"Podstawowe godziny: **{wyniki['podstawowe_minuty'] / 60:.2f} h**")
    st.write(f"Podstawowy koszt: **{kwota(wyniki['koszt_godziny'] * wyniki['podstawowe_minuty'] / 60)}**")
    for rodzaj in dodatkowe:
        minuty = wyniki["podstawowe_minuty"] + dodatkowe[rodzaj]
        st.write(f"{rodzaj}: {minuty} min ({minuty / 60:.2f} h), koszt jednej sprawy: **{kwota(wyniki['koszty_jednostkowe'][rodzaj])}**")
