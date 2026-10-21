import json
import unittest
import test_admin
from wedding.store import connect


class HouseholdTests(unittest.TestCase):
    setUp = test_admin.AdminTests.setUp
    get = test_admin.AdminTests.get
    post = test_admin.AdminTests.post
    token = test_admin.AdminTests.token
    login = test_admin.AdminTests.login
    admin_login = test_admin.AdminTests.admin_login
    action = test_admin.AdminTests.action
    code = test_admin.AdminTests.code

    def add(self, **changes):
        data = {'csrf_token': self.token('/admin'), 'name': 'Pierwsza Osoba', 'kind': 'single', 'children_count': '0'}
        data.update(changes)
        return self.post('/admin/guests', data)

    def person(self, name='Pierwsza Osoba'):
        with connect(self.app.config['DATABASE']) as db:
            return db.execute('SELECT * FROM guests WHERE name=?', (name,)).fetchone()

    def test_named_couple_and_children_share_one_code(self):
        self.admin_login()
        code = self.code(self.add(kind='couple', partner_name='Druga Osoba', children_count='2', children=['Prywatne Dziecko', '']))
        person = self.person()
        self.assertEqual(person['partner_name'], 'Druga Osoba')
        self.assertEqual(person['allows_companion'], 0)
        self.assertEqual(json.loads(person['children']), ['Prywatne Dziecko', ''])
        guest = self.app.test_client()
        self.login(code, guest)
        page = self.get(client=guest)
        for name in ('Pierwsza Osoba', 'Druga Osoba', 'Prywatne Dziecko', 'Dziecko 2'):
            self.assertIn(name, page.text)
        self.assertNotIn('name="companion_name"', page.text)
        self.assertEqual(self.post('/rsvp', {'csrf_token': self.token('/guest', guest), 'attendance':'yes', 'diet':'standard', 'lodging':'no'}, guest).status_code, 303)

    def test_plus_one_needs_no_name_and_discards_stale_partner_field(self):
        self.admin_login()
        self.code(self.add(kind='plusone', partner_name='Nie zapisuj tej osoby', children_count='1'))
        person = self.person()
        self.assertEqual(person['partner_name'], '')
        self.assertEqual(person['allows_companion'], 1)
        self.assertEqual(json.loads(person['children']), [''])
        self.assertNotIn('Nie zapisuj tej osoby', self.get('/admin').text)

    def test_child_count_works_without_javascript_or_child_names(self):
        self.admin_login()
        self.code(self.add(children_count='3'))
        self.assertEqual(json.loads(self.person()['children']), ['', '', ''])

    def test_invalid_households_are_rejected_before_creation(self):
        self.admin_login()
        for data in [{'kind':'couple'}, {'kind':'invalid'}, {'children_count':'-1'},
                     {'children_count':'21'}, {'children_count':'1.5'},
                     {'children_count':'1', 'children':['One', 'Two']},
                     {'children_count':'1', 'children':['x'*121]}]:
            response = self.add(**data)
            self.assertEqual(response.status_code, 303)
            self.assertIsNone(self.person())

    def test_edit_and_code_reset_preserve_household_and_response(self):
        self.admin_login()
        self.assertEqual(self.action('edit', name='Rodzina Testowa', kind='couple', partner_name='Drugi Rodzic', children_count='2', children=['Dziecko Alfa','']).status_code, 303)
        self.code(self.action('rotate'))
        person = self.person('Rodzina Testowa')
        self.assertEqual(person['partner_name'], 'Drugi Rodzic')
        self.assertEqual(json.loads(person['children']), ['Dziecko Alfa', ''])
        self.action('edit', name='Rodzina Testowa', kind='plusone', children_count='1', children=[''])
        person = self.person('Rodzina Testowa')
        self.assertEqual(person['partner_name'], '')
        self.assertEqual(person['allows_companion'], 1)
        self.assertEqual(json.loads(person['children']), [''])

    def test_children_are_not_exposed_to_other_guests_or_public(self):
        self.admin_login()
        self.code(self.add(kind='couple', partner_name='Druga Osoba', children_count='1', children=['Prywatne Dziecko']))
        other = self.app.test_client()
        self.login(self.bob_code, other)
        page = self.get(client=other)
        self.assertIn('Druga Osoba', page.text)
        self.assertNotIn('Prywatne Dziecko', page.text)
        self.assertNotIn('Prywatne Dziecko', self.get('/').text)

    def test_household_fields_are_translated_and_guest_cannot_edit_members(self):
        self.get('/?lang=en')
        self.admin_login()
        page = self.get('/admin')
        for label in ('Couple — enter both names', 'Children on the invitation', '+ Add a child'):
            self.assertIn(label, page.text)
        guest = self.app.test_client()
        self.login(self.alice_code, guest)
        self.assertEqual(self.post('/rsvp', {'csrf_token': self.token('/guest', guest), 'children_count': '10'}, guest).status_code, 400)
