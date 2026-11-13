import unittest
from html.parser import HTMLParser
import test_guests

class PublicSEOTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get
    token = test_guests.GuestTests.token
    response = test_guests.GuestTests.response

    class UniversalParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.elements = []

        def handle_starttag(self, tag, attrs):
            self.elements.append({'tag': tag, 'attrs': dict(attrs)})

    def get_elements(self, html):
        parser = self.UniversalParser()
        parser.feed(html)
        return parser.elements

    def test_public_seo_pl(self):
        response = self.get("/")
        self.assertEqual(response.status_code, 200)
        elements = self.get_elements(response.text)

        # Canonical
        canonical = next((e['attrs'].get('href') for e in elements if e['tag'] == 'link' and e['attrs'].get('rel') == 'canonical'), None)
        self.assertEqual(canonical, "https://weronikarafal.com/?lang=pl")

        # Hreflang
        hreflangs = [e for e in elements if e['tag'] == 'link' and e['attrs'].get('rel') == 'alternate']
        pl_found = any(e['attrs'].get('hreflang') == 'pl' and e['attrs'].get('href') == "https://weronikarafal.com/?lang=pl" for e in hreflangs)
        en_found = any(e['attrs'].get('hreflang') == 'en' and e['attrs'].get('href') == "https://weronikarafal.com/?lang=en" for e in hreflangs)
        default_found = any(e['attrs'].get('hreflang') == 'x-default' and e['attrs'].get('href') == "https://weronikarafal.com/?lang=pl" for e in hreflangs)

        self.assertTrue(pl_found, "Hreflang pl missing")
        self.assertTrue(en_found, "Hreflang en missing")
        self.assertTrue(default_found, "Hreflang x-default missing")

        # OpenGraph
        meta = [e['attrs'] for e in elements if e['tag'] == 'meta']
        og_type = next((m.get('content') for m in meta if m.get('property') == 'og:type'), None)
        og_title = next((m.get('content') for m in meta if m.get('property') == 'og:title'), None)
        og_desc = next((m.get('content') for m in meta if m.get('property') == 'og:description'), None)
        og_url = next((m.get('content') for m in meta if m.get('property') == 'og:url'), None)
        og_locale = next((m.get('content') for m in meta if m.get('property') == 'og:locale'), None)

        self.assertEqual(og_type, "website")
        self.assertIn('2027', og_title)
        self.assertIn('2027', og_desc)
        self.assertEqual(og_url, "https://weronikarafal.com/?lang=pl")
        self.assertEqual(og_locale, "pl_PL")

        # Twitter
        twitter_card = next((m.get('content') for m in meta if m.get('name') == 'twitter:card'), None)
        self.assertEqual(twitter_card, "summary")

    def test_public_seo_en(self):
        response = self.get("/?lang=en")
        self.assertEqual(response.status_code, 200)
        elements = self.get_elements(response.text)

        # Canonical
        canonical = next((e['attrs'].get('href') for e in elements if e['tag'] == 'link' and e['attrs'].get('rel') == 'canonical'), None)
        self.assertEqual(canonical, "https://weronikarafal.com/?lang=en")

        # Hreflang
        hreflangs = [e for e in elements if e['tag'] == 'link' and e['attrs'].get('rel') == 'alternate']
        pl_found = any(e['attrs'].get('hreflang') == 'pl' and e['attrs'].get('href') == "https://weronikarafal.com/?lang=pl" for e in hreflangs)
        en_found = any(e['attrs'].get('hreflang') == 'en' and e['attrs'].get('href') == "https://weronikarafal.com/?lang=en" for e in hreflangs)
        default_found = any(e['attrs'].get('hreflang') == 'x-default' and e['attrs'].get('href') == "https://weronikarafal.com/?lang=pl" for e in hreflangs)

        self.assertTrue(pl_found, "Hreflang pl missing")
        self.assertTrue(en_found, "Hreflang en missing")
        self.assertTrue(default_found, "Hreflang x-default missing")

        # OpenGraph
        meta = [e['attrs'] for e in elements if e['tag'] == 'meta']
        og_type = next((m.get('content') for m in meta if m.get('property') == 'og:type'), None)
        og_title = next((m.get('content') for m in meta if m.get('property') == 'og:title'), None)
        og_desc = next((m.get('content') for m in meta if m.get('property') == 'og:description'), None)
        og_url = next((m.get('content') for m in meta if m.get('property') == 'og:url'), None)
        og_locale = next((m.get('content') for m in meta if m.get('property') == 'og:locale'), None)

        self.assertEqual(og_type, "website")
        self.assertIn('2027', og_title)
        self.assertIn('2027', og_desc)
        self.assertEqual(og_url, "https://weronikarafal.com/?lang=en")
        self.assertEqual(og_locale, "en_GB")

        # Twitter
        twitter_card = next((m.get('content') for m in meta if m.get('name') == 'twitter:card'), None)
        self.assertEqual(twitter_card, "summary")

    def test_cookie_language(self):
        # first GET /?lang=en
        self.get("/?lang=en")
        # then GET /
        response = self.get("/")
        self.assertEqual(response.status_code, 200)
        elements = self.get_elements(response.text)

        # canonical and og:locale must still be en
        canonical = next((e['attrs'].get('href') for e in elements if e['tag'] == 'link' and e['attrs'].get('rel') == 'canonical'), None)
        self.assertEqual(canonical, "https://weronikarafal.com/?lang=en")

        meta = [e['attrs'] for e in elements if e['tag'] == 'meta']
        og_locale = next((m.get('content') for m in meta if m.get('property') == 'og:locale'), None)
        self.assertEqual(og_locale, "en_GB")

    def test_description_different(self):
        # PL description
        res_pl = self.get("/")
        elements_pl = self.get_elements(res_pl.text)
        meta_pl = [e['attrs'] for e in elements_pl if e['tag'] == 'meta']
        desc_pl = next((m.get('content') for m in meta_pl if m.get('property') == 'og:description'), None)

        # EN description
        res_en = self.get("/?lang=en")
        elements_en = self.get_elements(res_en.text)
        meta_en = [e['attrs'] for e in elements_en if e['tag'] == 'meta']
        desc_en = next((m.get('content') for m in meta_en if m.get('property') == 'og:description'), None)

        self.assertNotEqual(desc_pl, desc_en)

    def test_canonical_no_localhost_or_extra_params(self):
        # Test that canonical doesn't use localhost or arbitrary params even if present in URL
        response = self.get("/?lang=en&next=secret")
        self.assertEqual(response.status_code, 200)
        elements = self.get_elements(response.text)
        canonical = next((e['attrs'].get('href') for e in elements if e['tag'] == 'link' and e['attrs'].get('rel') == 'canonical'), None)
        self.assertEqual(canonical, "https://weronikarafal.com/?lang=en")
        self.assertNotIn("localhost", canonical)
        self.assertNotIn("next=secret", canonical)

    def test_private_views_no_seo(self):
        # /login
        response = self.get("/login")
        self.assertIn("noindex", response.headers.get("X-Robots-Tag", ""))
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))

        elements = self.get_elements(response.text)
        canonical = next((e['attrs'].get('href') for e in elements if e['tag'] == 'link' and e['attrs'].get('rel') == 'canonical'), None)
        hreflangs = [e for e in elements if e['tag'] == 'link' and e['attrs'].get('rel') == 'alternate']
        meta = [e['attrs'] for e in elements if e['tag'] == 'meta']

        self.assertIsNone(canonical, "Canonical should not be present on /login")
        self.assertEqual(len(hreflangs), 0, "Hreflang should not be present on /login")

        og_tags = [m for m in meta if m.get('property', '').startswith('og:')]
        self.assertEqual(len(og_tags), 0, "OG tags should not be present on /login")

        # /admin/login
        response = self.get("/admin/login")
        self.assertIn("noindex", response.headers.get("X-Robots-Tag", ""))
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))
        elements = self.get_elements(response.text)
        canonical = next((e['attrs'].get('href') for e in elements if e['tag'] == 'link' and e['attrs'].get('rel') == 'canonical'), None)
        hreflangs = [e for e in elements if e['tag'] == 'link' and e['attrs'].get('rel') == 'alternate']
        meta = [e['attrs'] for e in elements if e['tag'] == 'meta']

        self.assertIsNone(canonical, "Canonical should not be present on /admin/login")
        self.assertEqual(len(hreflangs), 0, "Hreflang should not be present on /admin/login")
        og_tags = [m for m in meta if m.get('property', '').startswith('og:')]
        self.assertEqual(len(og_tags), 0, "OG tags should not be present on /admin/login")

    def test_no_private_data_in_metadata(self):
        # Check that no private data appears in metadata
        response = self.get("/")
        elements = self.get_elements(response.text)
        meta = [e['attrs'] for e in elements if e['tag'] == 'meta']

        private_data = ["Gość Alfa", "Gość Beta", "Prywatna sala", "+48 555", "Prywatny świadek", "Prywatny adres"]
        for m in meta:
            content = m.get('content', '')
            for item in private_data:
                self.assertNotIn(item, content)

if __name__ == "__main__":
    unittest.main()
