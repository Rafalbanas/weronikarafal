from pathlib import Path
import re
import subprocess
import unittest

import test_guests
import test_home_design


class EditorialTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get

    def test_bilingual_cats_dates_and_progressive_enhancement(self):
        for language, cat_copy in (('pl', 'Pod kocim nadzorem.'),
                                   ('en', 'Under feline supervision.')):
            html = self.get('/?lang=' + language).text
            parser = test_home_design.HomeDesignTests.ElementParser()
            parser.feed(html)
            elements = parser.elements
            self.assertIn('27 · 08 · 27', html)
            self.assertIn(cat_copy.lower(), html.lower())
            self.assertIn('Jeden ulubiony parapet.' if language == 'pl'
                          else 'One favourite sunny spot.', html)
            for secret in ('star-secret', 'heart-secret'):
                target = next(e for e in elements if e['attrs'].get('id') == secret)
                self.assertIn('hidden', target['attrs'])
                button = next(e for e in elements if e['attrs'].get('data-surprise') == secret)
                self.assertEqual(button['tag'], 'button')
                self.assertEqual(button['attrs']['type'], 'button')
                self.assertEqual(button['attrs']['aria-expanded'], 'false')
                self.assertEqual(button['attrs']['aria-controls'], secret)
                self.assertIn('hidden', button['attrs'])
                self.assertTrue(button['attrs']['aria-label'])
            cats = [e for e in elements if e['tag'] == 'svg' and
                    e['attrs'].get('class') in ('peeking-cat', 'cat-couple')]
            self.assertEqual(len(cats), 2)
            self.assertTrue(all(e['attrs']['aria-hidden'] == 'true' for e in cats))
            timer = next(e for e in elements if 'data-countdown' in e['attrs'])
            self.assertEqual(timer['attrs']['data-countdown'], '2027-08-27T14:00:00+02:00')
            self.assertEqual(timer['attrs']['role'], 'timer')
            self.assertEqual(timer['attrs']['aria-live'], 'off')
            sections = [e for e in elements if 'data-reveal' in e['attrs']]
            self.assertEqual(len(sections), 3)
            self.assertTrue(all('hidden' not in e['attrs'] for e in sections))

    def test_countdown_and_reveal_javascript(self):
        subprocess.run(['node', str(Path(__file__).with_name('editorial.cjs'))],
                       check=True, timeout=30)

    def test_critical_hero_animation_does_not_start_transparent(self):
        css = (Path(__file__).resolve().parents[1] / 'assets/site.css').read_text()
        keyframes = re.search(r'@keyframes invitation-arrive\{(.*?)\}\}', css, re.S)
        self.assertIsNotNone(keyframes)
        self.assertNotRegex(keyframes.group(1), r'opacity\s*:\s*0(?:[;}]|$)')
