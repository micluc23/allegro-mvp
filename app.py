from __future__ import annotations

import json
import base64
from datetime import datetime
from pathlib import Path
from io import BytesIO
from typing import Any, Dict, List

import streamlit as st
import pandas as pd
import requests
from PIL import Image

try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


TEMPLATES_FILE = Path("saved_templates.json")
INVENTORY_FILE = Path("inventory.json")

DEFAULT_AUCTION_DATA: Dict[str, Any] = {
    "product_name": "",
    "brand": "",
    "category": "",
    "condition": "Nowy",
    "size": "",
    "color": "",
    "code": "",
    "price": 0.0,
    "stock": 1,
    "features": "",
    "image_urls": "",
    "title": "",
    "description": "",
    "manual_notes": "",
}

DEFAULT_INVENTORY_ITEM: Dict[str, Any] = {
    "id": "",
    "created_at": "",
    "product_name": "",
    "brand": "",
    "category": "",
    "condition": "Nowy",
    "size": "",
    "color": "",
    "code": "",
    "quantity": 1,
    "location": "",
    "status": "Do wystawienia",
    "purchase_cost": 0.0,
    "sale_price": 0.0,
    "notes": "",
    "image_urls": "",
    "offer_id": "",
    "allegro_url": "",
    "external_id": "",
}


# -----------------------------
# Login
# -----------------------------
def login_screen() -> None:
    st.set_page_config(page_title="AI Sprzedawca Allegro — logowanie", layout="centered")
    st.title("🔒 Logowanie")
    st.caption("Dostęp do aplikacji jest zabezpieczony.")

    app_users = st.secrets.get("APP_USERS", {})

    if not app_users:
        st.error("Brak skonfigurowanych użytkowników. Dodaj APP_USERS w Streamlit Secrets.")
        st.code('APP_USERS = { "michal" = "twoje_haslo", "wspolniczka" = "jej_haslo" }', language="toml")
        st.stop()

    username = st.text_input("Login")
    password = st.text_input("Hasło", type="password")

    if st.button("Zaloguj", use_container_width=True):
        if username in app_users and app_users[username] == password:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.rerun()
        else:
            st.error("Nieprawidłowy login lub hasło.")

    st.stop()


def require_login() -> None:
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if not st.session_state.logged_in:
        login_screen()


