# Lokalny przegląd wizualny i diagnoza LCP

## Podgląd i porównanie

Podgląd uruchomiono na loopbacku, poza konfiguracją produkcyjną:

- AFTER: `https://127.0.0.1:18445/?lang=pl`
- BEFORE: `https://127.0.0.1:18444/?lang=pl`
- Galeria porównawcza: `http://127.0.0.1:18446/`

HTTPS używa samopodpisanego certyfikatu testowego. Bazy, sesje i sekret są
odseparowane od produkcji; nie utworzono rzeczywistych zaproszeń ani kont.
Podgląd AFTER przeładowuje szablony i wersje assets z katalogu roboczego.
Te adresy działają na hoście wykonania, nie są publicznymi adresami WWW.
Przy dostępie z innego komputera potrzebny jest tunel SSH do tych portów;
nie należy zmieniać bind na `0.0.0.0` ani dodawać publicznej konfiguracji Nginx.

BEFORE to archiwum `HEAD` sprzed redesignu, AFTER to aktualny katalog roboczy.
Zrzuty wykonano z działającego Flask przez HTTPS, w Chromium, przy viewportach
**1440 × 960** i **390 × 844**. Dodatkowo wykonano pełne strony i otwarte sceny.
Mapa jest przechwycona w automatycznych zrzutach, aby zewnętrzny iframe nie
wpływał na powtarzalność. W samym podglądzie mechanizm mapy pozostaje bez zmian.

Artefakty poza repozytorium: `/tmp/opencode/wedding-preview-review/`.
`screens-initial/` zachowuje stan redesignu przed lokalnymi korektami,
`screens/` końcowe zrzuty, `gallery/` zestawienia BEFORE/AFTER i zbliżenia kotów,
`videos/` nagrania interakcji. Żaden z tych plików nie wchodzi do wydania.

## Ocena krytyczna

### Co pozostawiono

- Hierarchia imiona → data → CTA jest czytelna. Szeryfowe imiona i kursywa
  odróżniają zaproszenie od wcześniejszego geometrycznego plakatu.
- Proporcje dwóch kolumn na desktopie są zrównoważone; negatywna przestrzeń
  nie wymaga wypełniania kolejnymi dekoracjami lub zdjęciami.
- Mobilny nagłówek celowo pozwala na drugi wiersz zamiast ściskać przyciski.
  Nie zastąpiono czytelnych etykiet anonimowymi ikonami.
- Nie zmieniano kolorystyki, monogramu, głównych proporcji ani kolejności
  informacji. Nie dodano efektów kursora lub kolejnych animacji.

### Rzeczywiste problemy i wąskie poprawki

1. **Niespodzianka zasłaniała godzinę na plakacie.** Absolutny komunikat
   przy dolnej krawędzi zastąpiono wspólnym slotem CSS Grid z dekoracyjnym
   podpisem. Otwarcie wymienia tylko podpis, nie datę, piątek ani 14:00.
   Slot zachowuje wysokość; SVG nadal wychyla się zza plakatu.
2. **Drobny tekst był zbyt mały na telefonie.** Wiadomość gwiazdki ma teraz
   12 px zamiast 10,72 px, jednostki odliczania 11 px zamiast 8,32 px.
   Etykiety mieszczą się także w EN przy 320 px.
3. **Stopka miała nadmiar pustej przestrzeni.** Scenę serca skrócono
   z 190 do 156 px, nadal rezerwując miejsce na koty i oba wiersze tekstu.
   Otwarcie nie przesuwa kredytu i nie obcina komunikatu.
4. **Animacja opóźniała widoczny tytuł i LCP.** Zachowano stagger, ale główny
   tekst nie zaczyna już od `opacity: 0`. Wejście trwa 600 zamiast 800 ms
   i animuje tylko przesunięcie 12 px. Reduced motion nadal wyłącza ruch.

## Co oznaczało LCP 2764 ms

Historyczny outlier dotyczył **1440 px / PL / dark / AFTER**. Stary zapis
zawierał tylko liczbę `startTime`, bez elementu LCP i waterfallu. Nie można
odtworzyć dokładnej przyczyny każdej z tych 2764 ms ani przypisać reszty czasu
serwerowi czy obciążeniu CPU bez ówczesnego trace.

Wykonano nowe, osobne pomiary z działającego serwera: po pięć na szerokość
i ustawienie ruchu, bez screenshotów i axe w trakcie pomiarów. Zapisano
kolejnych kandydatów LCP, renderTime/loadTime, navigation timing, zasoby,
FCP i long tasks. Przechwytywano wyłącznie zewnętrzną mapę, nie HTML/CSS/JS.

Przed korektą, na desktopie:

