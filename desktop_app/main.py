"""
Digital Business Twin Generator - Desktop Input App
PyQt5, macOS-inspired dark/light theme, live preview panel
"""
import sys
import os
import json
import math
import time
import base64
import requests
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QFileDialog, QFormLayout, QTabWidget, QScrollArea, QFrame, QMessageBox,
    QComboBox, QInputDialog, QDialog, QGridLayout, QCheckBox, QStackedWidget, QButtonGroup,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRectF, QByteArray, QBuffer, QUrl
from PyQt5.QtGui import QFont, QPainter, QColor, QPixmap, QPainterPath, QLinearGradient, QBrush
try:
    from PyQt5.QtSvg import QSvgRenderer
except Exception:  # QtSvg missing -> logo just won't draw
    QSvgRenderer = None

# ---------------- Connection settings ----------------
# Saved in ~/.digitaltwin_desktop.json (edit via the "Connection" button) or env vars.
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".digitaltwin_desktop.json")
DEFAULT_SERVER = "https://digital-twin-t4gf.onrender.com"


def load_config():
    cfg = {"server": DEFAULT_SERVER, "api_key": "", "email": ""}
    try:
        with open(CONFIG_PATH) as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    cfg["server"] = os.environ.get("DT_BACKEND_URL", cfg["server"])
    cfg["api_key"] = os.environ.get("DT_API_KEY", cfg["api_key"])
    cfg["email"] = os.environ.get("DT_USER_EMAIL", cfg["email"])
    return cfg


CONFIG = load_config()
API_BASE = CONFIG["server"].rstrip("/") + "/api"


def auth_headers():
    h = {}
    if CONFIG.get("api_key") and CONFIG.get("email"):
        h["X-API-Key"] = CONFIG["api_key"]
        h["X-User-Email"] = CONFIG["email"]
    return h


LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6366f1"/><stop offset="1" stop-color="#14b8a6"/></linearGradient></defs><rect width="64" height="64" rx="16" fill="url(#g)"/><g opacity=".35" transform="translate(6 -5)" fill="none" stroke="#fff" stroke-width="2.4" stroke-linejoin="round"><path d="M14 26h32v22H14z"/><path d="M12 26l4-9h28l4 9"/></g><path d="M12 28h32v22a2 2 0 0 1-2 2H14a2 2 0 0 1-2-2z" fill="#fff" fill-opacity=".9"/><path d="M10 28l4.5-10h27L46 28a5 5 0 0 1-9.3 0 5 5 0 0 1-9.4 0 5 5 0 0 1-9.4 0A5 5 0 0 1 10 28z" fill="#fff"/><rect x="24" y="37" width="9" height="15" rx="2" fill="#6366f1"/><circle cx="49" cy="46" r="7" fill="#fff"/><path d="M45.5 46l2.5 2.5 4.5-5" fill="none" stroke="#14b8a6" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>"""


def logo_pixmap(size):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    if QSvgRenderer is not None:
        r = QSvgRenderer(QByteArray(LOGO_SVG.encode()))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p)
        p.end()
    return pm


class ApiWorker(QThread):
    """
    Runs a network request on a background thread so the UI never freezes
    or gets killed by the OS while waiting on a slow/unreachable server
    (e.g. MongoDB Atlas taking a while to respond, or the Flask server
    not running yet).
    """
    finished = pyqtSignal(bool, str, dict)  # success, message, response_json

    def __init__(self, method, url, json_data=None, files=None, timeout=45):
        super().__init__()
        self.method = method
        self.url = url
        self.json_data = json_data
        self.files = files
        self.timeout = timeout

    def run(self):
        try:
            hdr = auth_headers()
            if self.method == "POST":
                resp = requests.post(self.url, json=self.json_data, files=self.files, timeout=self.timeout, headers=hdr)
            elif self.method == "PUT":
                resp = requests.put(self.url, json=self.json_data, timeout=self.timeout, headers=hdr)
            elif self.method == "DELETE":
                resp = requests.delete(self.url, timeout=self.timeout, headers=hdr)
            else:
                resp = requests.get(self.url, timeout=self.timeout, headers=hdr)

            if resp.status_code in (200, 202):
                self.finished.emit(True, "ok", resp.json())
            else:
                try:
                    err = resp.json().get("error", f"Server returned {resp.status_code}")
                except Exception:
                    err = f"Server returned {resp.status_code}"
                self.finished.emit(False, err, {})

        except requests.exceptions.ConnectionError:
            self.finished.emit(False, "Can't reach the backend server. Check the Connection settings (server URL) and your internet.", {})
        except requests.exceptions.ReadTimeout:
            self.finished.emit(False, "Server took too long to respond (check your MongoDB connection/Atlas IP whitelist).", {})
        except Exception as e:
            self.finished.emit(False, f"Unexpected error: {e}", {})

