import unittest
from html.parser import HTMLParser
import test_guests


class HomeDesignTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get
    token = test_guests.GuestTests.token
    post = test_guests.GuestTests.post
    login = test_guests.GuestTests.login
    response = test_guests.GuestTests.response

    class ElementParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.elements = []
            self.heading = []
            self.in_heading = False

        def handle_starttag(self, tag, attrs):
            self.elements.append({'tag': tag, 'attrs': dict(attrs)})
            if tag == 'h1':
                self.in_heading = True

        def handle_data(self, data):
            if self.in_heading:
                self.heading.append(data)

        def handle_endtag(self, tag):
            if tag == 'h1':
                self.in_heading = False

    def get_elements(self, html):
        parser = self.ElementParser()
        parser.feed(html)
        self.assertIn('Weronika', ''.join(parser.heading))
        self.assertIn('Rafał', ''.join(parser.heading))
        return parser.elements

    def test_home_page_pl(self):
        response = self.get('/')
        self.assertEqual(response.status_code, 200)
        elements = self.get_elements(response.text)

        # h1 id hero-title
        h1s = [e for e in elements if e['tag'] == 'h1' and e['attrs'].get('id') == 'hero-title']
        self.assertEqual(len(h1s), 1, "Expected exactly one h1 with id 'hero-title'")

        # .date-poster and <time datetime="2027-08-27">
        has_date_poster = any(e['attrs'].get('class') and 'date-poster' in e['attrs'].get('class') for e in elements)
        self.assertTrue(has_date_poster, "date-poster class missing")

        time_elements = [e for e in elements if e['tag'] == 'time' and e['attrs'].get('datetime') == '2027-08-27']
        self.assertEqual(len(time_elements), 1, "Expected exactly one time element")

        # odliczanie data-countdown="2027-08-27T14:00:00+02:00" and 4 data-unit
        countdown_elements = [e for e in elements if e['attrs'].get('data-countdown') == '2027-08-27T14:00:00+02:00']
        self.assertEqual(len(countdown_elements), 1, "Expected exactly one countdown element")

        units = [e['attrs'].get('data-unit') for e in elements if 'data-unit' in e['attrs']]
        self.assertCountEqual(units, ['days', 'hours', 'minutes', 'seconds'])

        # hero zawiera link href="#ceremonia" i href="#pytania"
        has_ceremonia = any(e['attrs'].get('href') == '#ceremonia' for e in elements)
        has_pytania = any(e['attrs'].get('href') == '#pytania' for e in elements)
        self.assertTrue(has_ceremonia, "Link to ceremonia missing")
        self.assertTrue(has_pytania, "Link to pytania missing")

        # Nowe logo SVG inline class wedding-mark z data-logo="wr" (2 wystąpienia)
        logo_elements = [
            e for e in elements
            if e['tag'] == 'svg'
            and 'wedding-mark' in e['attrs'].get('class', '').split()
            and e['attrs'].get('data-logo') == 'wr'
        ]
        self.assertEqual(len(logo_elements), 2, f"Expected 2 logo elements, found {len(logo_elements)}")

        # NIE ma starych obrączek (rect rx=14) ani tekstowego W&R
        self.assertFalse(any(e['tag'] == 'rect' and e['attrs'].get('rx') == '14' for e in elements), "Found old rect rx=14")
        self.assertNotIn('W&R', response.text)

        # 4 FAQ details
        details_elements = [e for e in elements if e['tag'] == 'details']
        self.assertEqual(len(details_elements), 4, "Expected 4 FAQ details")

        # brak tekstu o noclegu i prywatnych danych
        self.assertNotIn('Gdzie podać dietę i nocleg?', response.text)
        self.assertNotIn('Preferencje żywieniowe i zapotrzebowanie na nocleg', response.text)

        # brak prywatnych danych
        private_data = ['Gość Alfa', 'Gość Beta', 'Prywatna sala', 'Prywatny świadek', '+48 555', 'Prywatny adres']
        for item in private_data:
            self.assertNotIn(item, response.text)

    def test_home_page_en(self):
        response = self.get('/?lang=en')
        self.assertEqual(response.status_code, 200)
        elements = self.get_elements(response.text)

        # Structural checks
        h1s = [e for e in elements if e['tag'] == 'h1' and e['attrs'].get('id') == 'hero-title']
        self.assertEqual(len(h1s), 1, "Expected exactly one h1 with id 'hero-title'")

        has_date_poster = any(e['attrs'].get('class') and 'date-poster' in e['attrs'].get('class') for e in elements)
        self.assertTrue(has_date_poster, "date-poster class missing")

        time_elements = [e for e in elements if e['tag'] == 'time' and e['attrs'].get('datetime') == '2027-08-27']
        self.assertEqual(len(time_elements), 1, "Expected exactly one time element")

        countdown_elements = [e for e in elements if e['attrs'].get('data-countdown') == '2027-08-27T14:00:00+02:00']
        self.assertEqual(len(countdown_elements), 1, "Expected exactly one countdown element")

        units = [e['attrs'].get('data-unit') for e in elements if 'data-unit' in e['attrs']]
        self.assertCountEqual(units, ['days', 'hours', 'minutes', 'seconds'])

        has_ceremonia = any(e['attrs'].get('href') == '#ceremonia' for e in elements)
        has_pytania = any(e['attrs'].get('href') == '#pytania' for e in elements)
        self.assertTrue(has_ceremonia, "Link to ceremonia missing")
        self.assertTrue(has_pytania, "Link to pytania missing")

        logo_elements = [
            e for e in elements
            if e['tag'] == 'svg'
            and 'wedding-mark' in e['attrs'].get('class', '').split()
            and e['attrs'].get('data-logo') == 'wr'
        ]
        self.assertEqual(len(logo_elements), 2, f"Expected 2 logo elements, found {len(logo_elements)}")

        self.assertFalse(any(e['tag'] == 'rect' and e['attrs'].get('rx') == '14' for e in elements), "Found old rect rx=14")
        self.assertNotIn('W&R', response.text)

        details_elements = [e for e in elements if e['tag'] == 'details']
        self.assertEqual(len(details_elements), 4, "Expected 4 FAQ details")

        self.assertNotIn('Where do I enter diet and lodging?', response.text)
        self.assertNotIn('Dietary preferences and lodging needs', response.text)

        # Privacy checks
        private_data = ['Gość Alfa', 'Gość Beta', 'Prywatna sala', 'Prywatny świadek', '+48 555', 'Prywatny adres']
        for item in private_data:
            self.assertNotIn(item, response.text)

if __name__ == "__main__":
    unittest.main()
