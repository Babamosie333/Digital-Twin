"""
Site Generation Engine
Takes shop + product data from MongoDB and renders the chosen theme template
into static HTML files, ready for deployment (Cloudflare Pages).
"""
import os
import re
import shutil
import subprocess
from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "site_templates")
OUTPUT_DIR = os.path.join(BASE_DIR, "generated_sites")

THEME_FOLDERS = {
    "rival_shop": "rival_shop",
    "nami_shop": "nami_shop",
    "fernweg_shop": "fernweg_shop",
}

DEFAULT_THEME = "rival_shop"


def clean_whatsapp_number(raw: str) -> str:
    """
    Normalizes a WhatsApp number for use in wa.me links, which are extremely
    strict: digits only, full international format, no spaces/dashes/plus.
    If a 10-digit number is given with no country code, assumes India (+91).
    """
    if not raw:
        return ""
    digits = re.sub(r"[^0-9]", "", str(raw))
    if len(digits) == 10:
        digits = "91" + digits
    return digits


def generate_site(shop: dict, products: list, backend_url: str = "http://127.0.0.1:5000") -> str:
    """
    Renders every HTML page in the shop's chosen theme with its data, and
    copies over the theme's static assets (style.css, app.js, data.js is
    rendered too since it contains Jinja templating for the real product data).
    Returns the path to the generated index.html file.
    """
    theme_key = shop.get("theme", DEFAULT_THEME)
    theme_folder = THEME_FOLDERS.get(theme_key, DEFAULT_THEME)
    theme_dir = os.path.join(TEMPLATES_DIR, theme_folder)

    shop = dict(shop)  # don't mutate the caller's dict
    shop["whatsapp"] = clean_whatsapp_number(shop.get("whatsapp", ""))

    subdomain = shop.get("subdomain", "shop")
    site_dir = os.path.join(OUTPUT_DIR, subdomain)
    os.makedirs(site_dir, exist_ok=True)

    env = Environment(loader=FileSystemLoader(theme_dir))

    # data.js contains real Jinja templating (product data injection), so it
    # gets rendered like the HTML pages, not just copied as a static asset.
    render_as_template = lambda fn: fn.endswith(".html") or fn == "data.js"

    index_output_path = None
    for filename in os.listdir(theme_dir):
        src_path = os.path.join(theme_dir, filename)

        if render_as_template(filename):
            template = env.get_template(filename)
            rendered = template.render(shop=shop, products=products, backend_url=backend_url)
            output_path = os.path.join(site_dir, filename)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(rendered)
            if filename == "index.html":
                index_output_path = output_path
        else:
            shutil.copy2(src_path, os.path.join(site_dir, filename))

    return index_output_path


def deploy_to_cloudflare(subdomain: str, site_dir: str) -> str:
    """
    Publishes the generated static site to Cloudflare Pages using the `wrangler` CLI.

    Requires (set as environment variables before calling):
        CLOUDFLARE_API_TOKEN   - API token with Pages:Edit permission
        CLOUDFLARE_ACCOUNT_ID  - Cloudflare account ID
        CLOUDFLARE_PROJECT     - Pages project name (created once via `wrangler pages project create`)

    Cloudflare Pages deploys give every branch a URL like:
        https://{branch}.{project-name}.pages.dev

    If wrangler/credentials aren't available, falls back to a placeholder URL
    so the rest of the app can still be demoed — that placeholder is NOT a
    real website and will not open in a browser.
    """
    project = os.environ.get("CLOUDFLARE_PROJECT")

    has_credentials = all([
        os.environ.get("CLOUDFLARE_API_TOKEN"),
        os.environ.get("CLOUDFLARE_ACCOUNT_ID"),
        project
    ])

    if not has_credentials:
        print("[deploy_to_cloudflare] No Cloudflare credentials found in .env — skipping real deployment.")
        return f"https://{subdomain}.{project or 'your-project'}.pages.dev (PLACEHOLDER — Cloudflare not configured)"

    live_url = f"https://{subdomain}.{project}.pages.dev"

    try:
        result = subprocess.run(
            ["wrangler", "pages", "deploy", site_dir, "--project-name", project, "--branch", subdomain],
            capture_output=True, text=True, timeout=120,
            stdin=subprocess.DEVNULL
        )
        print(f"[deploy_to_cloudflare] wrangler stdout:\n{result.stdout}")
        if result.returncode != 0:
            print(f"[deploy_to_cloudflare] wrangler deploy FAILED (exit {result.returncode}):\n{result.stderr}")
        else:
            match = re.search(r"https://[a-zA-Z0-9\-]+\.pages\.dev", result.stdout)
            if match:
                live_url = match.group(0)
            print(f"[deploy_to_cloudflare] Deployed successfully: {live_url}")
    except subprocess.TimeoutExpired:
        print("[deploy_to_cloudflare] wrangler deploy timed out after 120s")
    except FileNotFoundError:
        print("[deploy_to_cloudflare] 'wrangler' command not found — is it installed and on PATH? Try: npm install -g wrangler")
    except Exception as e:
        print(f"[deploy_to_cloudflare] Unexpected error: {e}")

    return live_url


if __name__ == "__main__":
    sample_shop = {
        "name": "Shreeji General Stores",
        "category": "Grocery & Essentials",
        "hours": "8:00 AM - 9:00 PM (Mon-Sun)",
        "contact": "+91 98765 43210",
        "whatsapp": "919876543210",
        "subdomain": "shreeji-stores",
        "theme": "rival_shop",
        "_id": "sample123",
    }
    sample_products = [
        {"name": "Basmati Rice 5kg", "price": "450", "category": "Grocery", "photo_url": "https://via.placeholder.com/300x225"},
        {"name": "Sunflower Oil 1L", "price": "150", "category": "Grocery", "photo_url": "https://via.placeholder.com/300x225"},
    ]
    path = generate_site(sample_shop, sample_products)
    print(f"Generated site at: {path}")
    print(f"Would deploy to: {deploy_to_cloudflare(sample_shop['subdomain'], os.path.dirname(path))}")
