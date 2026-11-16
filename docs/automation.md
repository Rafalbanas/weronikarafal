# Automatyzacja bez niespodzianek

## Co robią boty?

| Narzędzie | Rola | Czego nie robi |
| --- | --- | --- |
| Dependabot — Python | Co poniedziałek o 08:00 czasu Europe/Warsaw proponuje aktualizacje przypiętych zależności z `requirements.txt`. | Nie zatwierdza ani nie scala PR-ów. |
| Dependabot — GitHub Actions | Co poniedziałek o 08:30 proponuje aktualizacje akcji, zachowując przypięcie do pełnego SHA. | Nie dostaje klucza SSH wdrożenia. |
| GitHub Actions — `test` | Sprawdza składnię, renderowanie, testy aplikacji i pakowanie dla push i PR. | Testy nie wymagają prawdziwej bazy gości ani sekretów produkcyjnych. |
| GitHub Actions — `deploy` | Po udanym teście na `main` wdraża dokładnie sprawdzony artefakt przez istniejący odbiornik SSH. | Nie wdraża pull requestów ani gałęzi Dependabota. |

Konfiguracja: [Dependabot](../.github/dependabot.yml) i
[CI/CD](../.github/workflows/ci-cd.yml). Harmonogram oznacza plan sprawdzeń,
nie gwarantowany czas utworzenia PR.

Aktualizacje minor i patch są grupowane osobno dla obu ekosystemów.
Aktualizacje major pozostają osobnymi PR-ami. Limit to trzy otwarte PR-y
wersji na ekosystem. Grupowanie dotyczy aktualizacji wersji, nie alertów
bezpieczeństwa. Repozytorium nie dodaje automatycznego scalania, automatycznych
akceptacji ani wyzwalacza `pull_request_target` wykonującego obcy kod z sekretami.

## Co trzeba włączyć na GitHubie?

Po przesłaniu konfiguracji na domyślną gałąź sprawdź w ustawieniach repozytorium:

1. **Code security → Dependabot alerts** i **Dependabot security updates** —
   zależnie od dostępności i uprawnień. Sam plik YAML nie włącza tych usług.
2. **Actions** — dopuszczenie użytych akcji oraz prawo uruchamiania CI.
3. **Rulesets / branch protection** — przegląd PR i obowiązkowy check `test`
   przed scaleniem do `main`. Pliki repozytorium same nie wymuszają tych ustawień.
4. **Environment `production`** — potrzebne sekrety SSH i ewentualna ręczna
   akceptacja wdrożenia. W forku nie ustawiaj ich, jeśli chcesz tylko testować.
5. **Private vulnerability reporting** — jeśli chcesz przyjmować poufne
   zgłoszenia przez GitHub.

Nie skopiowano sekretów ani nie zmieniono ustawień zdalnego repozytorium.
Dependabotowe PR-y są traktowane jak niezaufany kod: mają przejść zwykły
przegląd i CI. Nie przekazuj im sekretów produkcyjnych w celu „naprawienia” testów.

## Ważne: aktualizacja zależności a wdrożenie

Istniejący odbiornik wydania celowo **odrzuca zmieniony `requirements.txt`**.
Zielone CI przy aktualizacji Pythona nie oznacza zatem gotowości do wdrożenia
nowego środowiska. Przed scaleniem takiego PR przygotuj zgodną aktualizację
zależności na serwerze, prywatną kopię danych i plan powrotu, zgodnie z
[instrukcją administracyjną](../deploy/README.md).

Scalenie do `main` uruchamia istniejący workflow wdrożenia, jeżeli jego
środowisko jest skonfigurowane. To nie jest neutralna operacja dokumentacyjna.
Nie włączaj automerge dla aktualizacji zależności bez osobno zaprojektowanej
procedury aktualizacji serwera.

## Propozycja opisu repozytorium

Do ręcznego wklejenia w **About**:

> A self-hosted wedding website with private RSVP, a shared guest album and an elegant bilingual experience. Flask, SQLite & vanilla JavaScript.

Proponowane topics:

`wedding` · `wedding-website` · `rsvp` · `flask` · `python` · `sqlite` ·
`self-hosted` · `vanilla-javascript` · `open-source`

Adres projektu: `https://weronikarafal.com` — rzeczywista strona wydarzenia,
nie otwarte demo panelu administratora.

## Licencja w artefakcie

Artefakt GitHub zawiera pliki `release.zip` oraz `LICENSE` obok siebie.
Zamknięta lista plików ZIP wdrożeniowego i odbiornik pozostają bez zmian.
Udostępniając kod, zachowaj notice licencji MIT.
