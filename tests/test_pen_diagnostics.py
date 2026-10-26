import unittest

from beamerplus.PenDiagnostics import sanitize


class PenDiagnosticsTests(unittest.TestCase):
    def event(self, **extras):
        return dict(event='pointermove', pointer='pen', button=2, buttons=2, pressure=0, **extras)

    def test_accepts_flags_and_discards_content_and_coordinates(self):
        clean = sanitize({'browser': 'Chrome', 'events': [self.event(x=123, y=456, text='private')], 'apiKey': 'private'})
        self.assertEqual(clean, {'browser': 'Chrome', 'events': [self.event()]})

    def test_rejects_unknown_and_unbounded_data(self):
        for events in [[], [self.event()] * 41, [{'event': 'keydown'}],
                       [{**self.event(), 'pressure': float('nan')}],
                       [{**self.event(), 'buttons': '2'}]]:
            with self.assertRaises(ValueError):
                sanitize({'browser': 'Chrome', 'events': events})


if __name__ == '__main__':
    unittest.main()
