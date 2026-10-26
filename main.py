"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. Each function in trendyol/api.py matches one endpoint.
"""
import json
import os

from trendyol.api import product_details, products_search, rankings_products

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a product id or any trendyol.com product link
    save("product_905790695.json", product_details(product="905790695", country="TR"))

    # 36 products per page, with brand / category / price / sort filters
    save("search_airpods.json", products_search(query="airpods", sort=None, min_price=None, max_price=None,
                                                page=1, country="TR", brand=None, category=None))

    # the top 100 best-sellers of a category, 20 per page
    save("best_sellers_electronics.json", rankings_products(category="104024", type="bestSeller", gender=1,
                                                            page=1, country="TR"))
