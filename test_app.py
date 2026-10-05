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

        app.segmented_control[0].set_value("Kontrakt w czasie").run()
        self.assertFalse(app.exception)
        self.assertIn("Kontrakt w czasie", [header.value for header in app.header])
        self.assertTrue(
            {
                "Status kontraktu",
                "Break-even finansowy",
                "Największy deficyt",
                "Obsada",
                "Backlog",
            }.issubset({metric.label for metric in app.metric})
        )


if __name__ == "__main__":
    unittest.main()
