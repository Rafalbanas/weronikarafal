import re
import unittest
import test_guests
import test_home_design


class GuestUXTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get
    post = test_guests.GuestTests.post
    token = test_guests.GuestTests.token
    login = test_guests.GuestTests.login

    def primary(self, html):
        return re.search(r'<div class="hero-actions">\s*<a class="button" href="([^"]+)">([^<]+)', html).groups()

    def test_public_primary_action_and_summary_are_bilingual(self):
        for lang, label, deadline in (('pl', 'Potwierdź obecność', '1 lipca 2027'), ('en', 'RSVP', '1 July 2027')):
            html = self.get('/?lang=' + lang).text
            href, text = self.primary(html)
            self.assertEqual(href, '/login')
            self.assertEqual(text.strip(), label)
            self.assertIn('class="day-at-a-glance"', html)
            self.assertIn('<time datetime="2027-07-01">' + deadline + '</time>', html)
            self.assertIn('href="#ceremonia"', html)
            self.assertIn('href="#pytania"', html)
            self.assertNotIn('Prywatna sala', html)

    def test_authenticated_primary_action_goes_directly_to_rsvp(self):
        self.login()
        self.assertEqual(self.primary(self.get('/').text)[0], '/guest#rsvp')

    def test_date_has_full_accessible_text_without_prohibited_aria_name(self):
        for lang, full_date in (('pl', '27 sierpnia 2027'), ('en', '27 August 2027')):
            html = self.get('/?lang=' + lang).text
            date = re.search(r'<time class="poster-date"([^>]*)>(.*?)</time>', html, re.S)
            self.assertIsNotNone(date)
            self.assertNotIn('aria-label', date.group(1))
            self.assertIn('<span class="sr-only">' + full_date + '</span>', date.group(2))
            parser = test_home_design.HomeDesignTests.ElementParser()
            parser.feed(date.group(2))
            visual = [e for e in parser.elements
                      if e['tag'] == 'span' and e['attrs'].get('class') != 'sr-only']
            self.assertEqual(len(visual), 5)
            self.assertTrue(all(e['attrs'].get('aria-hidden') == 'true' for e in visual))

    def test_code_visibility_control_is_optional_and_bilingual(self):
        for lang, show, hide in (('pl', 'Pokaż kod', 'Ukryj kod'), ('en', 'Show code', 'Hide code')):
            parser = test_home_design.HomeDesignTests.ElementParser()
            parser.feed(self.get('/login?lang=' + lang).text)
            controls = [e for e in parser.elements if e['attrs'].get('data-password-toggle') == 'code']
            self.assertEqual(len(controls), 1)
            attrs = controls[0]['attrs']
            self.assertEqual(controls[0]['tag'], 'button')
            self.assertEqual(attrs['type'], 'button')
            self.assertEqual(attrs['aria-controls'], 'code')
            self.assertEqual(attrs['aria-pressed'], 'false')
            self.assertEqual(attrs['data-show'], show)
            self.assertEqual(attrs['data-hide'], hide)
            self.assertIn('hidden', attrs)
