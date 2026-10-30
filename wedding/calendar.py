"""Public ICS calendar entry. Contains only public ceremony data from details()."""
import time

UID = "weronikarafal-ceremonia"
DTSTART = "20270827T120000Z"  # 2027-08-27 14:00 Europe/Warsaw, stored in UTC
DOWNLOAD_NAME = "Weronika-and-Rafal-ceremonia.ics"  # ASCII-safe, constant across language and host
SUMMARY_BY_LANGUAGE = {"pl": "Weronika i Rafał ceremonia", "en": "Weronika and Rafał ceremony"}


def _escape(value):
    """Escape an ICS TEXT value for RFC 5545. CRLF and CR are normalized to LF, LF is escaped
    as \\n, every other C0 control character and DEL are removed, and tab is preserved."""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    escaped = []
    for char in value:
        if char in ("\\", ";", ","):
            escaped.append("\\" + char)
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\t":
            escaped.append("\t")
        elif ord(char) < 32 or char == "\x7f":
            continue
        else:
            escaped.append(char)
    return "".join(escaped)


def _fold(line):
    """Break one ICS content line into chunks of at most 75 UTF-8 octets, never splitting a codepoint."""
    lines, current, used = [], "", 0
    for char in line:
        size = len(char.encode("utf-8"))
        if used + size > 75:
            lines.append(current)
            current, used = " " + char, size + 1
        else:
            current += char
            used += size
    if current:
        lines.append(current)
    return lines


def build_ics(ceremony, language, timestamp):
    dtstamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(timestamp))
    location = ", ".join(value for value in (ceremony.get("name", ""), ceremony.get("address", "")) if value)
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//weronikarafal.com//ceremony//1.0", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        "UID:" + UID, "DTSTAMP:" + dtstamp, "DTSTART:" + DTSTART,
        "SUMMARY:" + _escape(SUMMARY_BY_LANGUAGE[language]),
    ]
    if location:
        lines.append("LOCATION:" + _escape(location))
    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    folded = []
    for content in lines:
        if len(content.encode("utf-8")) <= 75:
            folded.append(content)
        else:
            folded.extend(_fold(content))
    return "\r\n".join(folded) + "\r\n"
