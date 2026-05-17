from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st
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



# -----------------------------
# Helpers: simple login
# -----------------------------
def check_login() -> bool:
    """Simple password gate for Streamlit Cloud.

    Add this to Streamlit Secrets:

    APP_USERS = {"michal" = "your_password", "wspolniczka" = "her_password"}
    """
    users = st.secrets.get("APP_USERS", {})

    if not users:
        st.error("Brak skonfigurowanych użytkowników. Dodaj APP_USERS w Streamlit Secrets.")
        st.stop()

    if st.session_state.get("authenticated"):
        return True

    st.title("🔒 Logowanie")
    st.caption("Dostęp tylko dla uprawnionych użytkowników.")

    with st.form("login_form"):
        username = st.text_input("Login")
        password = st.text_input("Hasło", type="password")
        submitted = st.form_submit_button("Zaloguj")

    if submitted:
        expected_password = users.get(username)
        if expected_password and password == expected_password:
            st.session_state.authenticated = True
            st.session_state.username = username
            st.success("Zalogowano poprawnie.")
            st.rerun()
        else:
            st.error("Nieprawidłowy login lub hasło.")

    st.stop()


def logout_button() -> None:
    username = st.session_state.get("username", "")
    if username:
        st.sidebar.success(f"Zalogowano jako: {username}")
    if st.sidebar.button("🚪 Wyloguj"):
        st.session_state.authenticated = False
        st.session_state.username = ""
        st.rerun()


def init_state() -> None:
    for key, value in DEFAULT_AUCTION_DATA.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if "recognized_text" not in st.session_state:
        st.session_state.recognized_text = ""
    if "recognized_search_phrases" not in st.session_state:
        st.session_state.recognized_search_phrases = ""
    if "dry_run" not in st.session_state:
        st.session_state.dry_run = True
    if "loaded_template_name" not in st.session_state:
        st.session_state.loaded_template_name = ""


def reset_auction_data() -> None:
    for key, value in DEFAULT_AUCTION_DATA.items():
        st.session_state[key] = value
    st.session_state.recognized_text = ""
    st.session_state.recognized_search_phrases = ""
    st.session_state.loaded_template_name = ""


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


def load_templates() -> List[Dict[str, Any]]:
    if not TEMPLATES_FILE.exists():
        return []
    try:
        return json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_templates(templates: List[Dict[str, Any]]) -> None:
    TEMPLATES_FILE.write_text(json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8")


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


def generate_description_openai() -> str:
    if st.session_state.dry_run:
        return build_manual_description() + "\n\n<p><em>TRYB TESTOWY — tu pojawiłby się opis wygenerowany przez OpenAI.</em></p>"

    api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not api_key:
        return "Brak OPENAI_API_KEY w Streamlit Secrets."
    if OpenAI is None:
        return "Brak biblioteki openai. Sprawdź requirements.txt."

    client = OpenAI(api_key=api_key)
    prompt = build_listing_prompt()

    try:
        response = client.responses.create(model="gpt-4.1-mini", input=prompt)
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


st.set_page_config(page_title="AI Sprzedawca Allegro — MVP", layout="wide")
check_login()
init_state()
logout_button()

st.title("AI Sprzedawca Allegro — MVP")
st.caption("Rozpoznawanie produktów, przygotowanie opisu aukcji i zapisywanie szablonów.")

with st.sidebar:
    st.header("Ustawienia")
    st.checkbox("Tryb testowy bez używania API", key="dry_run")
    st.info("W trybie testowym przyciski AI działają 'na sucho' i nie zużywają limitów API.")

tab1, tab2, tab3 = st.tabs(["1️⃣ Rozpoznawanie zdjęć", "2️⃣ Opis i wzór aukcji", "3️⃣ Zapisane szablony"])


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
                title_parts = [
                    st.session_state.brand,
                    st.session_state.product_name,
                    st.session_state.size,
                    st.session_state.color,
                ]
                st.session_state.title = " ".join([x for x in title_parts if x]).strip()
            st.success("Utworzono ręczny wzór opisu.")

    if st.session_state.loaded_template_name:
        st.success(f"Obecnie wczytany szablon: {st.session_state.loaded_template_name}")

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