# -----------------------------
# State
# -----------------------------
def init_state() -> None:
    for key, value in DEFAULT_AUCTION_DATA.items():
        if key not in st.session_state:
            st.session_state[key] = value

    defaults = {
        "recognized_text": "",
        "recognized_search_phrases": "",
        "dry_run": True,
        "loaded_template_name": "",
        "inventory_loaded_item": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_auction_data() -> None:
    for key, value in DEFAULT_AUCTION_DATA.items():
        st.session_state[key] = value
    st.session_state.recognized_text = ""
    st.session_state.recognized_search_phrases = ""
    st.session_state.loaded_template_name = ""
    st.session_state.inventory_loaded_item = ""


def reset_description_only() -> None:
    st.session_state.title = ""
    st.session_state.description = ""


def build_manual_description() -> str:
    features = st.session_state.get("features", "")
    items = [x.strip() for x in features.replace("\n", ";").split(";") if x.strip()]
    features_html = "\n".join(f"<li>{item}</li>" for item in items)

    return f"""<h2>{st.session_state.get("product_name") or "Produkt"}</h2>

<p><strong>Marka:</strong> {st.session_state.get("brand") or "Brak danych"}</p>
<p><strong>Kategoria:</strong> {st.session_state.get("category") or "Odzież / bielizna"}</p>
<p><strong>Stan:</strong> {st.session_state.get("condition") or "Nowy"}</p>
<p><strong>Rozmiar:</strong> {st.session_state.get("size") or "Brak danych"}</p>
<p><strong>Kolor:</strong> {st.session_state.get("color") or "Brak danych"}</p>
<p><strong>Kod produktu / EAN / SKU:</strong> {st.session_state.get("code") or "Brak danych"}</p>

<h3>Najważniejsze cechy</h3>
<ul>
{features_html or "<li>Uzupełnij najważniejsze cechy produktu.</li>"}
</ul>

<h3>Opis produktu</h3>
<p>Uzupełnij opis produktu: krój, materiał, przeznaczenie, wygoda użytkowania oraz najważniejsze informacje widoczne na metce.</p>

<h3>Informacje o ofercie</h3>
<p>Produkt sprzedawany zgodnie z opisem i zdjęciami. Przed zakupem sprawdź rozmiar oraz szczegóły oferty.</p>
"""


def sync_recognition_to_auction() -> None:
    text = st.session_state.get("recognized_text", "")
    phrases = st.session_state.get("recognized_search_phrases", "")
    if text:
        st.session_state.manual_notes = text
    if phrases:
        st.session_state.features = phrases


# -----------------------------
# JSON storage
# -----------------------------
def read_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def write_json_list(path: Path, items: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


# -----------------------------
# Templates
# -----------------------------
def load_templates() -> List[Dict[str, Any]]:
    return read_json_list(TEMPLATES_FILE)


def save_templates(templates: List[Dict[str, Any]]) -> None:
    write_json_list(TEMPLATES_FILE, templates)


def current_template_payload(name: str) -> Dict[str, Any]:
    return {
        "name": name.strip(),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": {key: st.session_state.get(key, value) for key, value in DEFAULT_AUCTION_DATA.items()},
        "recognized_text": st.session_state.get("recognized_text", ""),
        "recognized_search_phrases": st.session_state.get("recognized_search_phrases", ""),
    }


def save_current_template(name: str) -> None:
    name = name.strip()
    if not name:
        st.warning("Podaj nazwę szablonu.")
        return

    templates = load_templates()
    templates = [tpl for tpl in templates if tpl.get("name") != name]
    templates.append(current_template_payload(name))
    save_templates(templates)
    st.success(f"Zapisano szablon: {name}")


def load_template_into_state(template: Dict[str, Any]) -> None:
    data = template.get("data", {})
    for key, default in DEFAULT_AUCTION_DATA.items():
        st.session_state[key] = data.get(key, default)

    st.session_state.recognized_text = template.get("recognized_text", "")
    st.session_state.recognized_search_phrases = template.get("recognized_search_phrases", "")
    st.session_state.loaded_template_name = template.get("name", "")


def delete_template(name: str) -> None:
    templates = [tpl for tpl in load_templates() if tpl.get("name") != name]
    save_templates(templates)


# -----------------------------
# Inventory
# -----------------------------
def load_inventory() -> List[Dict[str, Any]]:
    return read_json_list(INVENTORY_FILE)


def save_inventory(items: List[Dict[str, Any]]) -> None:
    write_json_list(INVENTORY_FILE, items)


def next_inventory_id(items: List[Dict[str, Any]]) -> str:
    today = datetime.now().strftime("%Y%m%d")
    existing_numbers = []
    for item in items:
        item_id = str(item.get("id", ""))
        if item_id.startswith(f"P-{today}-"):
            try:
                existing_numbers.append(int(item_id.split("-")[-1]))
            except Exception:
                pass
    next_no = max(existing_numbers, default=0) + 1
    return f"P-{today}-{next_no:04d}"


def inventory_payload_from_form(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    item_id = st.session_state.get("inv_id") or next_inventory_id(items)
    return {
        "id": item_id,
        "created_at": st.session_state.get("inv_created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "product_name": st.session_state.get("inv_product_name", ""),
        "brand": st.session_state.get("inv_brand", ""),
        "category": st.session_state.get("inv_category", ""),
        "condition": st.session_state.get("inv_condition", "Nowy"),
        "size": st.session_state.get("inv_size", ""),
        "color": st.session_state.get("inv_color", ""),
        "code": st.session_state.get("inv_code", ""),
        "quantity": int(st.session_state.get("inv_quantity", 1)),
        "location": st.session_state.get("inv_location", ""),
        "status": st.session_state.get("inv_status", "Do wystawienia"),
        "purchase_cost": float(st.session_state.get("inv_purchase_cost", 0.0)),
        "sale_price": float(st.session_state.get("inv_sale_price", 0.0)),
        "notes": st.session_state.get("inv_notes", ""),
        "image_urls": st.session_state.get("inv_image_urls", ""),
    }


def clear_inventory_form() -> None:
    fields = {
        "inv_id": "",
        "inv_created_at": "",
        "inv_product_name": "",
        "inv_brand": "",
        "inv_category": "",
        "inv_condition": "Nowy",
        "inv_size": "",
        "inv_color": "",
        "inv_code": "",
        "inv_quantity": 1,
        "inv_location": "",
        "inv_status": "Do wystawienia",
        "inv_purchase_cost": 0.0,
        "inv_sale_price": 0.0,
        "inv_notes": "",
        "inv_image_urls": "",
    }
    for key, value in fields.items():
        st.session_state[key] = value


def load_inventory_item_to_form(item: Dict[str, Any]) -> None:
    st.session_state.inv_id = item.get("id", "")
    st.session_state.inv_created_at = item.get("created_at", "")
    st.session_state.inv_product_name = item.get("product_name", "")
    st.session_state.inv_brand = item.get("brand", "")
    st.session_state.inv_category = item.get("category", "")
    st.session_state.inv_condition = item.get("condition", "Nowy")
    st.session_state.inv_size = item.get("size", "")
    st.session_state.inv_color = item.get("color", "")
    st.session_state.inv_code = item.get("code", "")
    st.session_state.inv_quantity = int(item.get("quantity", 1) or 1)
    st.session_state.inv_location = item.get("location", "")
    st.session_state.inv_status = item.get("status", "Do wystawienia")
    st.session_state.inv_purchase_cost = float(item.get("purchase_cost", 0.0) or 0.0)
    st.session_state.inv_sale_price = float(item.get("sale_price", 0.0) or 0.0)
    st.session_state.inv_notes = item.get("notes", "")
    st.session_state.inv_image_urls = item.get("image_urls", "")


def load_inventory_item_to_auction(item: Dict[str, Any]) -> None:
    st.session_state.product_name = item.get("product_name", "")
    st.session_state.brand = item.get("brand", "")
    st.session_state.category = item.get("category", "")
    st.session_state.condition = item.get("condition", "Nowy")
    st.session_state.size = item.get("size", "")
    st.session_state.color = item.get("color", "")
    st.session_state.code = item.get("code", "")
    st.session_state.stock = int(item.get("quantity", 1) or 1)
    st.session_state.price = float(item.get("sale_price", 0.0) or 0.0)
    st.session_state.manual_notes = item.get("notes", "")
    st.session_state.image_urls = item.get("image_urls", "")
    st.session_state.title = " ".join(
        [
            item.get("brand", ""),
            item.get("product_name", ""),
            item.get("size", ""),
            item.get("color", ""),
        ]
    ).strip()
    st.session_state.description = build_manual_description()
    st.session_state.inventory_loaded_item = item.get("id", "")


def update_inventory_status(item_id: str, status: str) -> None:
    items = load_inventory()
    for item in items:
        if item.get("id") == item_id:
            item["status"] = status
            item["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_inventory(items)


def clean_csv_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.lower() == "nan":
        return ""
    # fix GTIN that pandas sometimes reads as 3.340444e+12
    if "e+" in text.lower():
        try:
            return str(int(float(text)))
        except Exception:
            return text
    if text.endswith(".0") and text.replace(".0", "").isdigit():
        return text.replace(".0", "")
    return text.strip()


def infer_brand_from_name(name: str) -> str:
    if not name:
        return ""
    return name.split()[0].strip(" ,-").upper()


def infer_size_from_name(name: str) -> str:
    import re
    patterns = [
        r"\bEU\s*([0-9]{2,3}[A-Z]{0,2}|XS|S|M|L|XL|XXL|XXXL)\b",
        r"\b(XXXS|XXS|XS|S|M|L|XL|XXL|XXXL)\b",
        r"\b([0-9]{2,3}[A-Z]{1,2})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, name, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return ""


def map_allegro_status(status: str) -> str:
    status = (status or "").upper()
    if status == "ACTIVE":
        return "Wystawione"
    if status in ["ENDED", "INACTIVE", "CLOSED"]:
        return "Archiwum"
    return "Do wystawienia"


def import_allegro_csv(uploaded_file, overwrite_existing: bool = True) -> Dict[str, int]:
    try:
        df = pd.read_csv(uploaded_file, dtype=str)
    except Exception:
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, sep=";", dtype=str)

    inventory = load_inventory()
    existing_by_id = {item.get("id"): item for item in inventory}

    imported = 0
    updated = 0
    skipped = 0

    for _, row in df.iterrows():
        offer_id = clean_csv_value(row.get("offer_id", ""))
        name = clean_csv_value(row.get("name", ""))
        if not offer_id and not name:
            skipped += 1
            continue

        item_id = f"ALG-{offer_id}" if offer_id else next_inventory_id(inventory)
        if item_id in existing_by_id and not overwrite_existing:
            skipped += 1
            continue

        stock_raw = clean_csv_value(row.get("stock", "1"))
        price_raw = clean_csv_value(row.get("price@allegro-pl", "0"))
        try:
            quantity = int(float(stock_raw or 1))
        except Exception:
            quantity = 1
        try:
            sale_price = float((price_raw or "0").replace(",", "."))
        except Exception:
            sale_price = 0.0

        payload = {
            "id": item_id,
            "created_at": existing_by_id.get(item_id, {}).get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "product_name": name,
            "brand": infer_brand_from_name(name),
            "category": "Bielizna / odzież",
            "condition": "Nowy",
            "size": infer_size_from_name(name),
            "color": "",
            "code": clean_csv_value(row.get("gtin", "")),
            "quantity": quantity,
            "location": existing_by_id.get(item_id, {}).get("location", ""),
            "status": map_allegro_status(clean_csv_value(row.get("status", ""))),
            "purchase_cost": float(existing_by_id.get(item_id, {}).get("purchase_cost", 0.0) or 0.0),
            "sale_price": sale_price,
            "notes": f"Import z Allegro. offer_id: {offer_id}. external_id: {clean_csv_value(row.get('external_id', ''))}.",
            "image_urls": existing_by_id.get(item_id, {}).get("image_urls", ""),
            "offer_id": offer_id,
            "allegro_url": clean_csv_value(row.get("url", "")),
            "external_id": clean_csv_value(row.get("external_id", "")),
        }

        if item_id in existing_by_id:
            inventory = [payload if item.get("id") == item_id else item for item in inventory]
            updated += 1
        else:
            inventory.append(payload)
            imported += 1

        existing_by_id[item_id] = payload

    save_inventory(inventory)
    return {"imported": imported, "updated": updated, "skipped": skipped}



# -----------------------------
# AI / internet image search
# -----------------------------
def image_to_data_url(image: Image.Image, max_size: int = 1200) -> str:
    """Prepare image for SerpApi Google Lens as base64 data URL."""
    img = image.convert("RGB")
    img.thumbnail((max_size, max_size))
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def search_google_lens_serpapi(image: Image.Image, query: str = "", country: str = "pl", limit: int = 12) -> Dict[str, Any]:
    """Search visually similar products using SerpApi Google Lens."""
    api_key = st.secrets.get("SERPAPI_API_KEY", "")
    if not api_key:
        return {
            "error": "Brak SERPAPI_API_KEY w Streamlit Secrets. Dodaj klucz SerpApi, żeby włączyć wyszukiwanie zdjęć."
        }

    params = {
        "engine": "google_lens",
        "api_key": api_key,
        "url": image_to_data_url(image),
        "country": country,
        "hl": "pl",
        "safe": "active",
    }

    if query.strip():
        params["q"] = query.strip()

    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=45)
        response.raise_for_status()
        data = response.json()

        matches = (
            data.get("visual_matches")
            or data.get("exact_matches")
            or data.get("products")
            or []
        )

        normalized = []
        for item in matches[:limit]:
            normalized.append(
                {
                    "title": item.get("title", ""),
                    "source": item.get("source", ""),
                    "link": item.get("link", ""),
                    "thumbnail": item.get("thumbnail", "") or item.get("image", ""),
                    "price": item.get("price", ""),
                    "rating": item.get("rating", ""),
                    "in_stock": item.get("in_stock", ""),
                }
            )

        return {"results": normalized, "raw_count": len(matches)}
    except Exception as exc:
        return {"error": f"Nie udało się wykonać wyszukiwania Google Lens przez SerpApi: {exc}"}


def append_image_link_to_auction(link: str) -> None:
    current = st.session_state.get("image_urls", "").strip()
    links = [x.strip() for x in current.replace("\n", ";").split(";") if x.strip()]
    if link and link not in links:
        links.append(link)
    st.session_state.image_urls = "; ".join(links)


# -----------------------------
# AI
# -----------------------------
def get_gemini_model():
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        return None, "Brak GEMINI_API_KEY w Streamlit Secrets."
    if genai is None:
        return None, "Brak biblioteki google-generativeai. Sprawdź requirements.txt."
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.0-flash"), ""


def recognize_with_gemini(images: List[Image.Image]) -> str:
    if st.session_state.dry_run:
        return """TRYB TESTOWY — przykładowy wynik rozpoznania:

Produkt: biustonosz / bielizna damska
Marka: do uzupełnienia po metce
Kolor: do sprawdzenia ze zdjęcia
Rozmiar: do odczytania z metki
Możliwe kody: sprawdź etykietę i kod kreskowy

Frazy do wyszukiwania:
- marka + kod z metki + biustonosz
- marka + rozmiar + kolor + bielizna
- kod produktu + bra
- numer z metki + lingerie
"""

    model, error = get_gemini_model()
    if error:
        return f"Nie udało się połączyć z Gemini API. Szczegóły: {error}"

    prompt = """
Jesteś asystentem sprzedawcy odzieży i bielizny na Allegro.
Na podstawie zdjęć rozpoznaj produkt i metki.

Zwróć po polsku:
1. Co to za produkt
2. Marka
3. Typ / fason
4. Kolor
5. Rozmiar
6. Kody z metek / EAN / SKU / numery modelu
7. Materiał, jeśli widoczny
8. Cechy produktu
9. Gotowe frazy do wyszukania produktu online
10. Propozycja tytułu aukcji Allegro

Nie wymyślaj danych. Jeśli czegoś nie widać, napisz: brak pewnych danych.
"""
    try:
        response = model.generate_content([prompt, *images])
        return response.text
    except Exception as exc:
        return f"Nie udało się połączyć z Gemini API. Szczegóły: {exc}"


def build_listing_prompt() -> str:
    return f"""
Przygotuj profesjonalny opis aukcji Allegro po polsku.

Dane:
Nazwa: {st.session_state.product_name}
Marka: {st.session_state.brand}
Kategoria: {st.session_state.category}
Stan: {st.session_state.condition}
Rozmiar: {st.session_state.size}
Kolor: {st.session_state.color}
Kod: {st.session_state.code}
Cena: {st.session_state.price}
Cechy: {st.session_state.features}
Notatki: {st.session_state.manual_notes}

Zasady:
- nie wymyślaj danych technicznych
- opis ma być uczciwy i sprzedażowy
- użyj prostego HTML do Allegro
- dodaj sekcje: Najważniejsze cechy, Opis produktu, Informacje o ofercie, Słowa kluczowe SEO
"""


def generate_description_openai() -> str:
    if st.session_state.dry_run:
        return build_manual_description() + "\n\n<p><em>TRYB TESTOWY — tu pojawiłby się opis wygenerowany przez OpenAI.</em></p>"

    api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not api_key:
        return "Brak OPENAI_API_KEY w Streamlit Secrets."
    if OpenAI is None:
        return "Brak biblioteki openai. Sprawdź requirements.txt."

    client = OpenAI(api_key=api_key)
    try:
        response = client.responses.create(model="gpt-4.1-mini", input=build_listing_prompt())
        return response.output_text
    except Exception as exc:
        return f"Nie udało się połączyć z OpenAI API. Szczegóły: {exc}"


def generate_description_gemini() -> str:
    if st.session_state.dry_run:
        return build_manual_description() + "\n\n<p><em>TRYB TESTOWY — tu pojawiłby się opis wygenerowany przez Gemini.</em></p>"

    model, error = get_gemini_model()
    if error:
        return f"Nie udało się połączyć z Gemini API. Szczegóły: {error}"

    try:
        response = model.generate_content(build_listing_prompt())
        return response.text
    except Exception as exc:
        return f"Nie udało się połączyć z Gemini API. Szczegóły: {exc}"


# -----------------------------
# App
# -----------------------------
require_login()
st.set_page_config(page_title="AI Sprzedawca Allegro — MVP", layout="wide")
init_state()

st.title("AI Sprzedawca Allegro — MVP")
st.caption("Rozpoznawanie produktów, magazyn, opisy aukcji i szablony.")

with st.sidebar:
    st.header("Ustawienia")
    st.write(f"Zalogowano jako: **{st.session_state.get('username', '')}**")
    if st.button("🚪 Wyloguj", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

    st.divider()
    st.checkbox("Tryb testowy bez używania API", key="dry_run")
    st.info("W trybie testowym przyciski AI działają 'na sucho' i nie zużywają limitów API.")

tab1, tab_inventory, tab_listed, tab_image_search, tab2, tab3 = st.tabs(
    [
        "1️⃣ Rozpoznawanie zdjęć",
        "📦 Magazyn / Asortyment",
        "🛒 Wystawione aukcje",
        "🤖 AI wyszukiwanie zdjęć",
        "2️⃣ Opis i wzór aukcji",
        "3️⃣ Zapisane szablony",
    ]
)


# -----------------------------
# TAB 1
# -----------------------------
with tab1:
    st.subheader("Rozpoznawanie produktu ze zdjęć")

    uploaded_files = st.file_uploader(
        "Dodaj zdjęcia produktu i metek",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
    )

    images: List[Image.Image] = []
    if uploaded_files:
        cols = st.columns(3)
        for idx, file in enumerate(uploaded_files):
            image = Image.open(file).convert("RGB")
            images.append(image)
            with cols[idx % 3]:
                st.image(image, caption=file.name, use_container_width=True)

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("🔎 Rozpoznaj produkt ze zdjęć", use_container_width=True):
            if not images:
                st.warning("Dodaj przynajmniej jedno zdjęcie.")
            else:
                with st.spinner("Analizuję zdjęcia..."):
                    st.session_state.recognized_text = recognize_with_gemini(images)

    with col_b:
        if st.button("➡️ Przenieś wynik do danych aukcji", use_container_width=True):
            sync_recognition_to_auction()
            st.success("Przeniesiono wynik do notatek/cech aukcji.")

    st.text_area("Wynik rozpoznania", key="recognized_text", height=360)
    st.text_area(
        "Frazy / notatki do wyszukiwania produktu online",
        key="recognized_search_phrases",
        height=140,
        placeholder="Np. marka + kod z metki + kolor + typ produktu...",
    )


# -----------------------------
# TAB INVENTORY
# -----------------------------
with tab_inventory:
    st.subheader("Magazyn / Asortyment")
    st.caption("Prosty rejestr produktów: lokalizacja, status, koszt, cena, marża.")

    inventory = load_inventory()

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    total_items = sum(int(item.get("quantity", 0) or 0) for item in inventory)
    total_cost = sum(float(item.get("purchase_cost", 0.0) or 0.0) * int(item.get("quantity", 0) or 0) for item in inventory)
    potential_sales = sum(float(item.get("sale_price", 0.0) or 0.0) * int(item.get("quantity", 0) or 0) for item in inventory)
    potential_margin = potential_sales - total_cost

    metric_col1.metric("Pozycje", len(inventory))
    metric_col2.metric("Sztuki", total_items)
    metric_col3.metric("Koszt zakupu", f"{total_cost:.2f} zł")
    metric_col4.metric("Potencjalna marża", f"{potential_margin:.2f} zł")

    st.divider()

    with st.expander("⬆️ Import asortymentu z pliku CSV Allegro", expanded=False):
        st.write("Wgraj eksport z Allegro z kolumnami typu: offer_id, name, status, gtin, stock, price@allegro-pl, url.")
        allegro_csv = st.file_uploader(
            "Plik CSV z Allegro",
            type=["csv"],
            key="allegro_csv_import",
        )
        overwrite_existing = st.checkbox(
            "Aktualizuj istniejące pozycje o tym samym offer_id",
            value=True,
            key="overwrite_allegro_import",
        )

        if allegro_csv is not None:
            try:
                preview_df = pd.read_csv(allegro_csv, dtype=str)
            except Exception:
                allegro_csv.seek(0)
                preview_df = pd.read_csv(allegro_csv, sep=";", dtype=str)
            allegro_csv.seek(0)

            st.caption(f"Wykryto {len(preview_df)} wierszy i {len(preview_df.columns)} kolumn.")
            st.dataframe(preview_df.head(10), use_container_width=True)

            if st.button("📥 Importuj do magazynu", use_container_width=True):
                result = import_allegro_csv(allegro_csv, overwrite_existing=overwrite_existing)
                st.success(
                    f"Import zakończony. Nowe: {result['imported']}, zaktualizowane: {result['updated']}, pominięte: {result['skipped']}."
                )
                st.rerun()

    st.divider()

    with st.expander("➕ Dodaj / edytuj produkt w magazynie", expanded=True):
        form_col1, form_col2, form_col3 = st.columns(3)

        with form_col1:
            st.text_input("ID produktu", key="inv_id", placeholder="Automatyczne, jeśli puste")
            st.text_input("Nazwa produktu", key="inv_product_name")
            st.text_input("Marka", key="inv_brand")
            st.text_input("Kategoria", key="inv_category")
            st.selectbox("Stan", ["Nowy", "Używany", "Po zwrocie", "Powystawowy"], key="inv_condition")

        with form_col2:
            st.text_input("Rozmiar", key="inv_size")
            st.text_input("Kolor", key="inv_color")
            st.text_input("Kod produktu / EAN / SKU", key="inv_code")
            st.number_input("Ilość", min_value=1, step=1, key="inv_quantity")
            st.text_input("Lokalizacja", key="inv_location", placeholder="Np. Karton A1 / Worek B3 / Półka C2")

        with form_col3:
            st.selectbox(
                "Status",
                ["Do identyfikacji", "Do wystawienia", "Wystawione", "Sprzedane", "Wysłane", "Zwrot", "Archiwum"],
                key="inv_status",
            )
            st.number_input("Koszt zakupu / szt.", min_value=0.0, step=1.0, key="inv_purchase_cost")
            st.number_input("Cena sprzedaży / szt.", min_value=0.0, step=1.0, key="inv_sale_price")
            st.text_area("Linki do zdjęć", key="inv_image_urls", height=80)
            st.text_area("Notatki", key="inv_notes", height=80)

        btn1, btn2, btn3 = st.columns(3)

        with btn1:
            if st.button("💾 Zapisz produkt w magazynie", use_container_width=True):
                payload = inventory_payload_from_form(inventory)
                inventory = [item for item in inventory if item.get("id") != payload["id"]]
                inventory.append(payload)
                save_inventory(inventory)
                st.success(f"Zapisano produkt: {payload['id']}")
                st.rerun()

        with btn2:
            if st.button("🧹 Wyczyść formularz magazynu", use_container_width=True):
                clear_inventory_form()
                st.rerun()

        with btn3:
            if st.button("➡️ Przenieś z formularza do aukcji", use_container_width=True):
                payload = inventory_payload_from_form(inventory)
                load_inventory_item_to_auction(payload)
                st.success("Przeniesiono produkt do zakładki opisu aukcji.")

    st.divider()
    st.subheader("Lista asortymentu")

    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        status_filter = st.selectbox(
            "Filtr statusu",
            ["Wszystkie", "Do identyfikacji", "Do wystawienia", "Wystawione", "Sprzedane", "Wysłane", "Zwrot", "Archiwum"],
        )
    with filter_col2:
        search_query = st.text_input("Szukaj", placeholder="Marka, nazwa, kod, lokalizacja...")
    with filter_col3:
        st.write("")
        st.write("")
        if st.button("🔄 Odśwież listę", use_container_width=True):
            st.rerun()

    filtered = inventory
    if status_filter != "Wszystkie":
        filtered = [item for item in filtered if item.get("status") == status_filter]
    if search_query.strip():
        q = search_query.lower().strip()
        filtered = [
            item for item in filtered
            if q in " ".join(str(item.get(k, "")) for k in ["id", "product_name", "brand", "category", "size", "color", "code", "location", "status", "offer_id", "allegro_url", "external_id"]).lower()
        ]

    if not filtered:
        st.info("Brak produktów dla wybranych filtrów.")
    else:
        for item in reversed(filtered):
            margin = float(item.get("sale_price", 0.0) or 0.0) - float(item.get("purchase_cost", 0.0) or 0.0)
            with st.container(border=True):
                header_col1, header_col2, header_col3 = st.columns([2, 1, 1])
                with header_col1:
                    st.markdown(f"**{item.get('brand', '')} {item.get('product_name', '')}**")
                    st.caption(f"ID: {item.get('id')} | Kod: {item.get('code', '')} | Dodano: {item.get('created_at', '')}")
                    if item.get("allegro_url"):
                        st.markdown(f"[Otwórz ofertę Allegro]({item.get('allegro_url')})")
                with header_col2:
                    st.write(f"**Status:** {item.get('status', '')}")
                    st.write(f"**Lokalizacja:** {item.get('location', '')}")
                with header_col3:
                    st.write(f"**Cena:** {float(item.get('sale_price', 0.0) or 0.0):.2f} zł")
                    st.write(f"**Marża/szt.:** {margin:.2f} zł")

                detail_col1, detail_col2, detail_col3, detail_col4 = st.columns(4)
                detail_col1.write(f"Rozmiar: **{item.get('size', '')}**")
                detail_col2.write(f"Kolor: **{item.get('color', '')}**")
                detail_col3.write(f"Ilość: **{item.get('quantity', '')}**")
                detail_col4.write(f"Koszt/szt.: **{float(item.get('purchase_cost', 0.0) or 0.0):.2f} zł**")

                if item.get("notes"):
                    st.caption(item.get("notes"))

                action_col1, action_col2, action_col3, action_col4, action_col5 = st.columns(5)

                with action_col1:
                    if st.button("✏️ Edytuj", key=f"edit_{item.get('id')}", use_container_width=True):
                        load_inventory_item_to_form(item)
                        st.success("Wczytano do formularza powyżej.")
                        st.rerun()

                with action_col2:
                    if st.button("➡️ Do aukcji", key=f"auction_{item.get('id')}", use_container_width=True):
                        load_inventory_item_to_auction(item)
                        st.success("Przeniesiono do zakładki opisu aukcji.")
                        st.rerun()

                with action_col3:
                    if st.button("🛒 Wystawione", key=f"listed_{item.get('id')}", use_container_width=True):
                        update_inventory_status(item.get("id", ""), "Wystawione")
                        st.rerun()

                with action_col4:
                    if st.button("✅ Sprzedane", key=f"sold_{item.get('id')}", use_container_width=True):
                        update_inventory_status(item.get("id", ""), "Sprzedane")
                        st.rerun()

                with action_col5:
                    if st.button("🗑️ Usuń", key=f"delete_{item.get('id')}", use_container_width=True):
                        inventory = [x for x in load_inventory() if x.get("id") != item.get("id")]
                        save_inventory(inventory)
                        st.success("Usunięto produkt.")
                        st.rerun()

    st.download_button(
        "⬇️ Pobierz magazyn jako JSON",
        json.dumps(load_inventory(), ensure_ascii=False, indent=2),
        file_name="magazyn_asortyment.json",
        mime="application/json",
    )


# -----------------------------
# TAB LISTED AUCTIONS
# -----------------------------
with tab_listed:
    st.subheader("Wystawione aukcje")
    st.caption("Panel kontroli ofert: wystawione, sprzedane, wysłane i do ponownego wystawienia.")

    inventory = load_inventory()
    auction_items = [
        item for item in inventory
        if item.get("status") in ["Wystawione", "Sprzedane", "Wysłane", "Zwrot"] or item.get("allegro_url") or item.get("offer_id")
    ]

    listed_count = sum(1 for item in auction_items if item.get("status") == "Wystawione")
    sold_count = sum(1 for item in auction_items if item.get("status") == "Sprzedane")
    shipped_count = sum(1 for item in auction_items if item.get("status") == "Wysłane")
    listed_value = sum(float(item.get("sale_price", 0.0) or 0.0) * int(item.get("quantity", 0) or 0) for item in auction_items if item.get("status") == "Wystawione")

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("Wystawione", listed_count)
    metric_col2.metric("Sprzedane", sold_count)
    metric_col3.metric("Wysłane", shipped_count)
    metric_col4.metric("Wartość wystawionych", f"{listed_value:.2f} zł")

    st.divider()

    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        auction_status_filter = st.selectbox(
            "Status aukcji",
            ["Wszystkie", "Wystawione", "Sprzedane", "Wysłane", "Zwrot"],
            key="auction_status_filter",
        )
    with filter_col2:
        auction_search = st.text_input(
            "Szukaj aukcji",
            placeholder="Nazwa, marka, kod, offer_id...",
            key="auction_search",
        )
    with filter_col3:
        st.write("")
        st.write("")
        if st.button("🔄 Odśwież aukcje", use_container_width=True):
            st.rerun()

    filtered_auctions = auction_items
    if auction_status_filter != "Wszystkie":
        filtered_auctions = [item for item in filtered_auctions if item.get("status") == auction_status_filter]
    if auction_search.strip():
        q = auction_search.lower().strip()
        filtered_auctions = [
            item for item in filtered_auctions
            if q in " ".join(str(item.get(k, "")) for k in ["id", "product_name", "brand", "category", "size", "color", "code", "offer_id", "allegro_url", "status"]).lower()
        ]

    if not filtered_auctions:
        st.info("Brak aukcji dla wybranych filtrów.")
    else:
        for item in reversed(filtered_auctions):
            item_id = item.get("id", "")
            sale_price = float(item.get("sale_price", 0.0) or 0.0)
            purchase_cost = float(item.get("purchase_cost", 0.0) or 0.0)
            quantity = int(item.get("quantity", 0) or 0)
            margin_total = (sale_price - purchase_cost) * quantity

            with st.container(border=True):
                header_col1, header_col2, header_col3 = st.columns([2, 1, 1])

                with header_col1:
                    st.markdown(f"**{item.get('brand', '')} {item.get('product_name', '')}**")
                    st.caption(f"ID: {item_id} | Allegro offer_id: {item.get('offer_id', 'brak')} | Kod: {item.get('code', '')}")
                    if item.get("allegro_url"):
                        st.markdown(f"[🔗 Otwórz ofertę Allegro]({item.get('allegro_url')})")

                with header_col2:
                    st.write(f"**Status:** {item.get('status', '')}")
                    st.write(f"**Ilość:** {quantity}")
                    st.write(f"**Lokalizacja:** {item.get('location', '')}")

                with header_col3:
                    st.write(f"**Cena:** {sale_price:.2f} zł")
                    st.write(f"**Marża razem:** {margin_total:.2f} zł")

                detail_col1, detail_col2, detail_col3, detail_col4 = st.columns(4)
                detail_col1.write(f"Rozmiar: **{item.get('size', '')}**")
                detail_col2.write(f"Kolor: **{item.get('color', '')}**")
                detail_col3.write(f"Stan: **{item.get('condition', '')}**")
                detail_col4.write(f"Kategoria: **{item.get('category', '')}**")

                if item.get("notes"):
                    st.caption(item.get("notes"))

                action_col1, action_col2, action_col3, action_col4, action_col5 = st.columns(5)

                with action_col1:
                    if st.button("✅ Sprzedane", key=f"listed_sold_{item_id}", use_container_width=True):
                        update_inventory_status(item_id, "Sprzedane")
                        st.rerun()

                with action_col2:
                    if st.button("📦 Wysłane", key=f"listed_shipped_{item_id}", use_container_width=True):
                        update_inventory_status(item_id, "Wysłane")
                        st.rerun()

                with action_col3:
                    if st.button("♻️ Wystawione", key=f"listed_back_{item_id}", use_container_width=True):
                        update_inventory_status(item_id, "Wystawione")
                        st.rerun()

                with action_col4:
                    if st.button("✏️ Edytuj w magazynie", key=f"listed_edit_{item_id}", use_container_width=True):
                        load_inventory_item_to_form(item)
                        st.success("Wczytano aukcję do formularza magazynu. Przejdź do zakładki Magazyn / Asortyment.")
                        st.rerun()

                with action_col5:
                    if st.button("➡️ Do opisu", key=f"listed_to_desc_{item_id}", use_container_width=True):
                        load_inventory_item_to_auction(item)
                        st.success("Przeniesiono aukcję do zakładki opisu aukcji.")
                        st.rerun()

    st.download_button(
        "⬇️ Pobierz wystawione aukcje jako JSON",
        json.dumps(auction_items, ensure_ascii=False, indent=2),
        file_name="wystawione_aukcje.json",
        mime="application/json",
    )



# -----------------------------
# TAB IMAGE SEARCH
# -----------------------------
with tab_image_search:
    st.subheader("AI wyszukiwanie zdjęć / podobnych produktów")
    st.caption(
        "Wgraj zdjęcie produktu lub metki. Aplikacja wyszuka podobne produkty w Google Lens przez SerpApi."
    )

    st.warning(
        "Uwaga: wyniki z internetu służą głównie do identyfikacji produktu. Przed użyciem zdjęć w aukcji upewnij się, że masz prawo ich używać."
    )

    if st.session_state.dry_run:
        st.info("Masz włączony tryb testowy. Wyszukiwanie pokaże przykładowe wyniki i nie użyje SerpApi.")

    search_col1, search_col2 = st.columns([1, 1])

    with search_col1:
        lens_files = st.file_uploader(
            "Dodaj zdjęcia do wyszukania",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="lens_files",
        )

        lens_query = st.text_input(
            "Dodatkowa fraza zawężająca",
            placeholder="Np. Triumph biustonosz 75B czarny / kod z metki",
            key="lens_query",
        )

        country = st.selectbox(
            "Rynek wyszukiwania",
            ["pl", "de", "uk", "us", "fr", "it", "es"],
            index=0,
            help="pl = Polska, de = Niemcy, uk = Wielka Brytania itd.",
        )

        result_limit = st.slider("Liczba wyników", min_value=4, max_value=24, value=12, step=4)

        run_lens = st.button("🔍 Szukaj podobnych produktów/zdjęć", use_container_width=True)

    images_for_search: List[Image.Image] = []
    if lens_files:
        preview_cols = st.columns(4)
        for idx, file in enumerate(lens_files):
            img = Image.open(file).convert("RGB")
            images_for_search.append(img)
            with preview_cols[idx % 4]:
                st.image(img, caption=file.name, use_container_width=True)

    if run_lens:
        if not images_for_search:
            st.warning("Dodaj przynajmniej jedno zdjęcie.")
        elif st.session_state.dry_run:
            st.session_state.lens_results = [
                {
                    "title": "TRYB TESTOWY — przykładowy podobny produkt",
                    "source": "example.com",
                    "link": "https://example.com/produkt",
                    "thumbnail": "",
                    "price": "99,99 zł",
                    "rating": "",
                    "in_stock": "unknown",
                },
                {
                    "title": "TRYB TESTOWY — przykładowe dopasowanie z Google Lens",
                    "source": "example-shop.com",
                    "link": "https://example-shop.com/podobny-produkt",
                    "thumbnail": "",
                    "price": "",
                    "rating": "",
                    "in_stock": "unknown",
                },
            ]
            st.success("Tryb testowy: wygenerowano przykładowe wyniki.")
        else:
            all_results: List[Dict[str, Any]] = []
            with st.spinner("Szukam podobnych produktów w sieci..."):
                # Na start używamy pierwszego zdjęcia, bo każde wyszukiwanie to osobny koszt/limit.
                search_result = search_google_lens_serpapi(
                    images_for_search[0],
                    query=lens_query,
                    country=country,
                    limit=result_limit,
                )

            if search_result.get("error"):
                st.error(search_result["error"])
            else:
                all_results = search_result.get("results", [])
                st.session_state.lens_results = all_results
                st.success(f"Znaleziono wyników: {len(all_results)}")

    results = st.session_state.get("lens_results", [])

    if results:
        st.divider()
        st.subheader("Znalezione dopasowania")

        for idx, item in enumerate(results):
            with st.container(border=True):
                cols = st.columns([1, 3, 1])

                with cols[0]:
                    if item.get("thumbnail"):
                        st.image(item.get("thumbnail"), use_container_width=True)
                    else:
                        st.write("Brak miniatury")

                with cols[1]:
                    st.markdown(f"**{item.get('title') or 'Brak tytułu'}**")
                    st.write(f"Źródło: {item.get('source') or 'brak'}")
                    if item.get("price"):
                        st.write(f"Cena: {item.get('price')}")
                    if item.get("link"):
                        st.link_button("Otwórz wynik", item.get("link"), use_container_width=False)

                with cols[2]:
                    if st.button("➕ Dodaj link do aukcji", key=f"add_lens_link_{idx}", use_container_width=True):
                        append_image_link_to_auction(item.get("thumbnail") or item.get("link") or "")
                        st.success("Dodano link do pola 'Linki do zdjęć' w zakładce opisu.")

                    if st.button("📝 Użyj tytułu", key=f"use_lens_title_{idx}", use_container_width=True):
                        st.session_state.title = (item.get("title") or "")[:75]
                        st.success("Przeniesiono tytuł do szkicu aukcji.")

                    if st.button("🧾 Dodaj do notatek", key=f"note_lens_{idx}", use_container_width=True):
                        note = f"{item.get('title', '')} | {item.get('source', '')} | {item.get('link', '')}"
                        current = st.session_state.get("manual_notes", "")
                        st.session_state.manual_notes = (current + "\n" + note).strip()
                        st.success("Dodano do notatek aukcji.")

        st.download_button(
            "⬇️ Pobierz wyniki jako JSON",
            json.dumps(results, ensure_ascii=False, indent=2),
            file_name="wyniki_wyszukiwania_zdjec.json",
            mime="application/json",
        )


# -----------------------------
# TAB 2
# -----------------------------
with tab2:
    st.subheader("Dane aukcji")

    top_col1, top_col2, top_col3 = st.columns(3)

    with top_col1:
        if st.button("🧹 Wyczyść dane aukcji", use_container_width=True):
            reset_auction_data()
            st.rerun()

    with top_col2:
        if st.button("🧽 Wyczyść gotowy szkic", use_container_width=True):
            reset_description_only()
            st.rerun()

    with top_col3:
        if st.button("📝 Wprowadź ręcznie / odśwież wzór", use_container_width=True):
            st.session_state.description = build_manual_description()
            if not st.session_state.title:
                title_parts = [st.session_state.brand, st.session_state.product_name, st.session_state.size, st.session_state.color]
                st.session_state.title = " ".join([x for x in title_parts if x]).strip()
            st.success("Utworzono ręczny wzór opisu.")

    if st.session_state.loaded_template_name:
        st.success(f"Obecnie wczytany szablon: {st.session_state.loaded_template_name}")

    if st.session_state.inventory_loaded_item:
        st.info(f"Produkt przeniesiony z magazynu: {st.session_state.inventory_loaded_item}")

    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Nazwa produktu", key="product_name")
        st.text_input("Marka", key="brand")
        st.text_input("Kategoria", key="category")
        st.selectbox("Stan", ["Nowy", "Używany", "Po zwrocie", "Powystawowy"], key="condition")
        st.text_input("Rozmiar", key="size")
        st.text_input("Kolor", key="color")

    with col2:
        st.text_input("Kod produktu / EAN / SKU", key="code")
        st.number_input("Cena brutto", min_value=0.0, step=1.0, key="price")
        st.number_input("Liczba sztuk", min_value=1, step=1, key="stock")
        st.text_area("Cechy / parametry", key="features", height=120)
        st.text_area("Linki do zdjęć", key="image_urls", height=120)

    st.text_area("Notatki ręczne / wynik rozpoznania", key="manual_notes", height=160)

    st.divider()
    st.subheader("Gotowy szkic do edycji")

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("🤖 Opis AI — OpenAI", use_container_width=True):
            with st.spinner("Generuję opis przez OpenAI..."):
                st.session_state.description = generate_description_openai()

    with btn_col2:
        if st.button("🤖 Opis AI — Gemini", use_container_width=True):
            with st.spinner("Generuję opis przez Gemini..."):
                st.session_state.description = generate_description_gemini()

    st.text_input("Tytuł aukcji", key="title", max_chars=75)
    st.text_area("Opis HTML do wklejenia/poprawy", key="description", height=460)

    st.markdown("### Podgląd")
    st.markdown(st.session_state.description or "_Brak opisu_", unsafe_allow_html=True)

    st.divider()
    st.subheader("Zapisz szkic jako szablon")

    save_col1, save_col2 = st.columns([2, 1])
    with save_col1:
        template_name = st.text_input("Nazwa szablonu", placeholder="Np. Biustonosz czarny Triumph 75B")
    with save_col2:
        st.write("")
        st.write("")
        if st.button("💾 Zapisz szablon", use_container_width=True):
            save_current_template(template_name)

    st.download_button(
        "⬇️ Pobierz opis jako HTML",
        st.session_state.description or "",
        file_name="opis_aukcji.html",
        mime="text/html",
    )


# -----------------------------
# TAB 3
# -----------------------------
with tab3:
    st.subheader("Zapisane szablony")

    templates = load_templates()
    if not templates:
        st.info("Nie masz jeszcze zapisanych szablonów.")
    else:
        names = [tpl.get("name", "Bez nazwy") for tpl in templates]
        selected_name = st.selectbox("Wybierz szablon", names)
        selected_template = next((tpl for tpl in templates if tpl.get("name") == selected_name), None)

        if selected_template:
            st.caption(f"Utworzono: {selected_template.get('created_at', 'brak daty')}")

            col_load, col_delete = st.columns(2)

            with col_load:
                if st.button("📥 Wczytaj wybrany szablon do edycji", use_container_width=True):
                    load_template_into_state(selected_template)
                    st.success(f"Wczytano szablon: {selected_name}. Przejdź do zakładki 'Opis i wzór aukcji'.")
                    st.rerun()

            with col_delete:
                if st.button("🗑️ Usuń wybrany szablon", use_container_width=True):
                    delete_template(selected_name)
                    st.success(f"Usunięto szablon: {selected_name}")
                    st.rerun()

            data = selected_template.get("data", {})

            st.markdown("### Podgląd danych")
            st.write(f"**Tytuł:** {data.get('title', '')}")
            st.write(f"**Produkt:** {data.get('product_name', '')}")
            st.write(f"**Marka:** {data.get('brand', '')}")
            st.write(f"**Rozmiar:** {data.get('size', '')}")
            st.write(f"**Kolor:** {data.get('color', '')}")

            st.markdown("### Podgląd opisu")
            st.markdown(data.get("description", "") or "_Brak opisu_", unsafe_allow_html=True)

            st.download_button(
                "⬇️ Pobierz ten szablon jako JSON",
                json.dumps(selected_template, ensure_ascii=False, indent=2),
                file_name=f"{selected_name}.json",
                mime="application/json",
            )
