"""
Digital Business Twin Generator - Web Backend
Flask + MongoDB (PyMongo) + Clerk (headless auth)
"""
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
from pymongo import MongoClient
import certifi
from bson.objectid import ObjectId
from dotenv import load_dotenv
import os
import re
import qrcode
import io
import base64
import subprocess
from datetime import datetime

load_dotenv()  # reads .env file if present

# .env lives in the project root, one level above this file (web_backend/app.py).
# load_dotenv() alone only reliably finds .env in the current working directory,
# so if the server is started from inside web_backend/, it can miss the file.
# This explicit fallback path guarantees it's picked up either way.
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path=_ENV_PATH, override=False)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

# CORS: the generated static shop sites live on a different origin (e.g.
# *.pages.dev) and need to call this backend for orders and the AI chatbot.
# Only the specific public-facing routes get CORS enabled below via decorators;
# this global setup covers preflight OPTIONS requests for them.
CORS(app, resources={
    r"/api/orders*": {"origins": "*"},
    r"/api/ai/*": {"origins": "*"},
    r"/api/analytics/*": {"origins": "*"},
})

# The public URL where THIS backend is reachable from the internet (not
# 127.0.0.1). Generated sites embed this so their order form / chatbot know
# where to send requests. Falls back to localhost for local-only testing —
# orders/chatbot won't work on the LIVE deployed site until this is set to a
# real public URL (e.g. via ngrok, Render, Railway, or similar).
BACKEND_PUBLIC_URL = os.environ.get("BACKEND_PUBLIC_URL", "http://127.0.0.1:5000")

# ---------------- Groq (AI descriptions + chatbot) ----------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
groq_client = None

if GROQ_API_KEY:
    try:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)
        print("[startup] Groq client initialized.")
    except Exception as e:
        print(f"[startup] Groq client failed to initialize: {e}")

# ---------------- Gemini (image analysis for AI descriptions) ----------------
# Your Groq account currently has no vision-capable models (confirmed via
# get_available_groq_models() below), so photo analysis uses Gemini instead —
# Groq stays as the fast path for text-only descriptions and the chatbot.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
gemini_client_ready = False

if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_client_ready = True
        print("[startup] Gemini client initialized.")
    except Exception as e:
        print(f"[startup] Gemini client failed to initialize: {e}")


# Gemini model names change too (their own API just told us gemini-2.0-flash
# was retired mid-project). Same self-healing approach as the Groq models:
# try candidates in order, remember whichever works.
GEMINI_MODEL_CANDIDATES = [
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-pro-latest",
]
_working_gemini_model = {"id": None}


def gemini_analyze_image(image_data_url: str, prompt_text: str) -> str:
    """
    Sends the product photo + prompt to Gemini's vision-capable model and
    returns its text response. image_data_url is a base64 data URL like
    "data:image/png;base64,...." (exactly what the browser's FileReader produces).

    Used for IMAGE ANALYSIS only — Gemini describes what it sees; Groq is the
    one that turns that analysis into actual marketing copy (see ai_describe_product).
    """
    if not gemini_client_ready:
        raise RuntimeError("Gemini not configured — add GEMINI_API_KEY to .env")

    import base64
    header, encoded = image_data_url.split(",", 1)
    mime_type = header.split(";")[0].replace("data:", "") or "image/jpeg"
    image_bytes = base64.b64decode(encoded)
    content = [prompt_text, {"mime_type": mime_type, "data": image_bytes}]

    candidates = ([_working_gemini_model["id"]] if _working_gemini_model["id"] else []) + GEMINI_MODEL_CANDIDATES
    last_error = None
    for model_name in candidates:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(content)
            text = (response.text or "").strip()
            if text:
                _working_gemini_model["id"] = model_name
                print(f"[gemini] Using model: {model_name}")
                return text
            print(f"[gemini] Model {model_name} returned empty content, trying next candidate.")
        except Exception as e:
            print(f"[gemini] Model {model_name} failed: {e}")
            last_error = e
            continue

    raise last_error or RuntimeError("No working Gemini model found")

# Hardcoded model names kept going stale (Groq retires/renames them often,
# and different accounts have access to different sets). The only reliable
# fix is to ask the account directly what it actually has access to, right
# when we need it, and cache that list for the rest of this process's life.
_available_models_cache = {"models": None}