- kandydat LCP: **`SPAN.name-first`**, czyli tekst „Weronika”, nie obraz;
- zwykła animacja: **1020–1556 ms**, mediana **1188 ms**;
- reduced motion: **268–360 ms**, mediana **292 ms**;
- TTFB: **19–150 ms** przy zwykłym ruchu; występowały także long tasks.

W tych partiach wystąpiło ok. 0,9 s różnicy median; sama różnica nie izoluje
zmiennego obciążenia hosta. Nie jest to dowód, że całość historycznych
2764 ms pochodziła z animacji. `networkidle` nie dodaje automatycznie 500 ms
do `PerformanceEntry.startTime`; axe i screenshoty nie były izolowane od
poprzedniego audytu, więc nie należy traktować go jako czystego benchmarku.

Na telefonie największy element tekstowy to `P.hero-intro`, a nie tytuł;
dlatego efekt animacji tytułu nie powinien być uogólniany na wszystkie viewporty.
Nowy skrypt audytu zachowuje identyfikację kandydatów LCP i long tasks.

Po korekcie, w następnej partii: mediana desktopu 772 ms ze zwykłym ruchem
i 1152 ms przy reduced motion; na telefonie odpowiednio 404 i 660 ms.
Odwrócenie wyników pokazuje, dlaczego nie należy traktować pojedynczej partii
na współdzielonym hoście jako ścisłego testu przyczynowego.

### Kontrolowane A/B wariantów animacji

Wykonano następnie 6 par pomiarów, naprzemiennie A/B i B/A, w tym samym
Chromium przy 1440 × 960, PL/dark, na tym samym serwerze i aktualnym DOM.
Bez nagrywania, axe, screenshotów i wejścia użytkownika podczas pomiaru.
Jedyną celową różnicą był nadpisany wariant animacji CSS (pobranie CSS
przechodziło przez ten sam mechanizm `route.fetch/fulfill` w obu wariantach):

| Wariant | LCP min–max | Mediana |
| --- | --- | --- |
| A: poprzedni fade `opacity: 0`, 800 ms | 1164–3200 ms | **1744 ms** |
| B: widoczny tekst, tylko transform, 600 ms | 304–1088 ms | **816 ms** |

Wszystkie **6 z 6 par** miały niższy LCP w wariancie B; mediana różnic
w parach wyniosła 1010 ms. Elementem LCP w każdym pomiarze był `SPAN.name-first`.
W A `startTime` LCP wypadał 15–228 ms po zarejestrowanym `animationend` tytułu,
a w B już około 506–657 ms **przed** tym zdarzeniem. Potwierdza to realny koszt dotychczasowego
wejścia dla tego elementu; sam ruch transform nie wymaga czekania na jego koniec.
Nie wyjaśnia to z dokładnością do milisekundy starego outliera bez trace.
W najwolniejszym odtworzeniu (3200 ms) TTFB wyniósł 380 ms, FCP 1964 ms,
a observer wykazał m.in. long tasks 954 i 410 ms. Występowały więc także
istotne opóźnienia przetwarzania/renderu. Bez profilera z atrybucją nie należy
przypisywać tych zadań konkretnemu fragmentowi aplikacji lub zewnętrznej mapie
(mapa w eksperymencie była przechwycona).

Surowy zapis kontrolowany: `performance-paired.json`; skrypt eksperymentu:
`paired-lcp.py` w katalogu artefaktów. To mała próba lokalna, nie pomiar
produkcyjnego p75 ani gwarancja LCP poniżej 2,5 s dla rzeczywistych gości.

Wyniki surowe: `performance-before-tuning.json` i `performance-after-tuning.json`
w katalogu artefaktów. Pomiary są lokalne, nietrottlowane i nie dowodzą
spełnienia celów CWV w produkcji. Nie mierzono INP ani rzeczywistego p75.

## Walidacja końcowa

- 17 testów ukierunkowanych: assets, homepage, sceny, PL/EN, motywy i SEO — OK.
- Test regresyjny pilnuje braku `opacity: 0` na wejściu kluczowego tekstu.
- Kontrola Chromium sprawdza dodatkowo rozmiar etykiet odliczania, brak
  nakładania komunikatu na datę/godzinę, niezmienną wysokość plakatu po
  otwarciu gwiazdki i brak obcięcia sceny serca.
- Ostatnia kontrola: 32 warianty AFTER + 2 bazowe — OK; 8 audytów axe,
  0 zgłoszonych naruszeń wybranych reguł A/AA; maksymalny lokalny CLS 0,0015.
  Pozostają ręczne przypadki `incomplete`; nie jest to certyfikacja WCAG.
- Na działającym HTTPS sprawdzono CSP, no-store, anonimowe przekierowanie
  `/guest`, noindex logowania i odrzucenie POST bez CSRF z obcym Origin — OK.
- Logika aplikacji, baza produkcyjna, uprawnienia, CSRF, sesje i deployment
  nie zostały zmienione. Nie wykonano push, merge ani wdrożenia.
