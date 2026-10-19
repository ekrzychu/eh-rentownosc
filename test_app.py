import unittest

from streamlit.testing.v1 import AppTest


class TestGlowneWidoki(unittest.TestCase):
    @staticmethod
    def ustaw(app, label, value):
        next(x for x in app.number_input if x.label == label).set_value(value)
        return app

    def test_zero_ii_pokazuje_dojrzaly_wynik_i_trwaly_break_even(self):
        app = AppTest.from_file("app.py", default_timeout=30).run()
        self.ustaw(app, "Liczba pracowników", 4).run()
        for i in range(1, 5):
            self.ustaw(app, f"Wynagrodzenie pracownika {i} (zł/h)", 20.0)
        self.ustaw(app, "Udział spraw bez ugody w II instancji (%)", 0.0)
        app.segmented_control[0].set_value("Kontrakt w czasie").run()
        self.ustaw(app, "Horyzont analizy (mies.)", 24).run()
        self.assertFalse(app.exception)
        metrics = {x.label: x.value for x in app.metric}
        self.assertEqual(metrics["Stan stabilny"], "Osiągnięty")
        self.assertEqual(metrics["Break-even finansowy"], "Miesiąc 12")
        self.assertTrue(any("Ocena trwałości: **Break-even trwały**" in x.value for x in app.markdown))
        self.assertTrue(any("24 303,60 zł" in x.value for x in app.markdown))

    def test_450_minut_dziennych_nie_przerywa_analiz(self):
        from model import domyslne_parametry

        app = AppTest.from_file("app.py", default_timeout=30).run()
        for label, value in zip(domyslne_parametry()["codzienne_czynnosci"], (450, 0, 0)):
            next(x for x in app.number_input if x.label == label).set_value(value)
        app.run()
        self.assertFalse(app.exception)
        self.assertIn("Ekonomika sprawy", [x.value for x in app.header])
        self.assertIn("Analizy pogłębione", [x.value for x in app.subheader])
        self.assertIn("Wrażliwość", [x.label for x in app.expander])
        tabela = next(x.value for x in app.dataframe if "Wpływ niekorzystny" in x.value.columns)
        wiersz = tabela.loc[tabela["Parametr"] == "Obsługa skrzynki ugody EH"].iloc[0]
        self.assertGreater(wiersz["Wpływ korzystny"], 0)
        self.assertTrue(tabela.loc[tabela["Parametr"] == "Obsługa skrzynki ugody EH", "Wpływ niekorzystny"].isna().all())

    def test_neutralna_wrazliwosc_z_brakujacymi_kierunkami_renderuje_sie(self):
        app = AppTest.from_file("app.py", default_timeout=30).run()
        for label in ("Narzut kosztów ogólnych / h pracownika", "Wynagrodzenie pracownika 1 (zł/h)", "Wynagrodzenie pracownika 2 (zł/h)"):
            next(x for x in app.number_input if x.label == label).set_value(0.0)
        app.run()
        self.assertFalse(app.exception)
        tabela = next(x.value for x in app.dataframe if "Dźwignia" in x.value.columns)
        self.assertTrue((tabela["Wpływ na wynik kohorty"] > 0).all())
        szczegoly = next(x.value for x in app.dataframe if "Wpływ niekorzystny" in x.value.columns)
        self.assertTrue(szczegoly.loc[szczegoly["Parametr"] == "Duplika", "Wpływ korzystny"].isna().all())

    def test_niepelny_rozruch_nie_potwierdza_rentownosci(self):
        app = AppTest.from_file("app.py", default_timeout=30).run()
        self.ustaw(app, "Liczba pracowników", 4).run()
        for i in range(1, 5):
            self.ustaw(app, f"Wynagrodzenie pracownika {i} (zł/h)", 20.0)
        app.segmented_control[0].set_value("Kontrakt w czasie").run()
        self.ustaw(app, "Horyzont analizy (mies.)", 12).run()
        self.assertFalse(app.exception)
        metrics = {x.label: x.value for x in app.metric}
        self.assertEqual(metrics["Status kontraktu"], "Stabilny operacyjnie, rentowność niepotwierdzona")
        self.assertNotIn("Skumulowany wynik ma trwały trend spadkowy.", [x.value for x in app.caption])

    def test_obydwa_widoki_renderuja_sie_bez_bledow(self):
        app = AppTest.from_file("app.py", default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.segmented_control), 1)
        self.assertEqual(
            app.segmented_control[0].options,
            ["Ekonomika sprawy", "Kontrakt w czasie"],
        )
        self.assertIn("Ekonomika sprawy", [header.value for header in app.header])
        self.assertTrue(
            {"Przychód / sprawę", "Koszt / sprawę", "Wynik / sprawę", "Marża po podatku"}
            .issubset({metric.label for metric in app.metric})
        )

        self.assertIn("Wpływ zmiany parametrów o 10%", [x.value for x in app.subheader])
        self.assertTrue(any("około 10%" in x.value and "trudności wdrożenia" in x.value for x in app.caption))
        self.assertFalse(app.warning)

        app.segmented_control[0].set_value("Kontrakt w czasie").run()
        self.assertFalse(app.exception)
        self.assertIn("Kontrakt w czasie", [header.value for header in app.header])
        self.assertTrue(
            {
                "Status kontraktu",
                "Break-even finansowy",
                "Najniższy wynik do 60 mies.",
                "Obsada",
                "Backlog",
            }.issubset({metric.label for metric in app.metric})
        )

    def test_diagnostyka_rol_zamiast_fikcyjnej_minimalnej_obsady(self):
        app = AppTest.from_file("app.py", default_timeout=30).run()
        app.segmented_control[0].set_value("Kontrakt w czasie").run()
        self.assertFalse(app.exception)
        metryki = {x.label: x.value for x in app.metric}
        self.assertIn("Niedobór pojemności EH", metryki)
        self.assertIn("Dostępna pojemność ugód", metryki)
        self.assertNotIn("Minimalna stabilna obsada", metryki)
        self.assertEqual(metryki["Status kontraktu"], "Niewystarczająca pojemność według roli")
        self.ustaw(app, "Liczba pracowników", 4).run()
        self.assertFalse(app.exception)
        self.assertEqual(next(x.value for x in app.metric if x.label == "Stan stabilny"), "Osiągnięty")


