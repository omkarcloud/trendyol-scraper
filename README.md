# 🛍️ Trendyol Scraper

Trendyol Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Trendyol data for free.

## ✨ What Can I Get?

- 🛍️ **Full details on any Trendyol product** — price, stock, sizes, 30+ specs & every seller's offer
- 🔍 **Search & browse 1,100+ categories** — filter by brand, price and sort, with every filter facet
- ⭐ **Every review & buyer question** — photos, sizes & fit, rating breakdown, AI summary & seller answers
- 🏆 **4,000+ best-seller lists & full store profiles** — top 100 per category, store scores, followers & reviews

## 🎥 Example: A Full Trendyol Product

```json
{
  "id": 905790695,
  "name": "Pole Star Top İnci Mine Detaylı Üçlü Kombin Kolye",
  "link": "https://www.trendyol.com/magicstone/pole-star-top-inci-mine-detayli-uclu-kombin-kolye-p-905790695",
  "brand": { "id": 1008201, "name": "MagicStone" },
  "category": { "id": 103546, "name": "Bijuteri Kolye", "hierarchy": "Aksesuar/Takı & Mücevher/Kolye/Bijuteri Kolye" },
  "gender": "Kadın",
  "images": ["https://cdn.dsmcdn.com/ty1648/prod/QC/20250310/17/b3a343e8-be2c-3cfd-bd9b-c7a18775456f/1_org_zoom.jpg"],
  "price": { "current": 139, "original": 139, "discount_rate": null, "currency": "TRY" },
  "rating": { "average": 4.36, "count": 3302, "comment_count": 1840 },
  "favorite_count": 247400,
  "is_in_stock": true,
  "stock": { "is_running_out": false, "max_sale_limit": 10, "is_sellable": true },
  "rush_delivery_hours": 24,
  "variants": [
    { "item_number": 1262050948, "value": "45 cm", "barcode": "KL20576", "is_in_stock": true, "price": 149 }
  ],
  "attributes": [
    { "name": "Materyal", "value": "Lak Kaplama", "is_highlighted": true },
    { "name": "Taş Cinsi", "value": "İnci", "is_highlighted": true }
  ],
  "merchant": { "id": 207811, "name": "MagicStoneTakı", "score": 9.5, "city": "İstanbul", "is_cash_on_delivery_eligible": true },
  "promotions": [
    { "id": 29034114, "name": "4 Al 3 Öde", "type": "TwoForOne", "end_date": "2026-12-31" }
  ],
  "top_rankings": [{ "type": "bestSeller", "rank": 1 }],
  "description": "Kararmaya karşı özel kaplama kullanılmıştır.\nKombinimiz birleşik değildir. Ayrı ayrı da kullanılabilir.\nBoyut:40,45 cm."
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Trendyol Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/trendyol-scraper
cd trendyol-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/products/details?product=905790695"
```

```json
{
  "id": 905790695,
  "name": "Pole Star Top İnci Mine Detaylı Üçlü Kombin Kolye",
  "link": "https://www.trendyol.com/magicstone/pole-star-top-inci-mine-detayli-uclu-kombin-kolye-p-905790695",
  "brand": { "id": 1008201, "name": "MagicStone" },
  "category": { "id": 103546, "name": "Bijuteri Kolye", "hierarchy": "Aksesuar/Takı & Mücevher/Kolye/Bijuteri Kolye" },
  "price": { "current": 139, "original": 139, "currency": "TRY" },
  "rating": { "average": 4.36, "count": 3302, "comment_count": 1840 },
  "favorite_count": 247400,
  "is_in_stock": true,
  "variant_attribute": "Beden",
  "variants": [
    { "item_number": 1262050948, "value": "45 cm", "barcode": "KL20576", "is_in_stock": true, "is_selected": true, "price": 149 }
  ],
  "merchant": { "id": 207811, "name": "MagicStoneTakı", "score": 9.5, "city": "İstanbul" },
  "top_rankings": [{ "type": "bestSeller", "rank": 1 }]
}
```

All 14 endpoints are now live at `http://localhost:8000`.

Want prices in euros or dirhams? Add `country=DE` or `country=AE` to any call — 35 Trendyol storefronts are supported.

## 📚 Endpoints

14 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Product Details | `/products/details` | Price, stock, sizes, specs, ratings and every seller's offer |
| Search Products | `/products/search` | 36 products per page, with brand, category and price filters |
| Product Reviews | `/products/reviews` | 50 reviews per page with photos, rating breakdown and AI summary |
| Product Questions | `/products/questions` | Buyer questions with the seller's answers, 50 per page |
| Product Variants | `/products/variants` | Sizes with stock, plus sibling colours and storage options |
| Similar Products | `/products/similar` | 24 recommended look-alikes with prices and ratings |
| Categories | `/categories/list` | The full category menu with IDs and links |
| Category Products | `/categories/products` | 36 products per page from any category, filterable |
| Brand Products | `/brands/products` | 36 products per page from any brand, filterable |
| Store Details | `/stores/details` | Score, followers, product count, shipping and reply times |
| Store Products | `/stores/products` | 20 products per page from any store, searchable |
| Store Reviews | `/stores/reviews` | Reviews across a store's products, 20 per page |
| Best Seller Categories | `/rankings/categories` | The 4,000+ category lists behind Trendyol's best-sellers |
| Best Sellers | `/rankings/products` | Top 100 best-selling, most viewed or most favourited per category |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-trendyol-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-trendyol-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-trendyol-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/products/details",
    params={"product": "905790695"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Trendyol Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Trendyol%20Scraper%20API.)

[![Ask Us by Email about Trendyol Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Trendyol%20Scraper%20API&body=I%20need%20help%20using%20the%20Trendyol%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/trendyol-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/trendyol-scraper)