DARK_QSS = """
QMainWindow, QWidget { background-color: #0b0c1e; color: #f3f4ff; font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif; }
QLineEdit, QTextEdit, QComboBox {
    background-color: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
    border-radius: 10px; padding: 9px; color: #f3f4ff;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #6366f1; }
QComboBox QAbstractItemView { background: #161834; color: #f3f4ff; selection-background-color: #6366f1; }
QPushButton {
    background-color: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #6366f1, stop:0.55 #7c3aed, stop:1 #14b8a6);
    color: white; border: none; border-radius: 10px; padding: 10px 18px; font-weight: 700;
}
QPushButton:hover { background-color: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #7578ff, stop:0.55 #8b4dfb, stop:1 #2dd4bf); }
QPushButton:pressed { background-color: #4f46e5; }
QPushButton:disabled { background-color: #2a2c52; color: #8a8fb3; }
QPushButton#secondary {
    background-color: rgba(255,255,255,0.06); color: #f3f4ff; border: 1px solid rgba(255,255,255,0.14);
}
QPushButton#secondary:hover { background-color: rgba(255,255,255,0.12); }
QLabel#heading { font-size: 20px; font-weight: 800; }
QLabel#muted { color: #aab0d8; font-size: 12px; }
QListWidget { background-color: #12142b; border: 1px solid rgba(255,255,255,0.12); border-radius: 14px; }
QTabWidget::pane { border: 1px solid rgba(255,255,255,0.12); border-radius: 14px; }
QTabBar::tab { background: #12142b; padding: 9px 18px; border-top-left-radius: 10px; border-top-right-radius: 10px; margin-right: 3px; }
QTabBar::tab:selected { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #6366f1, stop:1 #7c3aed); color: white; }
QScrollArea { border: none; }
"""

LIGHT_QSS = DARK_QSS.replace("#0b0c1e", "#f2f3ff").replace("#f3f4ff", "#15162e") \
    .replace("rgba(255,255,255,0.06)", "rgba(79,70,229,0.05)") \
    .replace("rgba(255,255,255,0.12)", "rgba(40,40,100,0.14)") \
    .replace("rgba(255,255,255,0.14)", "rgba(40,40,100,0.16)") \
    .replace("#12142b", "#ffffff").replace("#161834", "#ffffff").replace("#aab0d8", "#5a5f86")