def get_available_groq_models():
    if _available_models_cache["models"] is not None:
        return _available_models_cache["models"]
    try:
        models = [m.id for m in groq_client.models.list().data]
        print(f"[groq] Account has access to: {models}")
    except Exception as e:
        print(f"[groq] Could not list available models: {e}")
        models = []
    _available_models_cache["models"] = models
    return models


def _exclude_non_chat(models):
    """Filter out model families that can't do plain chat completions
    (speech-to-text, text-to-speech, moderation/guard models)."""
    return [m for m in models if not any(x in m.lower() for x in ["whisper", "tts", "guard"])]


def get_text_model_candidates():
    """Chat-capable models, with fast/instant-style ones preferred first
    (less likely to burn the token budget on internal reasoning)."""
    models = _exclude_non_chat(get_available_groq_models())
    preferred = [m for m in models if "instant" in m.lower() or "versatile" in m.lower()]
    rest = [m for m in models if m not in preferred]
    return preferred + rest


def get_vision_model_candidates():
    """Models that can plausibly accept an image — heuristic name match since
    the API doesn't expose modality directly. Empty if the account has none."""
    models = _exclude_non_chat(get_available_groq_models())
    return [m for m in models if any(x in m.lower() for x in ["vision", "scout", "maverick", "4o"])]


_working_groq_model = {"id": None}
_working_vision_model = {"id": None}


def _has_real_content(completion) -> bool:
    """A request can succeed (200 OK, no exception) but still come back with an
    empty answer — e.g. a reasoning model spending its whole token budget on
    internal thinking. Treat that as a failure so we try the next candidate."""
    try:
        return bool(completion.choices[0].message.content.strip())
    except Exception:
        return False


def _groq_completion_with_fallback(messages, candidates, cache, max_tokens=150):
    """Shared logic: try the cached working model first, then walk through
    `candidates` in order until one returns a real (non-empty) reply."""
    if not groq_client:
        raise RuntimeError("Groq not configured")

    if cache["id"]:
        try:
            completion = groq_client.chat.completions.create(
                model=cache["id"], messages=messages, max_tokens=max_tokens
            )
            if _has_real_content(completion):
                return completion
            print(f"[groq] Cached model {cache['id']} returned empty content — re-discovering.")
            cache["id"] = None
        except Exception:
            cache["id"] = None

    last_error = None
    for candidate in candidates:
        try:
            completion = groq_client.chat.completions.create(
                model=candidate, messages=messages, max_tokens=max_tokens
            )
            if not _has_real_content(completion):
                print(f"[groq] Model {candidate} returned empty content, trying next candidate.")
                continue
            cache["id"] = candidate
            print(f"[groq] Using model: {candidate}")
            return completion
        except Exception as e:
            print(f"[groq] Model {candidate} failed: {e}")
            last_error = e
            continue

    raise last_error or RuntimeError("No working Groq model found")


def groq_chat_completion(messages, max_tokens=150):
    """Text-only completion, with automatic fallback across this account's actual available models."""
    return _groq_completion_with_fallback(messages, get_text_model_candidates(), _working_groq_model, max_tokens)


def groq_vision_completion(messages, max_tokens=200):
    """Image+text completion, with automatic fallback across this account's actual vision-capable models."""
    candidates = get_vision_model_candidates()
    if not candidates:
        raise RuntimeError("No vision-capable models available on this Groq account")
    return _groq_completion_with_fallback(messages, candidates, _working_vision_model, max_tokens)


UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def clean_whatsapp_number(raw: str) -> str:
    """Same normalization as site_generator.py — see that file for the full
    explanation. Applied here too since this file builds wa.me links directly
    (order notifications, WhatsApp catalog) independent of site generation."""
    if not raw:
        return ""
    digits = re.sub(r"[^0-9]", "", str(raw))
    if len(digits) == 10:
        digits = "91" + digits
    return digits

# ---------------- MongoDB Setup ----------------
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000, connectTimeoutMS=8000, tlsCAFile=certifi.where())
db = client["digital_twin_db"]

