"""
Digital Business Twin Generator - Desktop Input App
PyQt5, macOS-inspired dark/light theme, live preview panel
"""
import sys
import os
import json
import math
import time
import requests
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QFileDialog, QFormLayout, QTabWidget, QScrollArea, QFrame, QMessageBox,
    QComboBox, QInputDialog, QDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRectF, QByteArray
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


class TrafficLightBar(QWidget):
    def __init__(self, title, on_theme_toggle, on_connection):
        super().__init__()
        layout = QHBoxLayout()
        layout.setContentsMargins(16, 10, 16, 10)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(30))
        logo.setFixedSize(30, 30)
        layout.addWidget(logo)
        name = QLabel("Digital Twin")
        name.setStyleSheet("font-size:16px; font-weight:800;")
        layout.addWidget(name)
        layout.addStretch()
        title_label = QLabel(title)
        title_label.setObjectName("muted")
        layout.addWidget(title_label)
        layout.addStretch()

        conn_btn = QPushButton("⚙ Connection")
        conn_btn.setObjectName("secondary")
        conn_btn.clicked.connect(on_connection)
        layout.addWidget(conn_btn)
        toggle_btn = QPushButton("Toggle Theme")
        toggle_btn.setObjectName("secondary")
        toggle_btn.clicked.connect(on_theme_toggle)
        layout.addWidget(toggle_btn)
        self.setLayout(layout)


class BusinessInfoTab(QWidget):
    def __init__(self, preview_callback):
        super().__init__()
        self.preview_callback = preview_callback
        layout = QFormLayout()
        layout.setSpacing(12)

        self.name_input = QLineEdit()
        self.category_input = QLineEdit()
        self.hours_input = QLineEdit()
        self.contact_input = QLineEdit()
        self.whatsapp_input = QLineEdit()
        self.subdomain_input = QLineEdit()
        self.subdomain_input.setPlaceholderText("e.g. shreeji-stores")
        self.discount_banner_input = QLineEdit()
        self.discount_banner_input.setPlaceholderText("e.g. 20% off this week! (leave blank to hide)")
        self.custom_domain_input = QLineEdit()
        self.custom_domain_input.setPlaceholderText("Optional — www.yourshop.com")

        self.theme_dropdown = QComboBox()
        self.theme_dropdown.addItem("Rival — Bold indigo storefront with cart & WhatsApp checkout", "rival_shop")
        self.theme_dropdown.addItem("Nami — Calm slate blue, minimal paper-goods feel", "nami_shop")
        self.theme_dropdown.addItem("Fernweg — Earthy rust + cream, warm travel-goods feel", "fernweg_shop")
        self.theme_dropdown.currentIndexChanged.connect(self.preview_callback)

        for field in [self.name_input, self.category_input, self.hours_input,
                      self.contact_input, self.whatsapp_input, self.subdomain_input]:
            field.textChanged.connect(self.preview_callback)

        layout.addRow(QLabel("Business Name"), self.name_input)
        layout.addRow(QLabel("Category"), self.category_input)
        layout.addRow(QLabel("Working Hours"), self.hours_input)
        layout.addRow(QLabel("Contact Number"), self.contact_input)
        layout.addRow(QLabel("WhatsApp Number"), self.whatsapp_input)
        layout.addRow(QLabel("Desired Subdomain"), self.subdomain_input)
        layout.addRow(QLabel("Discount/Offer Banner"), self.discount_banner_input)
        layout.addRow(QLabel("Custom Domain"), self.custom_domain_input)
        layout.addRow(QLabel("Website Theme"), self.theme_dropdown)

        save_btn = QPushButton("Save Business Info")
        save_btn.clicked.connect(self.save_shop)
        self.save_btn_ref = save_btn
        layout.addRow(save_btn)

        self.setLayout(layout)

    def get_data(self):
        return {
            "name": self.name_input.text(),
            "category": self.category_input.text(),
            "hours": self.hours_input.text(),
            "contact": self.contact_input.text(),
            "whatsapp": self.whatsapp_input.text(),
            "subdomain": self.subdomain_input.text(),
            "discount_banner": self.discount_banner_input.text(),
            "custom_domain": self.custom_domain_input.text(),
            "theme": self.theme_dropdown.currentData()
        }

    def load_data(self, shop):
        """Populate fields from an existing shop record (e.g. after fetching from server)."""
        if not shop:
            return
        self.name_input.setText(shop.get("name") or "")
        self.category_input.setText(shop.get("category") or "")
        self.hours_input.setText(shop.get("hours") or "")
        self.contact_input.setText(shop.get("contact") or "")
        self.whatsapp_input.setText(shop.get("whatsapp") or "")
        self.subdomain_input.setText(shop.get("subdomain") or "")
        self.discount_banner_input.setText(shop.get("discount_banner") or "")
        self.custom_domain_input.setText(shop.get("custom_domain") or "")
        theme = shop.get("theme", "rival_shop")
        idx = self.theme_dropdown.findData(theme)
        if idx >= 0:
            self.theme_dropdown.setCurrentIndex(idx)

    def save_shop(self):
        self.save_btn_ref.setEnabled(False)
        self.save_btn_ref.setText("Saving...")

        self.worker = ApiWorker("POST", f"{API_BASE}/shop", json_data=self.get_data(), timeout=45)
        self.worker.finished.connect(self.on_save_finished)
        self.worker.start()

    def on_save_finished(self, success, message, data):
        self.save_btn_ref.setEnabled(True)
        self.save_btn_ref.setText("Save Business Info")
        if success:
            QMessageBox.information(self, "Saved", "Business info saved successfully.")
        else:
            QMessageBox.warning(self, "Error", message)


