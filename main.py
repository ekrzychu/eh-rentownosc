"""Konsolowe uruchomienie domyślnego modelu."""

from model import oblicz_model


if __name__ == "__main__":
    wynik = oblicz_model()
    ogolem = wynik["ogolem"]
    print(f"Roczny napływ spraw (kohorta referencyjna): {ogolem['liczba_spraw']}")
    print(f"Przychód: {ogolem['przychod']:,.2f} zł")
    print(f"Roczny koszt stały operacji: {wynik['koszt_staly_roczny']:,.2f} zł")
    print(
        "Koszt pracy pracowników dla cyklu kohorty: "
        f"{wynik['koszt_pracy_pracownika_lifecycle']:,.2f} zł"
    )
    print(f"Koszt całkowity: {ogolem['koszt_calkowity']:,.2f} zł")
    print(f"Wynik przed podatkiem: {ogolem['wynik_przed_podatkiem']:,.2f} zł")
    print(f"Podatek dochodowy: {ogolem['podatek_dochodowy']:,.2f} zł")
    print(f"Wynik po podatku: {ogolem['wynik_po_podatku']:,.2f} zł")
