import json
import re
import time
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import test_guests


class CalendarTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get
    token = test_guests.GuestTests.token
    post = test_guests.GuestTests.post
    login = test_guests.GuestTests.login

    def _details(self, name, address):
        with open(self.root / "details.json", "w", encoding="utf-8") as details:
            details.write(json.dumps({
                "ceremony": {"name": name, "address": address},
                "venue": {"name": "Prywatna sala weselna", "address": "Prywatny adres"},
                "contacts": [{"role": "Świadkowa", "name": "Prywatny świadek", "phone": "+48 555 000 111"}],
                "schedule": []}))

    def _ics_bytes(self, query=""):
        return self.get("/ceremony.ics" + query).get_data()

    def _ics(self, query=""):
        return self._ics_bytes(query).decode("utf-8")

    @staticmethod
    def _lines(data):
        # RFC 5545 unfolding: join CRLF followed by a continuation space or tab.
        return [line for line in re.sub(r"\r\n[ \t]", "", data).split("\r\n") if line]

    @staticmethod
    def _decode(value):
        # Decode the TEXT escaping applied by build_ics (\\, \; , \n and \N).
        out, i = [], 0
        while i < len(value):
            if value[i] == "\\" and i + 1 < len(value):
                nxt = value[i + 1]
                if nxt in ("\\", ";", ","):
                    out.append(nxt)
                elif nxt == "n":
                    out.append("\n")
                else:
                    out.append("\\" + nxt)
                i += 2
            else:
                out.append(value[i])
                i += 1
        return "".join(out)

    @staticmethod
    def _location(lines):
        # The LOCATION property, unfolded to one complete line and decoded to its value.
        line = next(line for line in lines if line.startswith("LOCATION:"))
        return CalendarTests._decode(line.partition(":")[2])

    def test_ics_response_content_type_and_filename(self):
        response = self.get("/ceremony.ics")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/calendar; charset=utf-8")
        self.assertEqual(response.headers["Content-Disposition"], 'attachment; filename="Weronika-and-Rafal-ceremonia.ics"')
        self.assertIn("noindex", response.headers.get("X-Robots-Tag", ""))
        self.assertIn("script-src 'self'", response.headers.get("Content-Security-Policy", ""))

    def test_ics_structure_constants_and_time(self):
        lines = self._lines(self._ics("?lang=pl"))
        for label in ("BEGIN:VCALENDAR", "END:VCALENDAR", "BEGIN:VEVENT", "END:VEVENT",
                      "VERSION:2.0", "UID:weronikarafal-ceremonia", "DTSTART:20270827T120000Z",
                      "SUMMARY:Weronika i Rafał ceremonia",
                      "LOCATION:Publiczny kościół\\, Publiczna ulica"):
            self.assertIn(label, lines)
        stamp = datetime.strptime(
            re.search(r"DTSTAMP:(\d{8}T\d{6}Z)", "\n".join(lines)).group(1),
            "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        # DTSTAMP is the current UTC time, not a placeholder value.
        self.assertLessEqual(abs((stamp - datetime.now(timezone.utc)).total_seconds()), 180)
        # DTSTART is 14:00 in Europe/Warsaw and stored as UTC.
        self.assertEqual(datetime(2027, 8, 27, 14, 0, tzinfo=ZoneInfo("Europe/Warsaw")),
                        datetime(2027, 8, 27, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(self._location(lines), "Publiczny kościół, Publiczna ulica")
        # Private venue, contacts, guest and RSVP data never reach the response text.
        for secret in ("Prywatna sala", "Prywatny adres", "+48 555", "Prywatny świadek", "Gość", "RSVP"):
            self.assertNotIn(secret, self._ics("?lang=pl"))

    def test_ics_in_english(self):
        lines = self._lines(self._ics("?lang=en"))
        self.assertIn("SUMMARY:Weronika and Rafał ceremony", lines)
        self.assertNotIn("SUMMARY:Weronika i Rafał ceremonia", lines)
        # The UID and start time are host- and language-stable.
        self.assertIn("UID:weronikarafal-ceremonia", lines)
        self.assertIn("DTSTART:20270827T120000Z", lines)

    def test_lines_are_crlf_and_folded_at_seventyfive_octets(self):
        data = self._ics("?lang=pl")
        self.assertTrue(data.endswith("\r\n"))
        for line in data[:-2].split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75, "line exceeds 75 UTF-8 octets")

    def test_missing_or_empty_ceremony_data_hides_location(self):
        self._details("", "")
        lines = self._lines(self._ics("?lang=pl"))
        self.assertIn("BEGIN:VEVENT", lines)
        self.assertIn("SUMMARY:Weronika i Rafał ceremonia", lines)
        self.assertFalse(any(line.startswith("LOCATION") for line in lines))

    def test_long_unicode_values_fold_and_decode_to_original(self):
        long_name = "Słowo, którego nazwa przekracza 75 bajtów; ; \\; ; " + "ó" * 120 + "😀" * 10
        address = "Adres, który przekracza 75 bajtów" + "ż" * 40
        self._details(long_name, address)
        raw = self._ics_bytes("?lang=pl")
        data = raw.decode("utf-8")  # the response body is valid UTF-8.
        self.assertTrue(data.endswith("\r\n"))
        for line in data[:-2].split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75, "line exceeds 75 UTF-8 octets")
        lines = self._lines(data)
        # Decoding the folded, escaped LOCATION value returns the original public text.
        self.assertEqual(self._location(lines), long_name + ", " + address)
        # The raw ICS body keeps the commas escaped as \\,.
        self.assertIn("\\,", data)

    def test_malicious_newlines_and_begin_events_never_inject_lines(self):
        evil_name = "BEGIN:VEVENT\nX-UNDEFINED:1\nEND:VEVENT\nceremonia\nNAME"
        self._details(evil_name, "ul. x\nul. y")
        data = self._ics("?lang=pl")
        lines = self._lines(data)
        # Counts cover full properties; the malicious text stays in one escaped value.
        self.assertEqual(lines.count("BEGIN:VEVENT"), 1)
        self.assertEqual(lines.count("END:VEVENT"), 1)
        self.assertNotIn("X-UNDEFINED:1", lines)
        self.assertNotIn("NAME", lines)
        # Newlines are preserved escaped inside LOCATION, so no extra ICS line exists.
        self.assertEqual(self._location(lines), evil_name + ", " + "ul. x\nul. y")
        # The literal backslash-n escape is present in the raw property line.
        location = next(line for line in lines if line.startswith("LOCATION:"))
        self.assertIn("ul. x\\nul. y", location)
        for line in data[:-2].split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75)

    def test_roundtrip_crlf_cr_and_control_characters_removed(self):
        self._details("nazwa\r\nCR\ttab\nnewline", "adres\x00\x01\x02\x7f")
        data = self._ics("?lang=pl")
        body = data[:-2].replace("\r\n", "")
        # Every newline ends as a CRLF line ending, and no other raw control character
        # remains; tab is the only allowed C0 character.
        self.assertNotIn("\n", body)
        self.assertNotIn("\r", body)
        for char in body:
            self.assertFalse(ord(char) < 32 and char != "\t")
            self.assertFalse(char == "\x7f")
        # CRLF and CR normalize to a single LF, which is escaped and round-trips.
        self.assertEqual(self._location(self._lines(data)), "nazwa\nCR\ttab\nnewline, adres")

    def test_missing_details_file_uses_defaults(self):
        (self.root / "details.json").unlink()
        lines = self._lines(self._ics("?lang=pl"))
        self.assertIn("UID:weronikarafal-ceremonia", lines)
        self.assertEqual(self._location(lines),
                        "Bazylika św. Ludwika Króla i Wniebowzięcia Najświętszej Maryi Panny, "
                        "ul. Panewnicka 76, 40-760 Katowice (Panewniki)")

    def test_uid_is_stable_across_trusted_hosts(self):
        self.app.config["TRUSTED_HOSTS"] = ["localhost", "alternate.test"]
        base = self._ics("?lang=pl")
        response = self.app.test_client().get("/ceremony.ics", base_url="https://alternate.test")
        self.assertEqual(response.status_code, 200)
        alternate = self._lines(response.get_data(as_text=True))
        uid = next(line for line in self._lines(base) if line.startswith("UID:"))
        self.assertEqual(next(line for line in alternate if line.startswith("UID:")), uid)

    def test_privacy_stable_even_when_authenticated(self):
        self.login()
        data = self._ics("?lang=pl")
        self.assertEqual(self._location(self._lines(data)), "Publiczny kościół, Publiczna ulica")
        for secret in ("Prywatna sala", "Prywatny adres", "+48 555", "Prywatny świadek", "Gość", "RSVP"):
            self.assertNotIn(secret, data)
        self.assertFalse(any(line.startswith("DTEND") or line.startswith("DURATION") for line in self._lines(data)))

    def test_calendar_button_present_in_both_languages(self):
        page = self.get("/?lang=pl")
        self.assertIn('href="/ceremony.ics"', page.text)
        self.assertIn("download", page.text)
        self.assertIn("Dodaj do kalendarza", page.text)
        page_en = self.get("/?lang=en")
        self.assertIn("Add to calendar", page_en.text)
        self.assertNotIn("Dodaj do kalendarza", page_en.text)

    def test_calendar_button_present_without_ceremony_data(self):
        self._details("", "")
        page = self.get("/?lang=pl")
        self.assertIn('href="/ceremony.ics"', page.text)
        self.assertIn("download", page.text)
        self.assertIn("Dodaj do kalendarza", page.text)
        page_en = self.get("/?lang=en")
        self.assertIn("Add to calendar", page_en.text)


if __name__ == "__main__":
    unittest.main()