users_col = db["users"]
shops_col = db["shops"]
products_col = db["products"]
site_configs_col = db["site_configs"]
analytics_col = db["analytics"]
orders_col = db["orders"]

# ---------------- Clerk Config ----------------
# Clerk handles auth logic (OTP, OAuth, sessions) — UI is fully custom, built to match
# the active site theme instead of Clerk's default hosted components (headless mode).
CLERK_PUBLISHABLE_KEY = os.environ.get("CLERK_PUBLISHABLE_KEY", "")
CLERK_SECRET_KEY = os.environ.get("CLERK_SECRET_KEY", "")

# Diagnostic: prints on server startup so you can confirm the key was actually
# picked up from .env. Look for this line in your terminal when you run app.py.
if CLERK_PUBLISHABLE_KEY:
    print(f"[startup] Clerk key loaded: {CLERK_PUBLISHABLE_KEY[:15]}... (length {len(CLERK_PUBLISHABLE_KEY)})")
else:
    print("[startup] WARNING: CLERK_PUBLISHABLE_KEY is EMPTY — .env was not found or the variable name doesn't match.")
    print(f"[startup] Looked for .env at: {_ENV_PATH}")
    print(f"[startup] That path exists: {os.path.exists(_ENV_PATH)}")

# Dev mode: when true (or when no Clerk key is configured yet), API routes
# that normally require a Clerk session will auto-create/use a local test
# user instead of returning 401. This lets you build and test the desktop
# app + dashboard flow before real Clerk keys are wired in.
DEV_MODE = os.environ.get("DEV_MODE", "true").lower() == "true"
DEV_USER_ID = "dev-local-user"


def ensure_session():
    """Returns a valid user_id for the current request — real session if signed in,
    or a dev fallback user if DEV_MODE is on and no session exists yet."""
    if "user_id" in session:
        return session["user_id"]
    if DEV_MODE:
        session["user_id"] = DEV_USER_ID
        return DEV_USER_ID
    return None


# ---------------- Home ----------------
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("sign_in_page"))


# ---------------- Auth Routes (custom UI, Clerk-powered) ----------------
@app.route("/sign-in")
def sign_in_page():
    """Custom sign-in page styled per active theme (default: macOS)."""
    theme = request.args.get("theme", "rival_shop")
    return render_template("auth/sign_in.html", clerk_pk=CLERK_PUBLISHABLE_KEY, theme=theme)


@app.route("/sign-up")
def sign_up_page():
    """Custom sign-up page styled per active theme (default: macOS)."""
    theme = request.args.get("theme", "rival_shop")
    return render_template("auth/sign_up.html", clerk_pk=CLERK_PUBLISHABLE_KEY, theme=theme)


@app.route("/api/auth/session", methods=["POST"])
def create_session():
    """Called by frontend JS after Clerk confirms sign-in, to sync our own user record."""
    data = request.json
    clerk_user_id = data.get("clerk_user_id")
    email = data.get("email")

    existing = users_col.find_one({"clerk_user_id": clerk_user_id})
    if not existing:
        user_id = users_col.insert_one({
            "clerk_user_id": clerk_user_id,
            "email": email,
            "created_at": datetime.utcnow(),
            "role": "owner"
        }).inserted_id
    else:
        user_id = existing["_id"]

    session["user_id"] = str(user_id)
    session["clerk_user_id"] = clerk_user_id
    return jsonify({"status": "ok", "user_id": str(user_id)})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "logged_out"})


# ---------------- Dashboard ----------------
@app.route("/dashboard")
def dashboard():
    user_id = ensure_session()
    shop = None
    products = []
    site_status = "Not generated yet"
    site_live_url = None
    view_count = 0
    scan_count = 0

    try:
        shop = shops_col.find_one({"owner_id": user_id})
        if shop:
            shop["_id"] = str(shop["_id"])
            products = list(products_col.find({"shop_id": shop["_id"]}).sort("order", 1))
            for p in products:
                p["_id"] = str(p["_id"])

            site_config = site_configs_col.find_one({"shop_id": shop["_id"]})
            if site_config:
                site_status = "Live"
                site_live_url = site_config.get("live_url")

            view_count = analytics_col.count_documents({"shop_id": shop["_id"], "event_type": "view"})
            scan_count = analytics_col.count_documents({"shop_id": shop["_id"], "event_type": "qr_scan"})
    except Exception as e:
        print(f"[dashboard] MongoDB error: {e}")
        site_status = "Database unreachable"

    return render_template(
        "dashboard.html", shop=shop, products=products,
        site_status=site_status, site_live_url=site_live_url,
        view_count=view_count, scan_count=scan_count
    )


