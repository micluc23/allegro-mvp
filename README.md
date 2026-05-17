# Allegro MVP — generator szkicu aukcji

To jest proste MVP do tworzenia szkiców aukcji Allegro.

## Co robi

- pozwala wgrać zdjęcie kodu/EAN/SKU,
- próbuje odczytać kod przez OCR,
- szuka produktu w lokalnym pliku CSV,
- opcjonalnie próbuje zapytać Allegro Product Catalog, jeśli podasz token OAuth,
- generuje tytuł i opis HTML,
- pozwala edytować opis,
- eksportuje opis do HTML/TXT,
- zapisuje historię szkiców lokalnie.

## Instalacja

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

OCR wymaga programu Tesseract:

- Windows: zainstaluj Tesseract OCR i dodaj do PATH.
- macOS: `brew install tesseract`
- Ubuntu/Debian: `sudo apt install tesseract-ocr`

## Uruchomienie

```bash
streamlit run app.py
```

## Lokalna baza produktów

Edytuj `sample_products.csv` albo podmień go na własny plik CSV z kolumnami:

```text
code,ean,sku,name,brand,category,price,condition,stock,features,image_urls
```

W `features` wpisuj cechy rozdzielone średnikiem. W `image_urls` wpisuj linki do zdjęć rozdzielone średnikiem.

## Integracja z Allegro

MVP celowo nie wystawia aukcji automatycznie. To bezpieczniejszy pierwszy etap.

Kolejny krok to dodanie:

- logowania OAuth do Allegro,
- pobierania kategorii i parametrów obowiązkowych,
- walidacji oferty,
- tworzenia szkicu/oferty przez `POST /sale/product-offers`,
- obsługi cenników dostaw, zwrotów, reklamacji, faktur, GPSR i stanów magazynowych.

## Proponowana ścieżka rozwoju

1. Uporządkować własną bazę produktów CSV/Excel.
2. Dodać reguły opisów dla Twoich kategorii.
3. Dodać porównywanie cen konkurencji.
4. Dodać pełne wystawianie ofert przez Allegro API.
5. Połączyć z BaseLinkerem, jeśli sprzedajesz wielokanałowo.
