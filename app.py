from __future__ import annotations

import base64
import json
import os
from io import BytesIO

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


def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)


def get_openai_client():
    api_key = get_secret("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def image_to_data_url(image: Image.Image, max_size: int = 1280) -> str:
    img = image.convert("RGB")
    img.thumbnail((max_size, max_size))

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def analyze_product_photos(images: list[Image.Image]) -> dict:
    client = get_openai_client()
    if client is None:
        return {
            "error": "Brak OPENAI_API_KEY w Streamlit Secrets. Dodaj klucz w Manage app → Settings → Secrets."
        }

    content = [
        {
            "type": "input_text",
            "text": """
Jesteś asystentem sprzedawcy Allegro specjalizującym się w odzieży i bieliźnie.
Na podstawie zdjęć produktu oraz metek spróbuj rozpoznać produkt.

Zwróć WYŁĄCZNIE poprawny JSON bez komentarzy i bez markdown.
Nie wymyślaj danych. Jeśli czegoś nie widać, wpisz pusty string albo pustą listę.

Schemat:
{
  "brand": "",
  "product_type": "",
  "gender": "",
  "color": "",
  "size": "",
  "model": "",
  "codes": [],
  "materials": [],
  "visible_text": [],
  "confidence": "niska/srednia/wysoka",
  "short_identification": "",
  "allegro_title": "",
  "features": [],
  "search_queries": [],
  "google_lens_tip": "",
  "notes": ""
}

Zasady:
- product_type po polsku, np. biustonosz, majtki, bokserki, koszulka, legginsy.
- allegro_title maksymalnie 75 znaków.
- search_queries przygotuj tak, żeby użytkownik mógł skopiować je do Google/Grafiki/Allegro.
- w search_queries uwzględnij markę, typ, kolor, rozmiar, kody z metek, jeśli są widoczne.
- jeśli to bielizna, nie używaj przesadzonego języka reklamowego.
""",
        }
    ]

    for image in images[:6]:
        content.append(
            {
                "type": "input_image",
                "image_url": image_to_data_url(image),
            }
        )

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[{"role": "user", "content": content}],
    )

    text = response.output_text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "error": "AI zwróciło odpowiedź, ale nie udało się jej odczytać jako JSON.",
            "raw": text,
        }


def generate_ai_listing(product: Product, extra_context: str = "") -> str:
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
- Dodatkowy kontekst z rozpoznania zdjęć: {extra_context}

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
st.caption("Wgraj zdjęcia produktu lub metki, rozpoznaj produkt przez AI i wygeneruj opis do Allegro.")

with st.sidebar:
    st.header("Ustawienia")
    catalog_path = st.text_input("Plik lokalnej bazy CSV", value="sample_products.csv")
    use_allegro = st.checkbox("Spróbuj pobrać dane z Allegro Product Catalog", value=False)
    st.info("MVP nie publikuje ofert automatycznie. Generuje szkic, który możesz skopiować i poprawić.")

tab_ai, tab_listing = st.tabs(["🔎 Rozpoznanie produktu ze zdjęć", "📝 Szkic aukcji"])