# ---------------- Shop / Site Generation API ----------------
@app.route("/api/shop", methods=["GET"])
def get_shop():
    """Returns the current session's shop + products — used by the desktop app
    to load existing saved data on startup, so it isn't always blank if the
    person already saved a shop via the web dashboard."""
    user_id = ensure_session()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    try:
        shop = shops_col.find_one({"owner_id": user_id})
        if not shop:
            return jsonify({"shop": None, "products": []})

        shop["_id"] = str(shop["_id"])
        products = list(products_col.find({"shop_id": shop["_id"]}).sort("order", 1))
        for p in products:
            p["_id"] = str(p["_id"])

        return jsonify({"shop": shop, "products": products})
    except Exception as e:
        return jsonify({"error": f"Database connection failed: {str(e)}"}), 503


DEFAULT_HOURS_BY_DAY = {
    "mon": {"open": "9:00 AM", "close": "9:00 PM", "closed": False},
    "tue": {"open": "9:00 AM", "close": "9:00 PM", "closed": False},
    "wed": {"open": "9:00 AM", "close": "9:00 PM", "closed": False},
    "thu": {"open": "9:00 AM", "close": "9:00 PM", "closed": False},
    "fri": {"open": "9:00 AM", "close": "9:00 PM", "closed": False},
    "sat": {"open": "9:00 AM", "close": "9:00 PM", "closed": False},
    "sun": {"open": "9:00 AM", "close": "9:00 PM", "closed": True},
}
SHOP_TEXT_FIELDS = ["name", "category", "hours", "contact", "whatsapp", "theme", "subdomain",
                     "discount_banner", "custom_domain", "language"]
SHOP_COMPLEX_FIELDS = ["hours_by_day"]  # dict fields, handled separately from simple .get()