class TestIndywidualniPracownicy(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file("app.py", default_timeout=30).run()

    def number(self, label):
        return next(x for x in self.app.number_input if x.label == label)

    def test_Z_indywidualne_role_stawki_i_przydzialy(self):
        from config import wczytaj_defaults
        self.assertEqual([x.value for x in self.app.selectbox if x.label == "Rola:"], ["EH", "UGODY"])
        for i in (1, 2):
            self.assertEqual(self.number(f"Wynagrodzenie pracownika {i} (zł/h)").value,
                             wczytaj_defaults()["obsada"]["stawka_poczatkowa"])
            self.assertEqual(self.number(f"Wykorzystanie pracownika {i} w projekcie (%)").value, 100)
        self.number("Wynagrodzenie pracownika 1 (zł/h)").set_value(60.0)
        self.number("Wykorzystanie pracownika 1 w projekcie (%)").set_value(60.0)
        self.number("Wykorzystanie pracownika 2 w projekcie (%)").set_value(0.0)
        self.app.segmented_control[0].set_value("Kontrakt w czasie").run()
        self.assertFalse(self.app.exception)
        df = next(x.value for x in self.app.dataframe if "Koszt wynagrodzeń EH" in x.value.columns)
        self.assertAlmostEqual(df.iloc[0]["Koszt wynagrodzeń EH"], 6012)
        self.assertEqual(df.iloc[0]["Koszt wynagrodzeń ugód"], 0)

    def test_N_usuniecie_i_powrot_pracownika_zachowuje_ustawienia(self):
        self.number("Wynagrodzenie pracownika 1 (zł/h)").set_value(72.0)
        self.number("Wynagrodzenie pracownika 2 (zł/h)").set_value(91.0)
        self.number("Wykorzystanie pracownika 2 w projekcie (%)").set_value(35.0)
        self.app.selectbox[1].set_value("EH").run()
        self.number("Liczba pracowników").set_value(1).run()
        self.number("Liczba pracowników").set_value(3).run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.number("Wynagrodzenie pracownika 1 (zł/h)").value, 72)
        self.assertEqual(self.number("Wynagrodzenie pracownika 2 (zł/h)").value, 91)
        self.assertEqual(self.number("Wykorzystanie pracownika 2 w projekcie (%)").value, 35)
        self.assertEqual(self.app.selectbox[1].value, "EH")
        self.number("Liczba pracowników").set_value(0).run()
        self.number("Liczba pracowników").set_value(2).run()
        self.assertEqual(self.number("Wynagrodzenie pracownika 2 (zł/h)").value, 91)

    def test_zalozenia_kosztowe_przetrwaja_zmiane_widoku(self):
        self.number("Koszt sekretariatu / h").set_value(50.0)
        self.number("Czynności sekretariatu (min/sprawę)").set_value(10.0)
        self.app.run()
        case_cost = next(x.value for x in self.app.metric if x.label == "Koszt / sprawę")
        self.app.segmented_control[0].set_value("Kontrakt w czasie").run()
        self.number("Koszty ogólne / aktywną sprawę / mies.").set_value(43.0)
        self.number("Koszt sekretariatu / aktywną sprawę / mies.").set_value(7.0)
        self.number("Opóźnienie płatności (mies.)").set_value(3).run()
        df = next(x.value for x in self.app.dataframe if "Koszt wynagrodzeń EH" in x.value.columns)
        self.assertEqual(df.iloc[0]["Koszty ogólne aktywnych spraw"], 2150)
        self.assertEqual(df.iloc[0]["Koszt sekretariatu aktywnych spraw"], 350)
        self.app.segmented_control[0].set_value("Ekonomika sprawy").run()
        self.assertEqual(next(x.value for x in self.app.metric if x.label == "Koszt / sprawę"), case_cost)
        self.app.segmented_control[0].set_value("Kontrakt w czasie").run()
        self.assertEqual(self.number("Koszty ogólne / aktywną sprawę / mies.").value, 43)
        self.assertEqual(self.number("Koszt sekretariatu / aktywną sprawę / mies.").value, 7)
        self.assertEqual(self.number("Opóźnienie płatności (mies.)").value, 3)
        self.assertFalse(self.app.exception)

    def test_zero_pracownikow_renderuje_kontrakt(self):
        self.number("Liczba pracowników").set_value(0)
        self.app.segmented_control[0].set_value("Kontrakt w czasie").run()
        self.assertFalse(self.app.exception)
        self.assertEqual(next(x.value for x in self.app.metric if x.label == "Obsada"), "0 os.")


