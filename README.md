# Digital Business Twin Generator

A hybrid desktop + web application that lets a small business owner enter
their shop details once and instantly get a live, hosted website, a QR code,
and a shareable WhatsApp catalog — no coding required.

---

## What it does

1. **Desktop app** (PyQt5) — the shop owner fills in business info and adds
   products with photos and descriptions, with a live preview as they type.
2. **Web dashboard** — the same data can be managed from a browser, with
   extra tools: theme picker, order inbox, analytics, AI product
   descriptions, and QR/WhatsApp sharing.
3. **Site Generation Engine** — takes the saved shop + product data and
   renders a complete, real website (not a mockup) using the chosen theme.
4. **Deployment** — the generated site is pushed live to Cloudflare Pages via
   `wrangler`, giving the shop a real public URL.
5. **Ordering** — customers order through the live site's checkout, which
   sends the order straight to WhatsApp *and* logs it in the dashboard's
   Order Inbox — no payment gateway needed.

---

## Project Structure

```
digital-twin/
├── desktop_app/
│   └── main.py                 # PyQt5 desktop input tool
├── web_backend/
│   ├── app.py                   # Flask app — routes, auth, AI, orders, QR
│   ├── site_generator.py        # Renders theme templates into static sites
│   ├── templates/
│   │   ├── auth/                 # Custom sign-in / sign-up pages (Clerk)
│   │   └── dashboard.html        # Web dashboard (all tabs)
│   └── static/
│       ├── uploads/               # Uploaded product/shop photos
│       └── theme-previews/        # Video previews shown in Theme tab
├── site_templates/              # Website THEMES used for GENERATED shop sites
│   ├── rival_shop/                # Bold indigo storefront
│   ├── nami_shop/                 # Calm slate-blue, paper-goods feel
│   └── fernweg_shop/              # Earthy rust + cream, travel-goods feel
├── generated_sites/             # Output folder — generated static sites land here
├── requirements.txt
├── .env.example
└── README.md
```

---

## Features

- **Authentication** — Clerk-powered, with a fully custom-themed sign-in/up UI
- **Three website themes**, each a real 5-page storefront (Home, Shop,
  Product, Cart, Checkout) with:
  - Real product photos, descriptions, and categories (no fake demo data)
  - Working cart (add/remove/qty) via browser localStorage
  - **WhatsApp checkout** — no card payment form; orders are sent straight
    to the shop owner's WhatsApp and logged in the Order Inbox
  - SEO meta tags, discount banner, AI chatbot widget, page-view tracking
- **Dashboard tabs**: Overview, Shop Info, Products, Theme, Share & QR, Order Inbox
- **Product management**: multi-photo upload, AI-written descriptions
  (Gemini analyzes the photo → Groq writes the copy), drag-to-reorder
- **QR code** generation that routes through a tracked redirect, so scans
  are counted in the dashboard
- **AI chatbot** on every generated site, scoped to that shop's own info/products
- **Desktop app parity** — business info, products (with description +
  photo), theme selection, and live preview, all synced to the same backend
  as the web dashboard

---

## Prerequisites

- Python 3.10+
- Node.js (for the Cloudflare `wrangler` CLI)
- A MongoDB Atlas account (free tier is enough)
- A free Clerk account — https://clerk.com
- A free Groq API key — https://console.groq.com
- A free Gemini API key — https://aistudio.google.com/apikey
- A free Cloudflare account — https://dash.cloudflare.com

---

## Setup & Run Locally

### 1. Extract and enter the project folder
```bash
cd digital-twin
```

### 2. Create a virtual environment (recommended)
```bash
python -m venv venv

venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
```bash
cp .env.example .env
```
Then fill in `.env`:
- `MONGO_URI` — your MongoDB Atlas connection string
- `CLERK_PUBLISHABLE_KEY` / `CLERK_SECRET_KEY` — from clerk.com
- `GROQ_API_KEY` — from console.groq.com (text AI: descriptions + chatbot)
- `GEMINI_API_KEY` — from aistudio.google.com/apikey (photo analysis)
- `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_PROJECT` —
  needed for real deployment (see Cloudflare setup below)
- `BACKEND_PUBLIC_URL` — the public address of this backend (needed for
  orders/chatbot/analytics to work from your *live* deployed site — see
  below). Leave as `http://127.0.0.1:5000` for local-only testing.