@app.route("/api/shop", methods=["POST"])
def create_or_update_shop():
    user_id = ensure_session()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    data = request.json or {}

    try:
        existing = shops_col.find_one({"owner_id": user_id})

        if existing:
            # Only update fields actually present in this request — e.g. the
            # "Apply Theme" button only sends {theme: "..."}, and blindly writing
            # every field with .get() would null out name/category/etc. that
            # weren't included, wiping the rest of the shop's saved info.
            update_fields = {"updated_at": datetime.utcnow()}
            for field in SHOP_TEXT_FIELDS + SHOP_COMPLEX_FIELDS:
                if field in data:
                    update_fields[field] = data[field]

            shops_col.update_one({"_id": existing["_id"]}, {"$set": update_fields})
            shop_id = existing["_id"]
        else:
            # New shop: fill in sensible defaults for anything not provided.
            shop_doc = {
                "owner_id": user_id,
                "name": data.get("name", ""),
                "category": data.get("category", ""),
                "hours": data.get("hours", ""),
                "contact": data.get("contact", ""),
                "whatsapp": data.get("whatsapp", ""),
                "theme": data.get("theme", "rival_shop"),
                "subdomain": data.get("subdomain", ""),
                "discount_banner": data.get("discount_banner", ""),
                "custom_domain": data.get("custom_domain", ""),
                "language": data.get("language", "en"),
                "hours_by_day": data.get("hours_by_day", DEFAULT_HOURS_BY_DAY),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            shop_id = shops_col.insert_one(shop_doc).inserted_id
    except Exception as e:
        # Most common cause: MongoDB Atlas can't be reached — wrong MONGO_URI,
        # or your current IP isn't whitelisted in Atlas Network Access settings.
        return jsonify({"error": f"Database connection failed: {str(e)}"}), 503

    return jsonify({"status": "ok", "shop_id": str(shop_id)})


@app.route("/api/product", methods=["POST"])
def add_product():
    user_id = ensure_session()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    shop = shops_col.find_one({"owner_id": user_id})
    if not shop:
        return jsonify({"error": "Save your Shop Info first before adding products."}), 400

    data = request.json
    photos = data.get("photos", [])
    primary_photo = data.get("photo_url", "") or (photos[0] if photos else "")

    try:
        max_order = products_col.count_documents({"shop_id": str(shop["_id"])})
    except Exception:
        max_order = 0

    product_doc = {
        "shop_id": str(shop["_id"]),
        "name": data.get("name"),
        "price": data.get("price"),
        "category": data.get("category"),
        "description": data.get("description", ""),
        "photo_url": primary_photo,       # backward-compatible single photo
        "photos": photos or ([primary_photo] if primary_photo else []),  # gallery
        "order": max_order,
        "created_at": datetime.utcnow()
    }
    try:
        product_id = products_col.insert_one(product_doc).inserted_id
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 503

    return jsonify({"status": "ok", "product_id": str(product_id)})


@app.route("/api/product/<product_id>", methods=["PUT"])
def edit_product(product_id):
    user_id = ensure_session()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    shop = shops_col.find_one({"owner_id": user_id})
    if not shop:
        return jsonify({"error": "no shop found"}), 400

    data = request.json
    update_fields = {}
    for field in ["name", "price", "category", "photo_url", "photos", "description"]:
        if field in data:
            update_fields[field] = data[field]

    try:
        result = products_col.update_one(
            {"_id": ObjectId(product_id), "shop_id": str(shop["_id"])},
            {"$set": update_fields}
        )
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 503

    if result.matched_count == 0:
        return jsonify({"error": "Product not found"}), 404

    return jsonify({"status": "ok"})


@app.route("/api/product/<product_id>", methods=["DELETE"])
def delete_product(product_id):
    user_id = ensure_session()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    shop = shops_col.find_one({"owner_id": user_id})
    if not shop:
        return jsonify({"error": "no shop found"}), 400

    try:
        result = products_col.delete_one({"_id": ObjectId(product_id), "shop_id": str(shop["_id"])})
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 503

    if result.deleted_count == 0:
        return jsonify({"error": "Product not found"}), 404

    return jsonify({"status": "ok"})


@app.route("/api/products/reorder", methods=["PUT"])
def reorder_products():
    """Accepts an ordered list of product IDs (drag-to-reorder result from the
    dashboard) and saves each product's new position."""
    user_id = ensure_session()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    shop = shops_col.find_one({"owner_id": user_id})
    if not shop:
        return jsonify({"error": "no shop found"}), 400

    ordered_ids = (request.json or {}).get("product_ids", [])
    try:
        for index, pid in enumerate(ordered_ids):
            products_col.update_one(
                {"_id": ObjectId(pid), "shop_id": str(shop["_id"])},
                {"$set": {"order": index}}
            )
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 503

    return jsonify({"status": "ok"})


@app.route("/api/upload-photo", methods=["POST"])
def upload_photo():
    """Handles product/shop photo uploads from the desktop app or web dashboard."""
    user_id = ensure_session()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    if "photo" not in request.files:
        return jsonify({"error": "no file part"}), 400

    file = request.files["photo"]
    if file.filename == "" or not allowed_file(file.filename):
        return jsonify({"error": "invalid file"}), 400

    filename = secure_filename(f"{datetime.utcnow().timestamp()}_{file.filename}")
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    # In production this would upload to a CDN/object storage (e.g. Cloudflare R2);
    # for now it's served locally via Flask's static route.
    photo_url = url_for("static", filename=f"uploads/{filename}", _external=True)
    return jsonify({"status": "ok", "photo_url": photo_url})


@app.route("/api/generate-site", methods=["POST"])
def generate_and_deploy_site():
    """
    Full pipeline: fetch shop + products from MongoDB, render the chosen theme
    template into a static site, then deploy it (Cloudflare Workers/Pages).
    """
    user_id = ensure_session()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    from site_generator import generate_site, deploy_to_cloudflare

    shop = shops_col.find_one({"owner_id": user_id})
    if not shop:
        return jsonify({"error": "no shop found — save business info first"}), 400

    products = list(products_col.find({"shop_id": str(shop["_id"])}).sort("order", 1))
    shop["_id"] = str(shop["_id"])  # make JSON/template safe

    site_path = generate_site(shop, products, backend_url=BACKEND_PUBLIC_URL)
    live_url = deploy_to_cloudflare(shop["subdomain"], os.path.dirname(site_path))

    site_configs_col.update_one(
        {"shop_id": shop["_id"]},
        {"$set": {"shop_id": shop["_id"], "live_url": live_url, "last_deployed": datetime.utcnow()}},
        upsert=True
    )

    return jsonify({"status": "ok", "live_url": live_url})


# ---------------- Order Inbox ----------------
@app.route("/api/orders", methods=["POST"])
def submit_order():
    """
    PUBLIC route — called directly from a generated shop's live site (a
    different origin, hence CORS enabled above) when a customer submits the
    order form. No login required: this is the shop's customer, not the owner.
    """
    data = request.json or {}
    shop_id = data.get("shop_id")
    if not shop_id:
        return jsonify({"error": "shop_id required"}), 400

    order_doc = {
        "shop_id": shop_id,
        "customer_name": data.get("customer_name", ""),
        "customer_phone": data.get("customer_phone", ""),
        "items": data.get("items", []),  # [{name, price, qty}, ...]
        "notes": data.get("notes", ""),
        "status": "new",  # new -> confirmed -> done
        "created_at": datetime.utcnow()
    }
    try:
        order_id = orders_col.insert_one(order_doc).inserted_id
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 503

    # Build a WhatsApp deep link pre-filled with the order, so the customer
    # (or the generated site's JS) can open it directly to send the order too.
    shop = None
    try:
        shop = shops_col.find_one({"_id": ObjectId(shop_id)})
    except Exception:
        pass

    wa_link = None
    if shop and shop.get("whatsapp"):
        lines = [f"New order from {order_doc['customer_name'] or 'a customer'}:"]
        for item in order_doc["items"]:
            lines.append(f"• {item.get('name')} x{item.get('qty', 1)} — ₹{item.get('price')}")
        if order_doc["notes"]:
            lines.append(f"Note: {order_doc['notes']}")
        lines.append(f"Contact: {order_doc['customer_phone']}")
        message = "\n".join(lines)
        wa_link = f"https://wa.me/{clean_whatsapp_number(shop['whatsapp'])}?text={message.replace(' ', '%20').replace(chr(10), '%0A')}"

    return jsonify({"status": "ok", "order_id": str(order_id), "whatsapp_link": wa_link})


@app.route("/api/orders", methods=["GET"])
def list_orders():
    """Order Inbox for the dashboard — owner-only."""
    user_id = ensure_session()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    shop = shops_col.find_one({"owner_id": user_id})
    if not shop:
        return jsonify({"orders": []})

    try:
        orders = list(orders_col.find({"shop_id": str(shop["_id"])}).sort("created_at", -1))
        for o in orders:
            o["_id"] = str(o["_id"])
        return jsonify({"orders": orders})
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 503


@app.route("/api/orders/<order_id>", methods=["PUT"])
def update_order_status(order_id):
    user_id = ensure_session()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    shop = shops_col.find_one({"owner_id": user_id})
    if not shop:
        return jsonify({"error": "no shop found"}), 400

    new_status = (request.json or {}).get("status")
    if new_status not in ["new", "confirmed", "done"]:
        return jsonify({"error": "invalid status"}), 400

    try:
        result = orders_col.update_one(
            {"_id": ObjectId(order_id), "shop_id": str(shop["_id"])},
            {"$set": {"status": new_status}}
        )
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 503

    if result.matched_count == 0:
        return jsonify({"error": "Order not found"}), 404
    return jsonify({"status": "ok"})


# ---------------- AI Features (Groq + Gemini) ----------------
@app.route("/api/ai/describe", methods=["POST"])
def ai_describe_product():
    """
    Owner-only: generates a short marketing description for a product.

    Pipeline: if a photo is included, Gemini (vision-capable) first analyzes
    it and produces a factual description of what's actually in the image —
    Groq then writes the final marketing sentence using that analysis plus
    the name/category (Groq has no vision models on this account, but is
    faster/cheaper for the actual writing step). If no photo is given, or
    Gemini isn't configured, or image analysis fails, Groq writes the
    description from name/category alone instead.
    """
    user_id = ensure_session()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    if not groq_client:
        return jsonify({"error": "AI not configured — add GROQ_API_KEY to .env"}), 503

    data = request.json or {}
    product_name = data.get("name", "")
    category = data.get("category", "")
    image_base64 = data.get("image_base64", "")
    if not product_name:
        return jsonify({"error": "product name required"}), 400

    image_analysis = None
    used_vision = False

    if image_base64:
        try:
            image_analysis = gemini_analyze_image(
                image_base64,
                "Describe what you see in this product photo in 1-2 factual sentences "
                "— visual details, colors, style, condition — the kind of detail useful "
                "for someone writing marketing copy about it. Don't write the marketing "
                "copy itself, just describe what's visible."
            )
            used_vision = bool(image_analysis)
            if image_analysis:
                print(f"[ai_describe] Gemini image analysis: {image_analysis!r}")
        except Exception as e:
            print(f"[ai_describe] Gemini vision analysis failed, continuing text-only: {e}")
            image_analysis = None

    prompt_text = (
        f"Write one short, appealing marketing sentence (under 20 words, no quotes) "
        f"for a product called '{product_name}'"
        f"{f' in the {category} category' if category else ''}, for a local shop's website."
    )
    if image_analysis:
        prompt_text += f" Here's what the product photo actually shows: {image_analysis}"

    try:
        completion = groq_chat_completion(
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=400,
        )
    except Exception as e:
        return jsonify({"error": f"AI request failed: {str(e)}"}), 503

    try:
        raw_content = completion.choices[0].message.content or ""
        raw_content = raw_content.strip()
        print(f"[ai_describe] raw model output (used_vision_analysis={used_vision}): {raw_content!r}")

        description = raw_content
        # Only strip quote characters if they're genuinely wrapping real text —
        # otherwise this used to turn a literal '""' response into an empty
        # string even though there was technically "content" there.
        if description.startswith('"') and description.endswith('"') and len(description) > 2:
            description = description[1:-1].strip()

        if not description:
            return jsonify({"error": "AI returned an empty response — try again."}), 503

        return jsonify({"description": description})
    except Exception as e:
        return jsonify({"error": f"AI request failed: {str(e)}"}), 503


@app.route("/api/ai/chat", methods=["POST"])
def ai_chat():
    """
    PUBLIC route — powers the chatbot widget on a generated shop's live site.
    Answers are scoped to that specific shop's info/products only.
    """
    if not groq_client:
        return jsonify({"reply": "Chat isn't available right now — please contact us directly."}), 200

    data = request.json or {}
    shop_id = data.get("shop_id")
    user_message = data.get("message", "")
    if not shop_id or not user_message:
        return jsonify({"error": "shop_id and message required"}), 400

    try:
        shop = shops_col.find_one({"_id": ObjectId(shop_id)})
        products = list(products_col.find({"shop_id": shop_id}).sort("order", 1))
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 503

    if not shop:
        return jsonify({"error": "shop not found"}), 404

    product_list = "\n".join([f"- {p['name']}: ₹{p['price']}" for p in products]) or "No products listed yet."
    system_prompt = (
        f"You are a helpful assistant for '{shop.get('name')}', a {shop.get('category')} business. "
        f"Working hours: {shop.get('hours')}. Contact: {shop.get('contact')}. "
        f"Products:\n{product_list}\n\n"
        f"Only answer questions about this shop, its products, hours, or how to order. "
        f"Keep replies short (2-3 sentences max). If asked something unrelated, politely redirect to shop topics."
    )

    try:
        completion = groq_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=150,
        )
        reply = completion.choices[0].message.content.strip()
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": "Sorry, I couldn't process that right now."}), 200