with tab_ai:
    st.subheader("1. Dodaj kilka zdjęć produktu / metek")

    product_photos = st.file_uploader(
        "Wgraj zdjęcia produktu, metki, kodu, opakowania",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
    )

    loaded_images: list[Image.Image] = []

    if product_photos:
        cols = st.columns(3)
        for idx, file in enumerate(product_photos):
            image = Image.open(file)
            loaded_images.append(image)
            with cols[idx % 3]:
                st.image(image, caption=file.name, use_container_width=True)

        st.caption("Najlepiej dodaj: zdjęcie całego produktu, metkę z marką, metkę z kodem/składem i ewentualnie opakowanie.")

    if st.button("🔎 Rozpoznaj produkt przez AI", disabled=not bool(loaded_images)):
        with st.spinner("Analizuję zdjęcia i metki..."):
            result = analyze_product_photos(loaded_images)
            st.session_state.photo_analysis = result

    analysis = st.session_state.get("photo_analysis")

    if analysis:
        if analysis.get("error"):
            st.error(analysis.get("error"))
            if analysis.get("raw"):
                st.text_area("Surowa odpowiedź AI", value=analysis.get("raw", ""), height=240)
        else:
            st.success("Rozpoznanie gotowe.")

            c1, c2, c3 = st.columns(3)
            c1.metric("Marka", analysis.get("brand") or "—")
            c2.metric("Typ", analysis.get("product_type") or "—")
            c3.metric("Pewność", analysis.get("confidence") or "—")

            st.markdown("### Co rozpoznałem")
            st.write(analysis.get("short_identification") or "Brak krótkiego opisu.")

            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown("#### Dane do aukcji")
                st.write(f"**Kolor:** {analysis.get('color') or '—'}")
                st.write(f"**Rozmiar:** {analysis.get('size') or '—'}")
                st.write(f"**Model:** {analysis.get('model') or '—'}")
                st.write(f"**Płeć/grupa:** {analysis.get('gender') or '—'}")
                st.write(f"**Kody:** {', '.join(analysis.get('codes') or []) or '—'}")
                st.write(f"**Materiały:** {', '.join(analysis.get('materials') or []) or '—'}")

            with col_b:
                st.markdown("#### Cechy")
                features_list = analysis.get("features") or []
                if features_list:
                    for item in features_list:
                        st.write(f"- {item}")
                else:
                    st.write("—")

            st.markdown("### Gotowe frazy do szukania zdjęć/produktu")
            queries = analysis.get("search_queries") or []
            if queries:
                for q in queries:
                    st.code(q, language="text")
            else:
                st.write("Brak fraz.")

            st.markdown("### Tytuł roboczy Allegro")
            st.code(analysis.get("allegro_title") or "", language="text")

            st.info(
                "Uwaga: znalezione w sieci zdjęcia traktuj jako materiał referencyjny. "
                "Do aukcji najbezpieczniej używać własnych zdjęć albo zdjęć producenta, jeśli masz prawo ich użyć."
            )

            if st.button("➡️ Przenieś rozpoznane dane do szkicu aukcji"):
                st.session_state.ai_brand = analysis.get("brand", "")
                st.session_state.ai_name = analysis.get("allegro_title", "")
                st.session_state.ai_category = analysis.get("product_type", "")
                st.session_state.ai_features = "; ".join(analysis.get("features") or [])
                st.session_state.ai_code = (analysis.get("codes") or [""])[0]
                st.success("Dane przeniesione. Przejdź do zakładki „Szkic aukcji”.")

with tab_listing:
    left, right = st.columns([1, 1.2])

    with left:
        st.subheader("2. Zdjęcie kodu / kod ręczny")

        uploaded = st.file_uploader(
            "Wgraj jedno zdjęcie etykiety, EAN lub SKU",
            type=["png", "jpg", "jpeg", "webp"],
            key="single_code_upload",
        )

        detected_code = ""
        raw_ocr = ""

        if uploaded:
            image = Image.open(uploaded)
            st.image(image, caption="Wgrane zdjęcie", use_container_width=True)
            detected_code, raw_ocr = read_code_from_image(image)

            if detected_code:
                st.success(f"Wykryty kod: {detected_code}")
            else:
                st.warning("Nie wykryłem pewnego kodu. Wpisz go ręcznie poniżej.")

            with st.expander("Pokaż surowy wynik OCR"):
                st.text(raw_ocr)

        manual_code = st.text_input("Kod/EAN/SKU", value=detected_code or st.session_state.get("ai_code", ""))
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
        st.subheader("3. Dane aukcji")

        default_name = product.name or st.session_state.get("ai_name", "")
        default_brand = product.brand or st.session_state.get("ai_brand", "")
        default_category = product.category or st.session_state.get("ai_category", "")
        default_features = product.features or st.session_state.get("ai_features", "")

        name = st.text_input("Nazwa produktu", value=default_name)
        brand = st.text_input("Marka", value=default_brand)
        category = st.text_input("Kategoria robocza", value=default_category)

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
            value=default_features,
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
    st.subheader("4. Gotowy szkic do edycji")

    title = st.text_input("Tytuł aukcji", value=make_title(edited_product), max_chars=75)

    if "description" not in st.session_state:
        st.session_state.description = make_description_html(edited_product)

    if st.button("🤖 Wygeneruj opis AI"):
        with st.spinner("AI tworzy opis aukcji..."):
            extra = json.dumps(st.session_state.get("photo_analysis", {}), ensure_ascii=False)
            st.session_state.description = generate_ai_listing(edited_product, extra_context=extra)
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