class ProductsTab(QWidget):
    def __init__(self, preview_callback):
        super().__init__()
        self.preview_callback = preview_callback
        self.products = []

        layout = QVBoxLayout()
        form_layout = QFormLayout()

        self.pname = QLineEdit()
        self.pprice = QLineEdit()
        self.pcategory = QLineEdit()
        self.pdescription = QTextEdit()
        self.pdescription.setFixedHeight(60)
        self.pdescription.setPlaceholderText("Optional — shown on the product page")
        self.pphoto_path = QLineEdit()
        self.pphoto_path.setReadOnly(True)

        browse_btn = QPushButton("Choose Photo")
        browse_btn.setObjectName("secondary")
        browse_btn.clicked.connect(self.choose_photo)

        photo_row = QHBoxLayout()
        photo_row.addWidget(self.pphoto_path)
        photo_row.addWidget(browse_btn)

        form_layout.addRow(QLabel("Product/Service Name"), self.pname)
        form_layout.addRow(QLabel("Price (₹)"), self.pprice)
        form_layout.addRow(QLabel("Category"), self.pcategory)
        form_layout.addRow(QLabel("Description"), self.pdescription)
        form_layout.addRow(QLabel("Photo"), photo_row)

        add_btn = QPushButton("Add Product")
        add_btn.clicked.connect(self.add_product)
        form_layout.addRow(add_btn)

        layout.addLayout(form_layout)

        layout.addWidget(QLabel("Current Catalog:"))
        self.product_list = QListWidget()
        layout.addWidget(self.product_list)

        self.setLayout(layout)

    def choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Photo", "", "Images (*.png *.jpg *.jpeg)")
        if path:
            self.pphoto_path.setText(path)

    def add_product(self):
        if not self.pname.text() or not self.pprice.text():
            QMessageBox.warning(self, "Missing Info", "Product name and price are required.")
            return

        name = self.pname.text()
        price = self.pprice.text()
        category = self.pcategory.text()
        description = self.pdescription.toPlainText()
        photo_path = self.pphoto_path.text()

        self.pname.clear(); self.pprice.clear(); self.pcategory.clear()
        self.pdescription.clear(); self.pphoto_path.clear()

        # Save to backend first (so we get a real product_id for Edit/Delete),
        # uploading the photo first if one was chosen.
        if photo_path:
            self.upload_then_save(photo_path, name, price, category, description)
        else:
            self.save_product_to_backend(name, price, category, description, "")

    def upload_then_save(self, local_path, name, price, category, description):
        try:
            with open(local_path, "rb") as f:
                file_bytes = f.read()
        except Exception:
            self.save_product_to_backend(name, price, category, description, "")
            return

        import io
        files = {"photo": (local_path.split("/")[-1], io.BytesIO(file_bytes))}
        self.photo_worker = ApiWorker("POST", f"{API_BASE}/upload-photo", files=files, timeout=45)

        def on_uploaded(success, message, data):
            photo_url = data.get("photo_url", "") if success else ""
            self.save_product_to_backend(name, price, category, description, photo_url)

        self.photo_worker.finished.connect(on_uploaded)
        self.photo_worker.start()

    def save_product_to_backend(self, name, price, category, description, photo_url):
        self.add_worker = ApiWorker(
            "POST", f"{API_BASE}/product",
            json_data={
                "name": name, "price": price, "category": category,
                "description": description, "photo_url": photo_url,
                "photos": [photo_url] if photo_url else []
            },
            timeout=45
        )

        def on_saved(success, message, data):
            if not success:
                QMessageBox.warning(self, "Error", message)
                return
            product = {
                "id": data.get("product_id"),
                "name": name, "price": price, "category": category,
                "description": description, "photo_url": photo_url
            }
            self.products.append(product)
            self.render_product_row(product)
            self.preview_callback()

        self.add_worker.finished.connect(on_saved)
        self.add_worker.start()

    def render_product_row(self, product):
        row_widget = QWidget()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(4, 2, 4, 2)

        label = QLabel(f"{product['name']} — ₹{product['price']} ({product['category'] or 'General'})")
        row_layout.addWidget(label)
        row_layout.addStretch()

        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("secondary")
        edit_btn.setFixedWidth(60)
        edit_btn.clicked.connect(lambda: self.edit_product(product, label))
        row_layout.addWidget(edit_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setObjectName("secondary")
        delete_btn.setFixedWidth(70)
        row_layout.addWidget(delete_btn)

        row_widget.setLayout(row_layout)

        list_item = QListWidgetItem()
        list_item.setSizeHint(row_widget.sizeHint())
        self.product_list.addItem(list_item)
        self.product_list.setItemWidget(list_item, row_widget)

        delete_btn.clicked.connect(lambda: self.delete_product(product, list_item))

    def edit_product(self, product, label_ref):
        new_name, ok1 = QInputDialog.getText(self, "Edit Product", "Name:", text=product["name"])
        if not ok1:
            return
        new_price, ok2 = QInputDialog.getText(self, "Edit Product", "Price (₹):", text=str(product["price"]))
        if not ok2:
            return
        new_category, ok3 = QInputDialog.getText(self, "Edit Product", "Category:", text=product["category"])
        if not ok3:
            return

        self.edit_worker = ApiWorker(
            "PUT", f"{API_BASE}/product/{product['id']}",
            json_data={"name": new_name, "price": new_price, "category": new_category},
            timeout=45
        )

        def on_updated(success, message, data):
            if not success:
                QMessageBox.warning(self, "Error", message)
                return
            product["name"] = new_name
            product["price"] = new_price
            product["category"] = new_category
            label_ref.setText(f"{new_name} — ₹{new_price} ({new_category or 'General'})")
            self.preview_callback()

        self.edit_worker.finished.connect(on_updated)
        self.edit_worker.start()

    def delete_product(self, product, list_item_ref):
        confirm = QMessageBox.question(
            self, "Delete Product", f"Delete '{product['name']}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        self.delete_worker = ApiWorker("DELETE", f"{API_BASE}/product/{product['id']}", timeout=45)

        def on_deleted(success, message, data):
            if not success:
                QMessageBox.warning(self, "Error", message)
                return
            self.products.remove(product)
            row = self.product_list.row(list_item_ref)
            self.product_list.takeItem(row)
            self.preview_callback()

        self.delete_worker.finished.connect(on_deleted)
        self.delete_worker.start()


class LivePreviewPanel(QWidget):
    """Simple text-based live preview summary (a full HTML preview would embed QWebEngineView)."""
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        heading = QLabel("Live Preview")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        note = QLabel("This panel updates as you fill in business info and add products.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.preview_box = QTextEdit()
        self.preview_box.setReadOnly(True)
        layout.addWidget(self.preview_box)

        self.setLayout(layout)

    def update_preview(self, business_tab, products_tab):
        data = business_tab.get_data()
        lines = [
            f"🏬  {data['name'] or '[Business Name]'}",
            f"📂  {data['category'] or '[Category]'}",
            f"🕒  {data['hours'] or '[Working Hours]'}",
            f"📞  {data['contact'] or '[Contact]'}",
            f"💬  {data['whatsapp'] or '[WhatsApp]'}",
            f"🌐  {data['subdomain'] or '[subdomain]'}.yourdomain.dpdns.org",
            "",
            "── Catalog ──",
        ]
        if products_tab.products:
            for p in products_tab.products:
                lines.append(f"  • {p['name']} — ₹{p['price']}")
        else:
            lines.append("  (no products added yet)")

        self.preview_box.setPlainText("\n".join(lines))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digital Twin — Business Setup")
        self.resize(1000, 640)
        self.dark_mode = True

        central = QWidget()
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.titlebar = TrafficLightBar("desktop · " + CONFIG["server"].replace("https://", ""), self.toggle_theme, self.open_connection)
        outer_layout.addWidget(self.titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(16)

        # Left: tabs (business info + products)
        self.tabs = QTabWidget()
        self.business_tab = BusinessInfoTab(self.refresh_preview)
        self.products_tab = ProductsTab(self.refresh_preview)
        self.tabs.addTab(self.business_tab, "Business Info")
        self.tabs.addTab(self.products_tab, "Products / Catalog")

        left_wrapper = QScrollArea()
        left_wrapper.setWidgetResizable(True)
        left_wrapper.setWidget(self.tabs)

        # Right: live preview
        self.preview_panel = LivePreviewPanel()

        body.addWidget(left_wrapper, 3)
        body.addWidget(self.preview_panel, 2)

        outer_layout.addLayout(body)

        # Bottom action bar
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(16, 0, 16, 16)
        generate_btn = QPushButton("Generate && Deploy Website")
        generate_btn.clicked.connect(self.generate_site)
        self.generate_btn_ref = generate_btn
        action_bar.addStretch()
        action_bar.addWidget(generate_btn)
        outer_layout.addLayout(action_bar)

        central.setLayout(outer_layout)
        self.setCentralWidget(central)

        self.overlay = GeneratingOverlay(central)
        self.apply_theme()
        self.load_existing_shop()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "overlay"):
            self.overlay.relayout()

    def open_connection(self):
        global API_BASE
        dlg = ConnectionDialog(self)
        if dlg.exec_():
            v = dlg.values()
            CONFIG.update(v)
            API_BASE = CONFIG["server"].rstrip("/") + "/api"
            try:
                with open(CONFIG_PATH, "w") as f:
                    json.dump(v, f)
            except Exception:
                pass
            QMessageBox.information(self, "Saved", "Connection saved. Restart the app to reload your shop data.")

    def load_existing_shop(self):
        """Pulls any previously saved shop + products from the backend on startup,
        so the desktop app isn't always blank if you already saved data via
        the web dashboard (or a previous desktop session)."""
        self.load_worker = ApiWorker("GET", f"{API_BASE}/shop", timeout=45)

        def on_loaded(success, message, data):
            if not success:
                return  # silently skip — backend may just not be running yet
            shop = data.get("shop")
            products = data.get("products", [])
            if shop:
                self.business_tab.load_data(shop)
            for p in products:
                p["id"] = p.get("_id")
                self.products_tab.products.append(p)
                self.products_tab.render_product_row(p)
            self.refresh_preview()

        self.load_worker.finished.connect(on_loaded)
        self.load_worker.start()

    def refresh_preview(self):
        self.preview_panel.update_preview(self.business_tab, self.products_tab)

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def apply_theme(self):
        self.setStyleSheet(DARK_QSS if self.dark_mode else LIGHT_QSS)

    def generate_site(self):
        data = self.business_tab.get_data()
        if not data["name"] or not data["subdomain"]:
            QMessageBox.warning(self, "Missing Info", "Business name and subdomain are required before generating.")
            return

        self.generate_btn_ref.setEnabled(False)
        self.generate_btn_ref.setText("Generating…")
        self.overlay.relayout(); self.overlay.show(); self.overlay.raise_()
        self.poll_count = 0

        def finish():
            self.overlay.hide()
            self.generate_btn_ref.setEnabled(True)
            self.generate_btn_ref.setText("Generate && Deploy Website")

        def show_result(live_url):
            finish()
            if "PLACEHOLDER" in live_url:
                QMessageBox.warning(
                    self, "Generated (not deployed)",
                    f"Site generated, but Cloudflare isn't configured yet:\n{live_url}\n\n"
                    "Add CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_PROJECT to the server's environment to go live."
                )
            else:
                QMessageBox.information(self, "Site Live!", f"Your site is live at:\n{live_url}")

        def poll():
            self.poll_count += 1
            if self.poll_count > 120:
                finish()
                QMessageBox.warning(self, "Still working", "The deploy is taking longer than expected. Check the server logs.")
                return
            self.status_worker = ApiWorker("GET", f"{API_BASE}/generate-site/status", timeout=45)

            def on_status(ok, msg, st):
                if not ok:
                    QTimer.singleShot(3000, poll)  # transient network error: keep trying
                    return
                state = st.get("state")
                if state == "done":
                    show_result(st.get("live_url", ""))
                elif state == "error":
                    finish()
                    QMessageBox.warning(self, "Generation Failed", st.get("error", "Unknown error"))
                else:
                    QTimer.singleShot(3000, poll)

            self.status_worker.finished.connect(on_status)
            self.status_worker.start()

        # The server now builds in the background and returns right away (HTTP 202).
        self.generate_worker = ApiWorker("POST", f"{API_BASE}/generate-site", timeout=60)

        def on_started(success, message, resp_data):
            if not success:
                finish()
                QMessageBox.warning(self, "Generation Failed", message)
                return
            QTimer.singleShot(3000, poll)

        self.generate_worker.finished.connect(on_started)
        self.generate_worker.start()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()