@app.route("/api/generate-qr", methods=["POST"])
def generate_qr():
    """
    Generates a QR code. Instead of encoding the live site URL directly
    (which gives no way to count scans), it encodes a link back through THIS
    backend's /r/<shop_id> redirect route — that route logs a 'qr_scan' event,
    then forwards the phone straight to the real live site.

    Requires BACKEND_PUBLIC_URL to be a real public address (not 127.0.0.1) —
    a phone scanning this QR is on the internet, not your laptop's localhost,
    so it can only reach the redirect if your backend is actually public
    (ngrok, Render, Railway, etc. — see earlier setup notes).
    """
    data = request.json
    site_url = data.get("site_url")
    shop_id = data.get("shop_id")
    if not site_url:
        return jsonify({"error": "site_url required"}), 400

    # Only route through the tracking redirect if we know which shop this is
    # for and have a real public backend URL to redirect through. Otherwise
    # fall back to the plain direct link so the QR still works, just untracked.
    if shop_id and BACKEND_PUBLIC_URL and "127.0.0.1" not in BACKEND_PUBLIC_URL:
        qr_target = f"{BACKEND_PUBLIC_URL}/r/{shop_id}"
    else:
        qr_target = site_url

    img = qrcode.make(qr_target)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return jsonify({"qr_code": f"data:image/png;base64,{qr_base64}"})


