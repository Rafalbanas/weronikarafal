# Weronika i Rafał

Statyczna strona ślubna: https://weronikarafal.com.

## CI/CD

GitHub Actions sprawdza każdy push i pull request: lokalne zasoby i odnośniki
HTML, składnię JavaScript oraz wdrażanie i automatyczne przywracanie wersji.
Po udanych testach push do `main` automatycznie wdraża dokładnie sprawdzoną
paczkę na VPS. Workflow można też uruchomić ręcznie na `main`.

Szczegóły serwera i odzyskiwania: [deploy/README.md](deploy/README.md).