### 5. One-time Cloudflare Pages setup
```bash
npm install -g wrangler
wrangler login
wrangler pages project create digital-twin-sites
```
Use that project name as `CLOUDFLARE_PROJECT` in `.env`.

### 6. Run the backend server
```bash
cd web_backend
python app.py
```

### 7. Open it in your browser
- Sign-in: http://127.0.0.1:5000/sign-in
- Dashboard: http://127.0.0.1:5000/dashboard

### 8. Run the desktop app (in a second terminal)
```bash
cd desktop_app
python main.py
```
Keep the Flask server running — the desktop app talks to the same backend.

---

## Making Orders/Chatbot Work on Your *Live* Site

Your generated site is hosted on Cloudflare (`*.pages.dev`), but your Flask
backend runs on your own machine (`127.0.0.1`) — the internet can't reach
that directly. For orders and the AI chatbot to work once the site is live,
your backend needs a public URL too:

- **Quick/demo option:** use [ngrok](https://ngrok.com) —
  `ngrok http 5000`, then set `BACKEND_PUBLIC_URL` in `.env` to the ngrok
  URL it gives you, restart the server, and regenerate your site.
- **Permanent option:** deploy `web_backend/` to a free host like Render or
  Railway, and use that URL as `BACKEND_PUBLIC_URL` instead.

---

## Themes

| Theme | Feel |
|---|---|
| **Rival** | Bold indigo, confident, full storefront with cart |
| **Nami** | Calm slate blue, minimal, paper-goods aesthetic |
| **Fernweg** | Earthy rust + cream, warm, travel-goods feel |

Each theme is a complete static site (no backend needed per-site) — all
dynamic behavior (orders, chat, analytics) calls back to this one shared
Flask backend via `BACKEND_PUBLIC_URL`.

Switch a shop's theme from the dashboard's **Theme** tab, then click
**Regenerate Site** on the **Overview** tab to publish the change.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` on run | Activate your venv before `pip install -r requirements.txt` |
| MongoDB connection timeout | Check `MONGO_URI`, and that your IP is allowed in Atlas → Network Access |
| SSL certificate errors on macOS | Run `/Applications/Python 3.x/Install Certificates.command`, or rely on the `certifi` package already wired into the backend |
| `wrangler pages deploy` fails with 7003 | Your `CLOUDFLARE_ACCOUNT_ID` is wrong — run `wrangler whoami` to get the correct one |
| AI description/chat returns an error | Check your Groq/Gemini keys are set; the backend auto-discovers working models, so check the terminal log for which model it picked |
| Orders don't appear in Order Inbox | Your generated site needs `BACKEND_PUBLIC_URL` set to a real public address — see the ngrok section above |
| QR scans / page views stay at 0 | Same cause as above — tracking calls need a reachable backend |
| Clerk sign-in shows "not configured" | Make sure you're on the full URL with port (`:5000`), and that `.env` is in the project root, not `web_backend/` |

---

## Tech Stack

| Category | Choice |
|---|---|
| Desktop | Python, PyQt5 |
| Backend | Flask, PyMongo, Flask-CORS |
| Database | MongoDB Atlas (NoSQL) |
| Auth | Clerk (custom themed UI) |
| AI | Groq (text) + Gemini (vision) |
| Deployment | Cloudflare Pages (`wrangler`) |
| Site generation | Jinja2 |
| QR codes | `qrcode` |

---

## Future Scope

- Multi-language toggle (EN/HI) per shop
- Per-day business hours table on generated sites
- Multiple shops per owner account
- Custom domain auto-verification (currently manual DNS steps)
- More themes