@app.route("/r/<shop_id>")
def qr_redirect(shop_id):
    """Logs a QR scan, then forwards the phone to the shop's real live site."""
    try:
        shop = shops_col.find_one({"_id": ObjectId(shop_id)})
        analytics_col.insert_one({
            "shop_id": shop_id,
            "event_type": "qr_scan",
            "timestamp": datetime.utcnow()
        })
    except Exception as e:
        print(f"[qr_redirect] Could not log scan: {e}")
        shop = None

    if not shop:
        return "Shop not found", 404

    site_config = site_configs_col.find_one({"shop_id": shop_id})
    live_url = site_config.get("live_url") if site_config else None
    if not live_url or "PLACEHOLDER" in live_url:
        return "This shop's site isn't live yet.", 404

    return redirect(live_url)


@app.route("/api/generate-whatsapp-catalog", methods=["POST"])
def generate_whatsapp_catalog():
    """Formats the product catalog into a shareable WhatsApp message, using the
    real shop name, real live site URL, and contact info — not placeholders."""
    user_id = ensure_session()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    try:
        shop = shops_col.find_one({"owner_id": user_id})
        if not shop:
            return jsonify({"error": "Save your Shop Info first."}), 400

        shop_id = str(shop["_id"])
        products = list(products_col.find({"shop_id": shop_id}).sort("order", 1))
        if not products:
            return jsonify({"error": "Add at least one product first."}), 400

        site_config = site_configs_col.find_one({"shop_id": shop_id})
        live_url = site_config.get("live_url") if site_config else None
        if not live_url or "PLACEHOLDER" in live_url:
            return jsonify({"error": "Generate your site first on the Overview tab, so we have a real link to share."}), 400

        shop_name = shop.get("name") or "Our Shop"
        lines = [f"*{shop_name}* — Catalog", ""]
        for p in products:
            lines.append(f"• {p['name']} — ₹{p['price']}")
        lines.append("")
        if shop.get("contact"):
            lines.append(f"📞 Order/Contact: {shop['contact']}")
        if shop.get("hours"):
            lines.append(f"🕒 Hours: {shop['hours']}")
        lines.append(f"🌐 Visit: {live_url}")

        message = "\n".join(lines)
        wa_link = f"https://wa.me/?text={message.replace(' ', '%20').replace(chr(10), '%0A')}"
        return jsonify({"message": message, "whatsapp_link": wa_link})
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 503


@app.route("/api/analytics/track", methods=["POST"])
def track_visit():
    """Logs a page view or QR scan for a shop's generated site."""
    data = request.json
    analytics_col.insert_one({
        "shop_id": data.get("shop_id"),
        "event_type": data.get("event_type", "view"),  # 'view' or 'qr_scan'
        "timestamp": datetime.utcnow()
    })
    return jsonify({"status": "logged"})


if __name__ == "__main__":
    # use_reloader=False: without this, Flask's auto-reloader watches the whole
    # project folder (including generated_sites/), and restarts the server the
    # moment a site-generation request writes new files there — killing that
    # in-flight request and causing "Backend not reachable" errors in the browser.
    # threaded=True: lets Flask handle more than one request at a time, so a slow
    # deploy (wrangler) doesn't block other pages/requests while it runs.
    app.run(debug=True, port=5000, use_reloader=False, threaded=True)