class TestNiezaleznoscWalidacjiWidokow(unittest.TestCase):
    def test_brak_pojemnosci_lifecycle_nie_blokuje_kontraktu_rol(self):
        app = AppTest.from_file("app.py", default_timeout=30).run()
        for label, value in (("Obsługa skrzynki ugody EH", 0),
                ("Komunikacja z EH i zlecanie opłat w SOSS", 240),
                ("Umieszczanie dokumentów w SOSS", 240)):
            next(x for x in app.number_input if x.label == label).set_value(value)
        app.run()
        self.assertTrue(app.error)
        app.segmented_control[0].set_value("Kontrakt w czasie").run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertIn("Niewystarczająca pojemność według roli", [x.value for x in app.metric])


class TestJednaObsadaObuPaneli(unittest.TestCase):
    def app(self):
        return AppTest.from_file('app.py', default_timeout=30).run()

    @staticmethod
    def liczba(app, label):
        return next(x for x in app.number_input if x.label == label)

    @staticmethod
    def kwota(value):
        return float(value.replace(' zł', '').replace(' ', '').replace(',', '.'))

    def test_jedno_zrodlo_stawek_i_brak_ogolnego_wejscia(self):
        app = self.app()
        labels = [x.label for x in app.number_input]
        self.assertNotIn('Wynagrodzenie pracownika / h', labels)
        self.assertEqual([x for x in labels if x.startswith('Wynagrodzenie')],
                         ['Wynagrodzenie pracownika 1 (zł/h)', 'Wynagrodzenie pracownika 2 (zł/h)'])
        self.assertTrue(any('średnia arytmetyczna' in x.value for x in app.caption))

    def test_zmiana_plac_EH_i_ugod_aktualizuje_obydwa_panele(self):
        for indeks, godziny, kolumna in ((1, 433.2375 / 60 * 480 / 420, 'Koszt wynagrodzeń EH'),
                                         (2, 42.375 / 60 * 480 / 450, 'Koszt wynagrodzeń ugód')):
            app = self.app()
            self.liczba(app, f'Wynagrodzenie pracownika {indeks} (zł/h)').set_value(69.88).run()
            self.assertFalse(app.exception)
            koszt = self.kwota(next(x.value for x in app.metric if x.label == 'Koszt / sprawę'))
            self.assertAlmostEqual(koszt, round(863.4450571428571 + godziny * 10, 2))
            app.segmented_control[0].set_value('Kontrakt w czasie').run()
            self.assertFalse(app.exception)
            df = next(x.value for x in app.dataframe if kolumna in x.value.columns)
            self.assertAlmostEqual(df.iloc[0][kolumna], 167 * 69.88)
            app.segmented_control[0].set_value('Ekonomika sprawy').run()
            self.assertEqual(self.liczba(app, f'Wynagrodzenie pracownika {indeks} (zł/h)').value, 69.88)
            self.assertEqual(self.kwota(next(x.value for x in app.metric if x.label == 'Koszt / sprawę')), koszt)

    def test_brak_stawki_widoczny_i_kontrakt_dostepny(self):
        for liczba in (0, 1):
            app = self.app()
            self.liczba(app, 'Liczba pracowników').set_value(liczba).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Brak stawki godzinowej wymaganej roli' in x.value for x in app.error))
            self.assertFalse(any(x.label == 'Koszt / sprawę' for x in app.metric))
            app.segmented_control[0].set_value('Kontrakt w czasie').run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertIn('Niewystarczająca pojemność według roli', [x.value for x in app.metric])

        app = self.app()
        self.liczba(app, 'Liczba pracowników').set_value(0)
        self.liczba(app, 'Roczny napływ spraw').set_value(0).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(self.kwota(next(x.value for x in app.metric if x.label == 'Koszt / sprawę')), 0)

    def test_zmiana_2_3_2_3_zachowuje_stawki_i_role(self):
        app = self.app()
        self.liczba(app, 'Liczba pracowników').set_value(3).run()
        for i, placa in ((1, 50.0), (2, 45.0), (3, 70.0)):
            self.liczba(app, f'Wynagrodzenie pracownika {i} (zł/h)').set_value(placa)
        self.liczba(app, 'Wykorzystanie pracownika 3 w projekcie (%)').set_value(1.0).run()
        koszt3 = next(x.value for x in app.metric if x.label == 'Koszt / sprawę')
        self.liczba(app, 'Liczba pracowników').set_value(2).run()
        koszt2 = next(x.value for x in app.metric if x.label == 'Koszt / sprawę')
        self.assertLess(self.kwota(koszt2), self.kwota(koszt3))
        self.liczba(app, 'Liczba pracowników').set_value(3).run()
        self.assertEqual(self.liczba(app, 'Wynagrodzenie pracownika 3 (zł/h)').value, 70)
        self.assertEqual(self.liczba(app, 'Wykorzystanie pracownika 3 w projekcie (%)').value, 1)
        self.assertEqual(next(x.value for x in app.metric if x.label == 'Koszt / sprawę'), koszt3)
        app.segmented_control[0].set_value('Kontrakt w czasie').run()
        self.assertTrue(any(x.label == 'Rozliczenie kontraktu za 60 mies.' for x in app.expander))
        df = next(x.value for x in app.dataframe if 'Wielkość' in x.value.columns)
        self.assertIn('Łączne sprawomiesiące naliczające koszt', list(df['Wielkość']))


if __name__ == "__main__":
    unittest.main()