class SliderLoader(QWidget):
    """Five liquid-filling sliders (port of the Uiverse 'Nawsome' loader)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(5 * 20 + 4 * 30, 84)
        self.t0 = time.time()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(33)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        now = time.time() - self.t0
        for i in range(5):
            x = i * 50
            rect = QRectF(x, 2, 20, 80)
            path = QPainterPath()
            path.addRoundedRect(rect, 10, 10)
            g = QLinearGradient(x, 0, x + 20, 0)
            g.setColorAt(0, QColor("#e4e6f7")); g.setColorAt(0.5, QColor("#ffffff")); g.setColorAt(1, QColor("#dfe2f5"))
            p.fillPath(path, QBrush(g))
            ph = ((now - 0.5 * i) % 2.5) / 2.5
            e = 0.5 - 0.5 * math.cos(2 * math.pi * ph)
            ty = 250 * (1 - e)
            if ty < 82:
                col = QColor.fromHsv(int((205 + 180 * ph) % 360), 190, 243)
                p.save(); p.setClipPath(path)
                p.setBrush(col); p.setPen(Qt.NoPen)
                p.drawEllipse(QRectF(x, 2 + ty, 20, 20))
                p.drawRect(QRectF(x, 2 + ty + 10, 20, 90))
                p.restore()


class GeneratingOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.card = QWidget(self)
        self.card.setStyleSheet("background:#ffffff; border-radius:22px;")
        self.card.setFixedSize(380, 250)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(24, 28, 24, 20)
        self.loader = SliderLoader()
        lay.addWidget(self.loader, 0, Qt.AlignHCenter)
        self.title = QLabel("Building your website…")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("color:#15162e; font-size:17px; font-weight:800; background:transparent;")
        self.sub = QLabel("Generating pages and publishing.\nThe first deploy can take a minute or two.")
        self.sub.setAlignment(Qt.AlignCenter)
        self.sub.setStyleSheet("color:#5a5f86; font-size:12px; background:transparent;")
        lay.addWidget(self.title); lay.addWidget(self.sub)
        self.hide()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(8, 9, 24, 170))

    def relayout(self):
        self.setGeometry(self.parent().rect())
        self.card.move((self.width() - self.card.width()) // 2, (self.height() - self.card.height()) // 2)


class ConnectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connection settings")
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        self.server = QLineEdit(CONFIG["server"])
        self.email = QLineEdit(CONFIG["email"])
        self.email.setPlaceholderText("the email you sign in with on the website")
        self.key = QLineEdit(CONFIG["api_key"])
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("DESKTOP_API_KEY from your Render environment")
        form.addRow("Server URL", self.server)
        form.addRow("Account email", self.email)
        form.addRow("Desktop API key", self.key)
        hint = QLabel("Use the same email as your web login so both apps edit the same shop.")
        hint.setObjectName("muted"); hint.setWordWrap(True)
        form.addRow(hint)
        save = QPushButton("Save"); save.clicked.connect(self.accept)
        form.addRow(save)

    def values(self):
        return {"server": self.server.text().strip().rstrip("/"), "email": self.email.text().strip(), "api_key": self.key.text().strip()}


EXTRA = """
QFrame#sidebar { background-color: #0e1026; border-right: 1px solid rgba(255,255,255,0.10); }
QPushButton#nav { background: transparent; color: #aab0d8; text-align: left; padding: 11px 14px; border-radius: 12px; font-weight: 600; }
QPushButton#nav:hover { background-color: rgba(255,255,255,0.07); color: #f3f4ff; }
QPushButton#nav:checked { background-color: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #6366f1, stop:0.6 #7c3aed, stop:1 #14b8a6); color: white; }
QFrame#card { background-color: #12142b; border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; }
QFrame#card QLabel { background: transparent; }
QFrame#themecard { background-color: #12142b; border: 2px solid rgba(255,255,255,0.12); border-radius: 16px; }
QFrame#themecard[selected="true"] { border: 2px solid #6366f1; }
QFrame#themecard QLabel { background: transparent; }
QLabel#stat { font-size: 26px; font-weight: 800; background: transparent; }
QLabel#title { font-size: 26px; font-weight: 800; background: transparent; }
QPushButton#danger { background-color: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.35); }
QPushButton#danger:hover { background-color: rgba(239,68,68,0.28); }
QTableWidget { background-color: #12142b; border: 1px solid rgba(255,255,255,0.12); border-radius: 12px; gridline-color: rgba(255,255,255,0.08); }
QHeaderView::section { background-color: #0e1026; color: #aab0d8; padding: 8px; border: none; font-weight: 700; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: rgba(160,165,220,0.35); border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.06); }
QCheckBox::indicator:checked { background-color: #6366f1; border: 1px solid #6366f1; }
"""
DARK_QSS = DARK_QSS + EXTRA
LIGHT_QSS = DARK_QSS.replace("#0b0c1e", "#f2f3ff").replace("#0e1026", "#ffffff").replace("#f3f4ff", "#15162e") \
    .replace("rgba(255,255,255,0.06)", "rgba(79,70,229,0.05)") \
    .replace("rgba(255,255,255,0.07)", "rgba(79,70,229,0.08)") \
    .replace("rgba(255,255,255,0.10)", "rgba(40,40,100,0.12)") \
    .replace("rgba(255,255,255,0.12)", "rgba(40,40,100,0.14)") \
    .replace("rgba(255,255,255,0.14)", "rgba(40,40,100,0.16)") \
    .replace("rgba(255,255,255,0.08)", "rgba(40,40,100,0.10)") \
    .replace("#12142b", "#ffffff").replace("#161834", "#ffffff").replace("#aab0d8", "#5a5f86")

THEMES = [
    ("rival_shop", "Rival", "Bold indigo, full storefront with cart & WhatsApp checkout", ("#4338ca", "#ec4899")),
    ("nami_shop", "Nami", "Calm slate blue, minimal paper-goods aesthetic", ("#475569", "#93c5fd")),
    ("fernweg_shop", "Fernweg", "Earthy rust + cream, warm travel-goods feel", ("#b45309", "#fde68a")),
]
DAYS = [("mon", "Monday"), ("tue", "Tuesday"), ("wed", "Wednesday"), ("thu", "Thursday"),
        ("fri", "Friday"), ("sat", "Saturday"), ("sun", "Sunday")]

_pix_cache = {}


class ImageLoader(QThread):
    done = pyqtSignal(str, QPixmap)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            r = requests.get(self.url, timeout=20)
            pm = QPixmap()
            if r.status_code == 200 and pm.loadFromData(r.content):
                self.done.emit(self.url, pm)
        except Exception:
            pass


def card():
    f = QFrame()
    f.setObjectName("card")
    return f


def title(text, sub=None):
    box = QVBoxLayout()
    t = QLabel(text); t.setObjectName("title")
    box.addWidget(t)
    if sub:
        s = QLabel(sub); s.setObjectName("muted"); s.setWordWrap(True)
        box.addWidget(s)
    box.setSpacing(4)
    return box


def page_scroll(inner):
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.NoFrame)
    sc.setWidget(inner)
    return sc


class Page(QWidget):
    def __init__(self):
        super().__init__()
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(32, 28, 32, 28)
        self.root.setSpacing(18)


def notify(parent, text, kind="info"):
    (QMessageBox.warning if kind == "warn" else QMessageBox.information)(parent, "Digital Twin", text)


# ---------------------------------------------------------------- pages
class OverviewPage(Page):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.root.addLayout(title("Overview", "Your shop at a glance."))
        row = QHBoxLayout(); row.setSpacing(14)
        self.stats = {}
        for key, label in [("products", "Products"), ("status", "Site status"), ("theme", "Theme")]:
            c = card(); v = QVBoxLayout(c); v.setContentsMargins(18, 14, 18, 14)
            l = QLabel(label); l.setObjectName("muted")
            val = QLabel("—"); val.setObjectName("stat")
            v.addWidget(l); v.addWidget(val)
            self.stats[key] = val
            row.addWidget(c)
        self.root.addLayout(row)

        c = card(); v = QVBoxLayout(c); v.setContentsMargins(20, 18, 20, 18); v.setSpacing(10)
        h = QLabel("Your live site"); h.setStyleSheet("font-size:15px; font-weight:800;")
        v.addWidget(h)
        self.url = QLineEdit(); self.url.setReadOnly(True); self.url.setPlaceholderText("Not generated yet")
        v.addWidget(self.url)
        btns = QHBoxLayout()
        self.gen_btn = QPushButton("Generate && Deploy Website")
        self.gen_btn.clicked.connect(win.generate_site)
        open_btn = QPushButton("Open site"); open_btn.setObjectName("secondary")
        open_btn.clicked.connect(self.open_site)
        copy_btn = QPushButton("Copy link"); copy_btn.setObjectName("secondary")
        copy_btn.clicked.connect(lambda: (QApplication.clipboard().setText(self.url.text()), None))
        for b in (self.gen_btn, open_btn, copy_btn):
            btns.addWidget(b)
        btns.addStretch()
        v.addLayout(btns)
        hint = QLabel("Saves nothing by itself — fill in Shop Info and Products first, then generate."); hint.setObjectName("muted")
        v.addWidget(hint)
        self.root.addWidget(c)
        self.root.addStretch()

    def open_site(self):
        u = self.url.text().strip()
        if u.startswith("http"):
            QDesktopServices.openUrl(QUrl(u.split(" ")[0]))
        else:
            notify(self, "Generate your site first.", "warn")

    def refresh(self):
        self.stats["products"].setText(str(len(self.win.products)))
        theme = (self.win.shop or {}).get("theme", "rival_shop")
        self.stats["theme"].setText(next((n for k, n, _, _ in THEMES if k == theme), "Rival"))
        live = self.win.live_url
        self.stats["status"].setText("🟢 Live" if live and "PLACEHOLDER" not in live else "⚪ Not live")
        if live:
            self.url.setText(live)


class ShopPage(Page):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.root.addLayout(title("Shop Info", "These details appear on your website."))
        c = card(); g = QGridLayout(c); g.setContentsMargins(20, 18, 20, 18); g.setHorizontalSpacing(16); g.setVerticalSpacing(10)
        self.f = {}
        fields = [("name", "Business name", ""), ("category", "Category", "e.g. Electronics"),
                  ("hours", "Working hours (summary)", "e.g. 9 AM – 9 PM"), ("contact", "Contact number", ""),
                  ("whatsapp", "WhatsApp number", "10 digits or with country code"),
                  ("subdomain", "Subdomain", "e.g. shreeji-stores"),
                  ("custom_domain", "Custom domain (optional)", "www.yourshop.com"),
                  ("discount_banner", "Offer banner (blank hides it)", "e.g. 20% off this week!")]
        for i, (key, label, ph) in enumerate(fields):
            r, col = divmod(i, 2)
            lab = QLabel(label); lab.setObjectName("muted")
            e = QLineEdit(); e.setPlaceholderText(ph)
            g.addWidget(lab, r * 2, col); g.addWidget(e, r * 2 + 1, col)
            self.f[key] = e
        self.language = QComboBox()
        self.language.addItem("English", "en"); self.language.addItem("हिन्दी", "hi")
        lab = QLabel("Language"); lab.setObjectName("muted")
        g.addWidget(lab, 8, 0); g.addWidget(self.language, 9, 0)
        self.root.addWidget(c)

        c2 = card(); v = QVBoxLayout(c2); v.setContentsMargins(20, 18, 20, 18); v.setSpacing(8)
        h = QLabel("Hours by day"); h.setStyleSheet("font-size:15px; font-weight:800;")
        v.addWidget(h)
        self.days = {}
        for key, label in DAYS:
            row = QHBoxLayout()
            n = QLabel(label); n.setFixedWidth(100)
            o = QLineEdit("9:00 AM"); o.setFixedWidth(120)
            cl = QLineEdit("9:00 PM"); cl.setFixedWidth(120)
            closed = QCheckBox("Closed")
            row.addWidget(n); row.addWidget(o); row.addWidget(QLabel("–")); row.addWidget(cl); row.addWidget(closed); row.addStretch()
            v.addLayout(row)
            self.days[key] = (o, cl, closed)
        self.root.addWidget(c2)

        save = QPushButton("Save shop info"); save.setFixedWidth(180)
        save.clicked.connect(self.save)
        self.root.addWidget(save)
        self.root.addStretch()

    def data(self):
        d = {k: e.text().strip() for k, e in self.f.items()}
        d["language"] = self.language.currentData()
        d["hours_by_day"] = {k: {"open": o.text().strip(), "close": c.text().strip(), "closed": ch.isChecked()}
                             for k, (o, c, ch) in self.days.items()}
        return d

    def load(self, shop):
        for k, e in self.f.items():
            e.setText(shop.get(k, "") or "")
        i = self.language.findData(shop.get("language", "en"))
        if i >= 0:
            self.language.setCurrentIndex(i)
        for k, (o, c, ch) in self.days.items():
            v = (shop.get("hours_by_day") or {}).get(k)
            if v:
                o.setText(v.get("open", "")); c.setText(v.get("close", "")); ch.setChecked(bool(v.get("closed")))

    def save(self):
        d = self.data()
        if not d["name"] or not d["subdomain"]:
            notify(self, "Business name and subdomain are required.", "warn")
            return
        d["theme"] = self.win.theme_key()
        self.w = ApiWorker("POST", f"{API_BASE}/shop", json_data=d, timeout=45)

        def done(ok, msg, _):
            if ok:
                self.win.load_existing()
                notify(self, "Saved! Now add products or generate your site.")
            else:
                notify(self, msg, "warn")
        self.w.finished.connect(done)
        self.w.start()


class ProductDialog(QDialog):
    def __init__(self, parent, product):
        super().__init__(parent)
        self.setWindowTitle("Edit product")
        self.setMinimumWidth(460)
        self.photos = list(product.get("photos") or ([product["photo_url"]] if product.get("photo_url") else []))
        form = QFormLayout(self)
        self.name = QLineEdit(product.get("name", ""))
        self.price = QLineEdit(str(product.get("price", "")))
        self.category = QLineEdit(product.get("category", "") or "")
        self.desc = QTextEdit(product.get("description", "") or ""); self.desc.setFixedHeight(90)
        form.addRow("Name", self.name); form.addRow("Price (₹)", self.price)
        form.addRow("Category", self.category); form.addRow("Description", self.desc)
        self.info = QLabel(f"{len(self.photos)} photo(s)")
        add = QPushButton("Add photo…"); add.setObjectName("secondary"); add.clicked.connect(self.add_photo)
        row = QHBoxLayout(); row.addWidget(self.info); row.addWidget(add)
        form.addRow("Photos", row)
        ok = QPushButton("Save changes"); ok.clicked.connect(self.accept)
        form.addRow(ok)

    def add_photo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose photo", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        self.up = ApiWorker("POST", f"{API_BASE}/upload-photo", files={"photo": open(path, "rb")}, timeout=90)

        def done(ok, msg, d):
            if ok:
                self.photos.append(d.get("photo_url", ""))
                self.info.setText(f"{len(self.photos)} photo(s)")
            else:
                notify(self, msg, "warn")
        self.up.finished.connect(done)
        self.up.start()

    def values(self):
        return {"name": self.name.text().strip(), "price": self.price.text().strip(), "category": self.category.text().strip(),
                "description": self.desc.toPlainText().strip(), "photos": self.photos,
                "photo_url": self.photos[0] if self.photos else ""}


class ProductsPage(Page):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.new_photos = []
        self.root.addLayout(title("Products", "Add what you sell. Drag rows to reorder."))
        c = card(); g = QGridLayout(c); g.setContentsMargins(20, 18, 20, 18); g.setHorizontalSpacing(14); g.setVerticalSpacing(8)
        self.name = QLineEdit(); self.name.setPlaceholderText("Product name")
        self.price = QLineEdit(); self.price.setPlaceholderText("Price (₹)")
        self.category = QLineEdit(); self.category.setPlaceholderText("Category")
        self.desc = QTextEdit(); self.desc.setPlaceholderText("Description (optional) — or let AI write it"); self.desc.setFixedHeight(80)
        g.addWidget(self.name, 0, 0); g.addWidget(self.price, 0, 1); g.addWidget(self.category, 0, 2)
        g.addWidget(self.desc, 1, 0, 1, 3)
        self.photo_label = QLabel("No photos chosen"); self.photo_label.setObjectName("muted")
        pick = QPushButton("Choose photos…"); pick.setObjectName("secondary"); pick.clicked.connect(self.choose)
        self.ai_btn = QPushButton("✨ AI suggest"); self.ai_btn.setObjectName("secondary"); self.ai_btn.clicked.connect(self.ai_suggest)
        self.add_btn = QPushButton("Add product"); self.add_btn.clicked.connect(self.add)
        row = QHBoxLayout(); row.addWidget(pick); row.addWidget(self.photo_label); row.addStretch(); row.addWidget(self.ai_btn); row.addWidget(self.add_btn)
        g.addLayout(row, 2, 0, 1, 3)
        self.root.addWidget(c)

        self.list = QListWidget()
        self.list.setDragDropMode(QListWidget.InternalMove)
        self.list.setSpacing(6)
        self.list.setMinimumHeight(260)
        self.list.model().rowsMoved.connect(self.reorder)
        self.root.addWidget(self.list, 1)

    # --- add
    def choose(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose photos", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if paths:
            self.new_photos = paths
            self.photo_label.setText(f"{len(paths)} photo(s) selected")

    def ai_suggest(self):
        name = self.name.text().strip()
        if not name:
            notify(self, "Enter the product name first.", "warn")
            return
        payload = {"name": name, "category": self.category.text().strip()}
        if self.new_photos:
            img = QImage(self.new_photos[0])
            if not img.isNull():
                img = img.scaled(900, 900, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                ba = QByteArray(); buf = QBuffer(ba); buf.open(QBuffer.WriteOnly); img.save(buf, "JPEG", 85)
                payload["image_base64"] = base64.b64encode(bytes(ba)).decode()
        self.ai_btn.setEnabled(False); self.ai_btn.setText("Writing…")
        self.aw = ApiWorker("POST", f"{API_BASE}/ai/describe", json_data=payload, timeout=90)

        def done(ok, msg, d):
            self.ai_btn.setEnabled(True); self.ai_btn.setText("✨ AI suggest")
            if ok:
                self.desc.setPlainText(d.get("description", ""))
            else:
                notify(self, msg, "warn")
        self.aw.finished.connect(done)
        self.aw.start()

    def add(self):
        name, price = self.name.text().strip(), self.price.text().strip()
        if not name or not price:
            notify(self, "Name and price are required.", "warn")
            return
        if not self.win.shop or not self.win.shop.get("_id"):
            notify(self, "Save your Shop Info first.", "warn")
            return
        self.add_btn.setEnabled(False); self.add_btn.setText("Uploading…")
        self._urls = []
        self._queue = list(self.new_photos)
        self._next_upload(name, price)

    def _next_upload(self, name, price):
        if not self._queue:
            return self._save_product(name, price)
        path = self._queue.pop(0)
        self.up = ApiWorker("POST", f"{API_BASE}/upload-photo", files={"photo": open(path, "rb")}, timeout=90)

        def done(ok, msg, d):
            if ok:
                self._urls.append(d.get("photo_url", ""))
                self._next_upload(name, price)
            else:
                self.add_btn.setEnabled(True); self.add_btn.setText("Add product")
                notify(self, "Photo upload failed: " + msg, "warn")
        self.up.finished.connect(done)
        self.up.start()

    def _save_product(self, name, price):
        body = {"name": name, "price": price, "category": self.category.text().strip(),
                "description": self.desc.toPlainText().strip(), "photos": self._urls,
                "photo_url": self._urls[0] if self._urls else ""}
        self.sw = ApiWorker("POST", f"{API_BASE}/product", json_data=body, timeout=45)

        def done(ok, msg, d):
            self.add_btn.setEnabled(True); self.add_btn.setText("Add product")
            if ok:
                body["_id"] = d.get("product_id")
                self.win.products.append(body)
                for w in (self.name, self.price, self.category):
                    w.clear()
                self.desc.clear(); self.new_photos = []; self.photo_label.setText("No photos chosen")
                self.render()
                self.win.refresh_all()
            else:
                notify(self, msg, "warn")
        self.sw.finished.connect(done)
        self.sw.start()

    # --- list
    def render(self):
        self.list.clear()
        for p in self.win.products:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, p.get("_id"))
            w = QWidget()
            h = QHBoxLayout(w); h.setContentsMargins(10, 8, 10, 8); h.setSpacing(12)
            thumb = QLabel(); thumb.setFixedSize(64, 64); thumb.setAlignment(Qt.AlignCenter)
            thumb.setStyleSheet("background:rgba(120,125,200,0.18); border-radius:10px; font-size:24px;")
            thumb.setText("📦")
            url = p.get("photo_url") or ((p.get("photos") or [None])[0])
            if url:
                self.load_thumb(thumb, url)
            h.addWidget(thumb)
            info = QVBoxLayout()
            n = QLabel(p.get("name", "")); n.setStyleSheet("font-weight:800; font-size:14px; background:transparent;")
            m = QLabel(f"₹{p.get('price', '')}  ·  {p.get('category') or 'No category'}  ·  {len(p.get('photos') or [])} photo(s)")
            m.setObjectName("muted")
            info.addWidget(n); info.addWidget(m)
            h.addLayout(info, 1)
            e = QPushButton("Edit"); e.setObjectName("secondary"); e.clicked.connect(lambda _, pr=p: self.edit(pr))
            d = QPushButton("Delete"); d.setObjectName("danger"); d.clicked.connect(lambda _, pr=p: self.delete(pr))
            h.addWidget(e); h.addWidget(d)
            it.setSizeHint(w.sizeHint())
            self.list.addItem(it)
            self.list.setItemWidget(it, w)

    def load_thumb(self, label, url):
        def apply(pm):
            label.setPixmap(pm.scaled(64, 64, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        if url in _pix_cache:
            return apply(_pix_cache[url])
        ld = ImageLoader(url)

        def done(u, pm):
            _pix_cache[u] = pm
            try:
                apply(pm)
            except RuntimeError:
                pass
        ld.done.connect(done)
        self.win.loaders.append(ld)
        ld.start()

    def edit(self, p):
        dlg = ProductDialog(self, p)
        if dlg.exec_():
            v = dlg.values()
            self.ew = ApiWorker("PUT", f"{API_BASE}/product/{p['_id']}", json_data=v, timeout=45)

            def done(ok, msg, _):
                if ok:
                    p.update(v); self.render()
                else:
                    notify(self, msg, "warn")
            self.ew.finished.connect(done)
            self.ew.start()

    def delete(self, p):
        if QMessageBox.question(self, "Delete", f"Delete “{p.get('name')}”?") != QMessageBox.Yes:
            return
        self.dw = ApiWorker("DELETE", f"{API_BASE}/product/{p['_id']}", timeout=45)

        def done(ok, msg, _):
            if ok:
                self.win.products = [x for x in self.win.products if x.get("_id") != p.get("_id")]
                self.render(); self.win.refresh_all()
            else:
                notify(self, msg, "warn")
        self.dw.finished.connect(done)
        self.dw.start()

    def reorder(self, *_):
        ids = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        by = {p.get("_id"): p for p in self.win.products}
        self.win.products = [by[i] for i in ids if i in by]
        self.rw = ApiWorker("PUT", f"{API_BASE}/products/reorder", json_data={"product_ids": ids}, timeout=45)
        self.rw.start()


class ThemePage(Page):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.selected = "rival_shop"
        self.root.addLayout(title("Website theme", "Pick how your generated website looks, then apply and regenerate."))
        row = QHBoxLayout(); row.setSpacing(16)
        self.cards = {}
        for key, name, desc, (c1, c2) in THEMES:
            f = QFrame(); f.setObjectName("themecard"); f.setCursor(Qt.PointingHandCursor)
            v = QVBoxLayout(f); v.setContentsMargins(14, 14, 14, 14)
            sw = QLabel(); sw.setFixedHeight(130)
            sw.setStyleSheet(f"border-radius:10px; background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {c1}, stop:1 {c2});")
            v.addWidget(sw)
            n = QLabel(name); n.setStyleSheet("font-size:15px; font-weight:800;")
            d = QLabel(desc); d.setObjectName("muted"); d.setWordWrap(True)
            v.addWidget(n); v.addWidget(d)
            f.mousePressEvent = lambda e, k=key: self.select(k)
            self.cards[key] = f
            row.addWidget(f)
        self.root.addLayout(row)
        b = QPushButton("Apply theme"); b.setFixedWidth(160); b.clicked.connect(self.apply)
        self.root.addWidget(b)
        n = QLabel("This saves your choice. Go to Overview and click Generate && Deploy to publish it."); n.setObjectName("muted")
        self.root.addWidget(n)
        self.root.addStretch()
        self.select("rival_shop")

    def select(self, key):
        self.selected = key
        for k, f in self.cards.items():
            f.setProperty("selected", "true" if k == key else "false")
            f.style().unpolish(f); f.style().polish(f)

    def apply(self):
        if not self.win.shop or not self.win.shop.get("_id"):
            notify(self, "Save your Shop Info first.", "warn")
            return
        self.w = ApiWorker("POST", f"{API_BASE}/shop", json_data={"theme": self.selected}, timeout=45)

        def done(ok, msg, _):
            if ok:
                self.win.shop["theme"] = self.selected
                self.win.refresh_all()
                notify(self, "Theme saved. Generate & deploy from the Overview page to publish it.")
            else:
                notify(self, msg, "warn")
        self.w.finished.connect(done)
        self.w.start()


class SharePage(Page):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.qr_png = None
        self.root.addLayout(title("Share & QR", "Get customers to your site — online and offline."))
        c = card(); h = QHBoxLayout(c); h.setContentsMargins(20, 18, 20, 18); h.setSpacing(20)
        self.qr = QLabel("QR code appears here"); self.qr.setFixedSize(220, 220); self.qr.setAlignment(Qt.AlignCenter)
        self.qr.setStyleSheet("background:white; color:#555; border-radius:14px;")
        h.addWidget(self.qr)
        v = QVBoxLayout()
        t = QLabel("Print it on your counter, menu or packaging. Scans are counted in your dashboard.")
        t.setObjectName("muted"); t.setWordWrap(True); v.addWidget(t)
        g = QPushButton("Generate QR code"); g.clicked.connect(self.gen_qr)
        s = QPushButton("Save QR as PNG…"); s.setObjectName("secondary"); s.clicked.connect(self.save_qr)
        v.addWidget(g); v.addWidget(s); v.addStretch()
        h.addLayout(v, 1)
        self.root.addWidget(c)

        c2 = card(); v2 = QVBoxLayout(c2); v2.setContentsMargins(20, 18, 20, 18); v2.setSpacing(10)
        hh = QLabel("WhatsApp catalog"); hh.setStyleSheet("font-size:15px; font-weight:800;")
        v2.addWidget(hh)
        self.msg = QTextEdit(); self.msg.setReadOnly(True); self.msg.setPlaceholderText("Click “Build message” to create a shareable catalog."); self.msg.setFixedHeight(150)
        v2.addWidget(self.msg)
        r = QHBoxLayout()
        b1 = QPushButton("Build message"); b1.clicked.connect(self.build)
        b2 = QPushButton("Copy"); b2.setObjectName("secondary"); b2.clicked.connect(lambda: QApplication.clipboard().setText(self.msg.toPlainText()))
        b3 = QPushButton("Share on WhatsApp"); b3.setObjectName("secondary"); b3.clicked.connect(self.share)
        for b in (b1, b2, b3):
            r.addWidget(b)
        r.addStretch()
        v2.addLayout(r)
        self.link = None
        self.root.addWidget(c2)
        self.root.addStretch()

    def gen_qr(self):
        live = self.win.live_url
        if not live or "PLACEHOLDER" in live:
            notify(self, "Generate your site first so the QR has a real link.", "warn")
            return
        self.w = ApiWorker("POST", f"{API_BASE}/generate-qr", json_data={"site_url": live.split(" ")[0], "shop_id": (self.win.shop or {}).get("_id", "")}, timeout=45)

        def done(ok, msg, d):
            if not ok:
                return notify(self, msg, "warn")
            raw = base64.b64decode(d["qr_code"].split(",", 1)[1])
            self.qr_png = raw
            pm = QPixmap(); pm.loadFromData(raw)
            self.qr.setPixmap(pm.scaled(210, 210, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.w.finished.connect(done)
        self.w.start()

    def save_qr(self):
        if not self.qr_png:
            return notify(self, "Generate the QR first.", "warn")
        path, _ = QFileDialog.getSaveFileName(self, "Save QR", "shop-qr.png", "PNG (*.png)")
        if path:
            with open(path, "wb") as f:
                f.write(self.qr_png)

    def build(self):
        self.w2 = ApiWorker("POST", f"{API_BASE}/generate-whatsapp-catalog", json_data={}, timeout=45)

        def done(ok, msg, d):
            if ok:
                self.msg.setPlainText(d.get("message", "")); self.link = d.get("whatsapp_link")
            else:
                notify(self, msg, "warn")
        self.w2.finished.connect(done)
        self.w2.start()

    def share(self):
        if self.link:
            QDesktopServices.openUrl(QUrl(self.link))
        else:
            notify(self, "Build the message first.", "warn")


class OrdersPage(Page):
    def __init__(self, win):
        super().__init__()
        self.win = win
        top = QHBoxLayout()
        top.addLayout(title("Order inbox", "Orders placed through your website's WhatsApp checkout."))
        top.addStretch()
        r = QPushButton("Refresh"); r.setObjectName("secondary"); r.clicked.connect(self.load)
        top.addWidget(r, 0, Qt.AlignTop)
        self.root.addLayout(top)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Customer", "Items / notes", "Placed", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setWordWrap(True)
        self.root.addWidget(self.table, 1)

    def load(self):
        self.w = ApiWorker("GET", f"{API_BASE}/orders", timeout=45)

        def done(ok, msg, d):
            if not ok:
                return notify(self, msg, "warn")
            orders = d.get("orders", [])
            self.table.setRowCount(len(orders))
            for i, o in enumerate(orders):
                items = "\n".join(f"• {x.get('name')} ×{x.get('qty', 1)}" for x in o.get("items", []))
                if o.get("notes"):
                    items += f"\nNote: {o['notes']}"
                self.table.setItem(i, 0, QTableWidgetItem(f"{o.get('customer_name') or 'Unknown'}\n{o.get('customer_phone', '')}"))
                self.table.setItem(i, 1, QTableWidgetItem(items))
                self.table.setItem(i, 2, QTableWidgetItem(str(o.get("created_at", ""))[:16]))
                cb = QComboBox()
                for s in ("new", "confirmed", "done"):
                    cb.addItem(s.capitalize(), s)
                cb.setCurrentIndex(max(0, cb.findData(o.get("status", "new"))))
                cb.currentIndexChanged.connect(lambda _, c=cb, oid=o["_id"]: self.set_status(oid, c.currentData()))
                self.table.setCellWidget(i, 3, cb)
                self.table.setRowHeight(i, 78)
            self.table.setColumnWidth(0, 200); self.table.setColumnWidth(2, 140)
        self.w.finished.connect(done)
        self.w.start()

    def set_status(self, oid, status):
        self.sw = ApiWorker("PUT", f"{API_BASE}/orders/{oid}", json_data={"status": status}, timeout=45)
        self.sw.start()


# ---------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digital Twin")
        self.resize(1180, 760)
        self.dark_mode = True
        self.shop = None
        self.products = []
        self.live_url = ""
        self.loaders = []

        central = QWidget()
        outer = QHBoxLayout(central); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        side = QFrame(); side.setObjectName("sidebar"); side.setFixedWidth(232)
        sv = QVBoxLayout(side); sv.setContentsMargins(14, 18, 14, 14); sv.setSpacing(4)
        brand = QHBoxLayout()
        logo = QLabel(); logo.setPixmap(logo_pixmap(34)); logo.setFixedSize(34, 34)
        nm = QLabel("Digital Twin"); nm.setStyleSheet("font-size:16px; font-weight:800; background:transparent;")
        brand.addWidget(logo); brand.addWidget(nm); brand.addStretch()
        sv.addLayout(brand); sv.addSpacing(16)

        self.stack = QStackedWidget()
        self.pages = {
            "overview": OverviewPage(self), "shop": ShopPage(self), "products": ProductsPage(self),
            "theme": ThemePage(self), "share": SharePage(self), "orders": OrdersPage(self),
        }
        self.nav = {}
        group = QButtonGroup(self); group.setExclusive(True)
        for key, label in [("overview", "📊  Overview"), ("shop", "🏬  Shop Info"), ("products", "📦  Products"),
                           ("theme", "🎨  Theme"), ("share", "🔗  Share & QR"), ("orders", "📥  Order Inbox")]:
            b = QPushButton(label.replace("&", "&&")); b.setObjectName("nav"); b.setCheckable(True)
            b.clicked.connect(lambda _, k=key: self.show_page(k))
            group.addButton(b); sv.addWidget(b); self.nav[key] = b
            self.stack.addWidget(page_scroll(self.pages[key]))
        sv.addStretch()
        self.server_lbl = QLabel(CONFIG["server"].replace("https://", "")); self.server_lbl.setObjectName("muted")
        self.server_lbl.setStyleSheet("background:transparent; font-size:11px;")
        sv.addWidget(self.server_lbl)
        cb = QPushButton("⚙  Connection"); cb.setObjectName("secondary"); cb.clicked.connect(self.open_connection)
        tb = QPushButton("◐  Toggle theme"); tb.setObjectName("secondary"); tb.clicked.connect(self.toggle_theme)
        sv.addWidget(cb); sv.addWidget(tb)

        outer.addWidget(side)
        outer.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.overlay = GeneratingOverlay(central)
        self.apply_theme()
        self.nav["overview"].setChecked(True)
        self.load_existing()

    # helpers
    def theme_key(self):
        return (self.shop or {}).get("theme") or "rival_shop"

    def show_page(self, key):
        self.stack.setCurrentWidget(self.stack.widget(list(self.pages).index(key)))
        if key == "orders":
            self.pages["orders"].load()

    def refresh_all(self):
        self.pages["overview"].refresh()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "overlay"):
            self.overlay.relayout()

    def load_existing(self):
        self.lw = ApiWorker("GET", f"{API_BASE}/shop", timeout=60)

        def done(ok, msg, d):
            if not ok:
                self.server_lbl.setText("⚠ " + msg[:60])
                return
            self.shop = d.get("shop")
            self.products = d.get("products", [])
            self.live_url = d.get("live_url", "") or ""
            if self.shop:
                self.pages["shop"].load(self.shop)
                self.pages["theme"].select(self.shop.get("theme", "rival_shop"))
            self.pages["products"].render()
            self.refresh_all()
        self.lw.finished.connect(done)
        self.lw.start()

    def open_connection(self):
        global API_BASE
        dlg = ConnectionDialog(self)
        if dlg.exec_():
            v = dlg.values()
            CONFIG.update(v)
            API_BASE = CONFIG["server"].rstrip("/") + "/api"
            self.server_lbl.setText(CONFIG["server"].replace("https://", ""))
            try:
                with open(CONFIG_PATH, "w") as f:
                    json.dump(v, f)
            except Exception:
                pass
            self.load_existing()

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def apply_theme(self):
        self.setStyleSheet(DARK_QSS if self.dark_mode else LIGHT_QSS)

    # generate
    def generate_site(self):
        if not self.shop or not self.shop.get("_id"):
            notify(self, "Save your Shop Info first (Shop Info → Save).", "warn")
            return
        btn = self.pages["overview"].gen_btn
        btn.setEnabled(False)
        self.overlay.relayout(); self.overlay.show(); self.overlay.raise_()
        self.poll_count = 0

        def finish():
            self.overlay.hide(); btn.setEnabled(True)

        def result(url):
            finish()
            self.live_url = url
            self.refresh_all()
            if "PLACEHOLDER" in url:
                notify(self, f"Site generated, but Cloudflare isn't configured on the server:\n{url}", "warn")
            else:
                notify(self, f"Your site is live at:\n{url}")

        def poll():
            self.poll_count += 1
            if self.poll_count > 120:
                finish(); return notify(self, "Still deploying — check the server logs.", "warn")
            self.sw = ApiWorker("GET", f"{API_BASE}/generate-site/status", timeout=45)

            def st(ok, msg, d):
                if not ok:
                    return QTimer.singleShot(3000, poll)
                s = d.get("state")
                if s == "done":
                    result(d.get("live_url", ""))
                elif s == "error":
                    finish(); notify(self, d.get("error", "Unknown error"), "warn")
                else:
                    QTimer.singleShot(3000, poll)
            self.sw.finished.connect(st)
            self.sw.start()

        self.gw = ApiWorker("POST", f"{API_BASE}/generate-site", timeout=60)

        def started(ok, msg, d):
            if not ok:
                finish(); return notify(self, msg, "warn")
            QTimer.singleShot(3000, poll)
        self.gw.finished.connect(started)
        self.gw.start()


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(logo_pixmap(256)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()