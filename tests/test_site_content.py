import unittest
import test_guests


class SiteContentTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get
    token = test_guests.GuestTests.token
    post = test_guests.GuestTests.post
    login = test_guests.GuestTests.login
    response = test_guests.GuestTests.response

    def test_guest_steps_and_faq_render_on_public_page(self):
        response = self.get('/')
        self.assertEqual(response.status_code, 200)
        for fragment in ('id="pytania"', 'id="guest-steps-title"', 'id="faq-title"'):
            self.assertEqual(response.text.count(fragment), 1)
        self.assertEqual(response.text.count('<details>'), 5)
        self.assertEqual(response.text.count('<summary>'), 5)
        self.assertIn('href="#pytania"', response.text)
        for label in ('Trzy kroki do naszego dnia', 'Pytania i odpowiedzi',
                    'Jak wpisać kod z zaproszenia?', 'Do kiedy potwierdzić obecność?',
                    'Gdzie podać dietę i nocleg?', 'Gdzie znajdę szczegóły przyjęcia?',
                    'Kto może widzieć zdjęcia i filmy?', 'Potwierdź obecność do 1 lipca 2027 r.',
                    'Wróć po szczegóły i wspomnienia'):
            self.assertIn(label, response.text)
        for private in ('Gość Alfa', 'Gość Beta', 'Prywatna sala', '+48 555',
                      'Prywatny świadek', 'Prywatny adres'):
            self.assertNotIn(private, response.text)

    def test_guest_steps_and_faq_are_translated_to_english(self):
        page = self.get('/?lang=en')
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers['Content-Language'], 'en')
        for fragment in ('id="pytania"', 'id="guest-steps-title"', 'id="faq-title"'):
            self.assertEqual(page.text.count(fragment), 1)
        self.assertEqual(page.text.count('<details>'), 5)
        self.assertEqual(page.text.count('<summary>'), 5)
        for label in ('Three steps to our day', 'Questions and answers',
                    'How do I enter the invitation code?', 'When is the RSVP deadline?',
                    'Where do I enter diet and lodging?', 'Where can I find reception details?',
                    'Who can see the photos and videos?',
                    'Confirm attendance by 1 July 2027.', 'Come back for details and memories'):
            self.assertIn(label, page.text)

    def test_guest_area_links_to_media_in_both_languages(self):
        self.login()
        page = self.get()
        self.assertIn('<section id="wspomnienia"', page.text)
        self.assertIn('href="/media"', page.text)
        self.assertIn('href="#wspomnienia"', page.text)
        self.assertIn('Otwórz bibliotekę', page.text)
        self.assertIn('Biblioteka mediów', page.text)
        page_en = self.get('/guest?lang=en')
        self.assertEqual(page_en.status_code, 200)
        self.assertIn('href="/media"', page_en.text)
        self.assertIn('Open the library', page_en.text)
        self.assertIn('Media library', page_en.text)
        self.assertIn('Memories', page_en.text)

    def test_anonymous_guest_and_media_pages_stay_protected(self):
        client = self.app.test_client()
        self.assertEqual(client.get('/guest', base_url="https://localhost").status_code, 303)
        self.assertEqual(client.get('/media', base_url="https://localhost").status_code, 303)


if __name__ == "__main__":
    unittest.main()
