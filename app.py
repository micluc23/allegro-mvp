from __future__ import annotations

from dotenv import load_dotenv
import streamlit as st
from PIL import Image
from openai import OpenAI

from ocr_utils import read_code_from_image
from catalog import Product, find_local_product, search_allegro_product_catalog, product_from_allegro
from generator import make_title, make_description_html, make_plain_summary
from storage import save_listing, load_history

load_dotenv()

st.set_page_config(page_title="Allegro MVP Generator Aukcji", layout="wide")

def get_openai_client():
    api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)

def generate_ai_listing(product: Product) -> str:
    client = get_openai_client()
    if client is None:
        return "Brak OPENAI_API_KEY w Streamlit Secrets."

    prompt = f"""
Przygotuj profesjonalny opis aukcji na Allegro po polsku.

Dane produktu:
- Nazwa: {product.name}
- Marka: {product.brand}
- Kategoria: {product.category}
- Stan: {product.condition}
- Kod/EAN/SKU: {product.code or product.ean or product.sku}
- Cena: {product.price} zł
- Cechy/parametry: {product.features}

Wymagania:
- tekst ma być sprzedażowy, ale uczciwy
- nie wymyślaj danych technicznych, których nie ma
- nie obiecuj gwarancji, jeśli nie ma jej w danych
- przygotuj opis w HTML prosty do wklejenia do Allegro
- dodaj sekcje: Tytuł, Najważniejsze cechy, Opis produktu, Dlaczego warto, Informacje o ofercie, Słowa kluczowe SEO
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )
    return response.output_text

st.title("Allegro MVP — generator szkicu aukcji")
st.caption("Wgraj zdjęcie kodu produktu, uzupełnij dane i wygeneruj edytowalny opis do Allegro.")

with st.sidebar:
    st.header("Ustawienia")
    catalog_path = st.text_input("Plik lokalnej bazy CSV", value="sample_products.csv")
    use_allegro = st.checkbox("Spróbuj pobrać dane z Allegro Product Catalog", value=False)
    st.info("MVP nie publikuje ofert automatycznie. Generuje szkic, który możesz skopiować i poprawić.")

left, right = st.columns([1, 1.2])

with left:
    st.subheader("1. Zdjęcie kodu / kod ręczny")

    uploaded = st.file_uploader(
        "Wgraj zdjęcie etykiety, EAN lub SKU",
        type=["png", "jpg", "jpeg", "webp"],
    )

    detected_code = ""
    raw_ocr = ""

    if uploaded:
        image = Image.open(uploaded)
        st.image(image, caption="Wgrane zdjęcie", use_column_width=True)
        detected_code, raw_ocr = read_code_from_image(image)

        if detected_code:
            st.success(f"Wykryty kod: {detected_code}")
        else:
            st.warning("Nie wykryłem pewnego kodu. Wpisz go ręcznie poniżej.")

        with st.expander("Pokaż surowy wynik OCR"):
            st.text(raw_ocr)

    manual_code = st.text_input("Kod/EAN/SKU", value=detected_code or "")
    code = manual_code.strip()

    product = Product(
        code=code,
        ean=code if code.isdigit() else "",
        sku="" if code.isdigit() else code,
    )

    if code:
        local = find_local_product(code, catalog_path)
        if local:
            st.success("Znaleziono produkt w lokalnej bazie CSV.")
            product = local
        elif use_allegro:
            raw = search_allegro_product_catalog(code)
            if raw:
                st.success("Znaleziono produkt w Allegro Product Catalog.")
                product = product_from_allegro(raw, code)
            else:
                st.warning("Nie znaleziono produktu w podłączonych źródłach. Uzupełnij dane ręcznie.")

with right:
    st.subheader("2. Dane aukcji")

    name = st.text_input("Nazwa produktu", value=product.name)
    brand = st.text_input("Marka", value=product.brand)
    category = st.text_input("Kategoria robocza", value=product.category)

    c1, c2, c3 = st.columns(3)

    with c1:
        price = st.number_input(
            "Cena brutto",
            min_value=0.0,
            value=float(product.price or 0.0),
            step=1.0,
        )

    with c2:
        stock = st.number_input(
            "Liczba sztuk",
            min_value=1,
            value=int(product.stock or 1),
            step=1,
        )

    with c3:
        condition = st.selectbox(
            "Stan",
            ["Nowy", "Używany", "Po zwrocie", "Powystawowy"],
            index=0,
        )

    features = st.text_area(
        "Cechy/parametry — oddziel średnikiem",
        value=product.features,
        height=90,
    )

    image_urls = st.text_area(
        "Linki do zdjęć — oddziel średnikiem",
        value=product.image_urls,
        height=90,
    )

edited_product = Product(
    code=code,
    ean=code if code.isdigit() else product.ean,
    sku=product.sku or (code if not code.isdigit() else ""),
    name=name,
    brand=brand,
    category=category,
    price=price,
    condition=condition,
    stock=stock,
    features=features,
    image_urls=image_urls,
)

st.divider()
st.subheader("3. Gotowy szkic do edycji")

default_title = make_title(edited_product)
title = st.text_input("Tytuł aukcji", value=default_title, max_chars=75)

default_description = make_description_html(edited_product)

if "description" not in st.session_state:
    st.session_state.description = default_description

if st.button("🤖 Wygeneruj opis AI"):
    with st.spinner("AI tworzy opis aukcji..."):
        st.session_state.description = generate_ai_listing(edited_product)
        st.success("Opis AI został wygenerowany.")

description = st.text_area(
    "Opis HTML do wklejenia/poprawy",
    value=st.session_state.description,
    height=520,
)

st.session_state.description = description

plain = make_plain_summary(edited_product)

preview_col, export_col = st.columns([1, 1])

with preview_col:
    st.markdown("### Podgląd opisu")
    st.markdown(description, unsafe_allow_html=True)

with export_col:
    st.markdown("### Eksport")
    st.code(plain, language="text")

    st.download_button(
        "Pobierz opis HTML",
        description,
        file_name=f"opis_{code or 'produkt'}.html",
        mime="text/html",
    )

    st.download_button(
        "Pobierz dane TXT",
        f"{plain}\n\nOPIS HTML:\n{description}",
        file_name=f"aukcja_{code or 'produkt'}.txt",
        mime="text/plain",
    )

if st.button("Zapisz w historii"):
    save_listing(
        {
            "title": title,
            "product": edited_product.to_dict(),
            "description_html": description,
        }
    )
    st.success("Zapisano szkic w historii.")

with st.expander("Historia zapisanych szkiców"):
    history = load_history()

    if not history:
        st.write("Brak zapisanych szkiców.")
    else:
        for item in reversed(history[-10:]):
            st.write(f"**{item.get('created_at')}** — {item.get('title')}")
