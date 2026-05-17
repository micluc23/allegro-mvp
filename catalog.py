from __future__ import annotations
import os
from dataclasses import dataclass, asdict
from typing import Optional, List
import pandas as pd
import requests


@dataclass
class Product:
    code: str = ""
    ean: str = ""
    sku: str = ""
    name: str = ""
    brand: str = ""
    category: str = ""
    price: float = 0.0
    condition: str = "Nowy"
    stock: int = 1
    features: str = ""
    image_urls: str = ""

    def to_dict(self):
        return asdict(self)


def load_local_catalog(path: str = "sample_products.csv") -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=list(Product().to_dict().keys()))
    return pd.read_csv(path, dtype={"code": str, "ean": str, "sku": str}).fillna("")


def find_local_product(code: str, path: str = "sample_products.csv") -> Optional[Product]:
    df = load_local_catalog(path)
    if df.empty or not code:
        return None
    code_norm = str(code).strip()
    mask = (df["code"].astype(str) == code_norm) | (df["ean"].astype(str) == code_norm) | (df["sku"].astype(str).str.upper() == code_norm.upper())
    rows = df[mask]
    if rows.empty:
        return None
    data = rows.iloc[0].to_dict()
    return Product(**{k: data.get(k, "") for k in Product().to_dict().keys()})


def search_allegro_product_catalog(code: str, access_token: str | None = None) -> Optional[dict]:
    """Optional proof-of-concept Allegro Product Catalog lookup.

    This intentionally does not publish offers. It only tries to search products.
    Requires a valid Allegro OAuth access token.
    """
    token = access_token or os.getenv("ALLEGRO_ACCESS_TOKEN")
    if not token or not code:
        return None

    url = "https://api.allegro.pl/sale/products"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.allegro.public.v1+json",
        "User-Agent": "allegro-mvp-listing-generator/0.1",
    }
    params = {"phrase": code, "limit": 1}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        products = data.get("products", [])
        return products[0] if products else None
    except Exception:
        return None


def product_from_allegro(raw: dict, code: str) -> Product:
    if not raw:
        return Product(code=code, ean=code)
    name = raw.get("name", "")
    category = raw.get("category", {}).get("name", "") if isinstance(raw.get("category"), dict) else ""
    images = raw.get("images", []) or []
    image_urls = ";".join([img.get("url", "") for img in images if isinstance(img, dict)])
    parameters = raw.get("parameters", []) or []
    features = "; ".join([f"{p.get('name')}: {', '.join([str(v) for v in p.get('values', [])])}" for p in parameters[:8] if isinstance(p, dict)])
    return Product(code=code, ean=code if code.isdigit() else "", name=name, category=category, features=features, image_urls=image_urls)


def image_url_list(product: Product) -> List[str]:
    if not product.image_urls:
        return []
    return [x.strip() for x in str(product.image_urls).replace(",", ";").split(";") if x.strip()]
