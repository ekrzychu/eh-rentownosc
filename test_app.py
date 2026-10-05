import unittest

from streamlit.testing.v1 import AppTest


class TestGlowneWidoki(unittest.TestCase):
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

    def test_niedostepny_wynik_malej_obsady_i_dojrzaly_wynik_wystarczajacej(self):
        app = AppTest.from_file("app.py", default_timeout=30).run()
        app.segmented_control[0].set_value("Kontrakt w czasie").run()
        self.assertFalse(app.exception)
        skladniki = next(x.value for x in app.caption if "Składniki statusu" in x.value)
        self.assertIn("wynik bieżącej obsady: niedostępny", skladniki)
        self.assertFalse(any("Dojrzały wynik miesięczny bieżącej obsady" in x.value for x in app.markdown))
        metryki = {x.label: x.value for x in app.metric}
        self.assertEqual(metryki["Minimalna stabilna obsada"], "3 os.")
        self.assertEqual(metryki["Status kontraktu"], "Nierentowna ekonomika sprawy")
        next(x for x in app.number_input if x.label == "Liczba pracowników").set_value(3).run()
        self.assertFalse(app.exception)
        skladniki = next(x.value for x in app.caption if "Składniki statusu" in x.value)
        self.assertNotIn("niedostępny", skladniki)
        self.assertTrue(any("Dojrzały wynik miesięczny bieżącej obsady" in x.value for x in app.markdown))


if __name__ == "__main__":
    unittest.main()
