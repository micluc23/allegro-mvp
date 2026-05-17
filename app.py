from __future__ import annotations

import json
from dotenv import load_dotenv
import streamlit as st
from PIL import Image
import google.generativeai as genai

from ocr_utils import read_code_from_image
from catalog import Product, find_local_product, search_allegro_product_catalog, product_from_allegro
from generator import make_title, make_description_html, make_plain_summary
from storage import save_listing, load_history

load_dotenv()

st.set_page_config(page_title="Allegro MVP Generator Aukcji", layout="wide")


def get_gemini_model():
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.0-flash")


def safe_generate_text(parts):
    model = get_gemini_model()
    if model is None:
        return "Brak GEMINI_API_KEY w Streamlit Secrets."
    try:
        response = model.generate_content(parts)
        return response.text or "Brak odpowiedzi z Gemini."
    except Exception as exc:
        return f"Nie udało się połączyć z Gemini API. Szczegóły: {exc}"


def analyze_product_photos(images):
    prompt = """
Jesteś asystentem sprzedawcy Allegro. Analizujesz zdjęcia odzieży/bielizny oraz metek.

Zadanie:
1. Rozpoznaj produkt możliwie dokładnie.
2. Wypisz markę, typ produktu, kolor, rozmiar, płeć/grupę docelową, materiał/skład, kody z metek, numer modelu/SKU/EAN, stan produktu.
3. Nie wymyślaj danych. Jeśli czegoś nie widać, napisz: nie ustalono.
4. Przygotuj 8 bardzo dobrych fraz do wyszukiwania produktu w Google/Grafika/Google Lens/Allegro.
5. Przygotuj propozycję tytułu Allegro do 75 znaków.
6. Przygotuj krótki opis produktu do aukcji.

Zwróć wynik po polsku w czytelnej formie z nagłówkami.
Na końcu dodaj sekcję:
DANE DO SKOPIOWANIA:
Marka: ...
Nazwa: ...
Kategoria: ...
Cechy: ...
Frazy: ...
"""
    parts = [prompt]
    for img in images:
        parts.append(img.convert("RGB"))
    return safe_generate_text(parts)


def generate_ai_listing(product: Product) -> str:
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
- tekst sprzedażowy, ale uczciwy
- nie wymyślaj danych technicznych
- nie obiecuj gwarancji, jeśli jej nie ma w danych
- prosty HTML do Allegro
- sekcje: Tytuł, Najważniejsze cechy, Opis produktu, Dlaczego warto, Informacje o ofercie, Słowa kluczowe SEO
"""
    return safe_generate_text(prompt)


st.title("Allegro MVP — generator szkicu aukcji")
st.caption("Wgraj zdjęcia produktu/metek, rozpoznaj produkt i wygeneruj edytowalny opis do Allegro.")

with st.sidebar:
    st.header("Ustawienia")
    catalog_path = st.text_input("Plik lokalnej bazy CSV", value="sample_products.csv")
    use_allegro = st.checkbox("Spróbuj pobrać dane z Allegro Product Catalog", value=False)
    st.info("MVP nie publikuje ofert automatycznie. Generuje szkic, który możesz skopiować i poprawić.")

main_tab, photo_tab = st.tabs(["📝 Generator aukcji", "🔎 Rozpoznanie produktu ze zdjęć"])

with photo_tab:
    st.subheader("Rozpoznanie produktu ze zdjęć")
    st.write("Dodaj kilka zdjęć: cały produkt, metka z marką, metka ze składem/kodem, ewentualnie opakowanie.")

    product_photos = st.file_uploader(
        "Zdjęcia produktu/metek",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key="product_photos",
    )

    loaded_images = []
    if product_photos:
        cols = st.columns(4)
        for i, file in enumerate(product_photos):
            img = Image.open(file)
            loaded_images.append(img)
            with cols[i % 4]:
                st.image(img, caption=file.name, use_column_width=True)

    if st.button("🔎 Rozpoznaj produkt przez Gemini AI", disabled=not loaded_images):
        with st.spinner("Analizuję zdjęcia produktu i metek..."):
            st.session_state.photo_analysis = analyze_product_photos(loaded_images)

    analysis = st.session_state.get("photo_analysis", "")
    if analysis:
        st.markdown("### Wynik rozpoznania")
        st.text_area("Analiza AI", value=analysis, height=520)
        st.download_button(
            "Pobierz analizę TXT",
            analysis,
            file_name="analiza_produktu.txt",
            mime="text/plain",
        )

with main_tab:
    left, right = st.columns([1, 1.2])

    with left:
        st.subheader("1. Zdjęcie kodu / kod ręczny")

        uploaded = st.file_uploader(
            "Wgraj zdjęcie etykiety, EAN lub SKU",
            type=["png", "jpg", "jpeg", "webp"],
            key="code_photo",
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

        product = Product(code=code, ean=code if code.isdigit() else "", sku="" if code.isdigit() else code)

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
            price = st.number_input("Cena brutto", min_value=0.0, value=float(product.price or 0.0), step=1.0)
        with c2:
            stock = st.number_input("Liczba sztuk", min_value=1, value=int(product.stock or 1), step=1)
        with c3:
            condition = st.selectbox("Stan", ["Nowy", "Używany", "Po zwrocie", "Powystawowy"], index=0)

        features = st.text_area("Cechy/parametry — oddziel średnikiem", value=product.features, height=90)
        image_urls = st.text_area("Linki do zdjęć — oddziel średnikiem", value=product.image_urls, height=90)

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

    title = st.text_input("Tytuł aukcji", value=make_title(edited_product), max_chars=75)

    if "description" not in st.session_state:
        st.session_state.description = make_description_html(edited_product)

    if st.button("🤖 Wygeneruj opis Gemini AI"):
        with st.spinner("Gemini tworzy opis aukcji..."):
            st.session_state.description = generate_ai_listing(edited_product)

    description = st.text_area("Opis HTML do wklejenia/poprawy", value=st.session_state.description, height=420)
    st.session_state.description = description

    plain = make_plain_summary(edited_product)

    preview_col, export_col = st.columns([1, 1])

    with preview_col:
        st.markdown("### Podgląd opisu")
        st.markdown(description, unsafe_allow_html=True)

    with export_col:
        st.markdown("### Eksport")
        st.code(plain, language="text")
        st.download_button("Pobierz opis HTML", description, file_name=f"opis_{code or 'produkt'}.html", mime="text/html")
        st.download_button("Pobierz dane TXT", f"{plain}\n\nOPIS HTML:\n{description}", file_name=f"aukcja_{code or 'produkt'}.txt", mime="text/plain")

    if st.button("Zapisz w historii"):
        save_listing({"title": title, "product": edited_product.to_dict(), "description_html": description})
        st.success("Zapisano szkic w historii.")

    with st.expander("Historia zapisanych szkiców"):
        history = load_history()
        if not history:
            st.write("Brak zapisanych szkiców.")
        else:
            for item in reversed(history[-10:]):
                st.write(f"**{item.get('created_at')}** — {item.get('title')}")
