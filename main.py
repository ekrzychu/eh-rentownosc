"""Konsolowe uruchomienie domyślnego modelu."""

from model import oblicz_model


if __name__ == "__main__":
    wynik = oblicz_model()
    ogolem = wynik["ogolem"]
    print(f"Liczba spraw: {ogolem['liczba_spraw']}")
    print(f"Przychód: {ogolem['przychod']:,.2f} zł")
    print(f"Koszt: {ogolem['koszt']:,.2f} zł")
    print(f"Wynik: {ogolem['wynik']:,.2f} zł")
