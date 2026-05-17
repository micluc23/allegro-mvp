from __future__ import annotations
from catalog import Product, image_url_list


def make_title(product: Product) -> str:
    base = f"{product.name} {product.brand}".strip()
    return base[:75] if base else f"Produkt {product.code}"[:75]


def make_description_html(product: Product) -> str:
    features = []
    if product.features:
        for part in str(product.features).split(";"):
            part = part.strip()
            if part:
                features.append(part)

    feature_html = "\n".join([f"<li>{f}</li>" for f in features]) or "<li>Uzupełnij najważniejsze cechy produktu.</li>"
    images = image_url_list(product)
    image_html = "\n".join([f'<p><img src="{url}" alt="{product.name}" /></p>' for url in images])

    return f"""
<h2>{product.name or 'Nazwa produktu'}</h2>
<p><strong>Marka:</strong> {product.brand or 'uzupełnij'}</p>
<p><strong>Stan:</strong> {product.condition or 'Nowy'}</p>

<h3>Najważniejsze cechy</h3>
<ul>
{feature_html}
</ul>

<h3>Opis produktu</h3>
<p>
{product.name or 'Ten produkt'} to praktyczny wybór dla osób, które szukają sprawdzonego rozwiązania w dobrej cenie.
Opis możesz łatwo poprawić przed wklejeniem do Allegro — dodaj własne informacje o zastosowaniu, kompatybilności i zawartości zestawu.
</p>

<h3>Informacje o ofercie</h3>
<ul>
<li>Kod produktu: {product.code or product.ean or product.sku or 'uzupełnij'}</li>
<li>Kategoria robocza: {product.category or 'uzupełnij'}</li>
<li>Dostępna liczba sztuk: {product.stock or 1}</li>
</ul>
{image_html}
""".strip()


def make_plain_summary(product: Product) -> str:
    return f"""TYTUŁ: {make_title(product)}
CENA: {product.price or 'uzupełnij'} zł
STAN: {product.condition or 'Nowy'}
KATEGORIA: {product.category or 'uzupełnij'}
KOD/EAN/SKU: {product.code or product.ean or product.sku or 'uzupełnij'}
""".strip()
