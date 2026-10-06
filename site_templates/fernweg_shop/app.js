/* =========================================================
   Shared app logic — cart, theme, drawer (no fake variants/promo/tax)
   ========================================================= */

const STORAGE_CART = "digitaltwin_cart";
const STORAGE_THEME = "digitaltwin_theme";

/* ---------- Theme ---------- */

function initTheme(){
  const saved = localStorage.getItem(STORAGE_THEME);
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const theme = saved || (prefersDark ? "dark" : "light");
  document.documentElement.setAttribute("data-theme", theme);
}
initTheme();

function bindThemeToggle(){
  const btn = document.getElementById("themeToggle");
  if(!btn) return;
  btn.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem(STORAGE_THEME, next);
  });
}

/* ---------- Cart state (simple: id + qty, no size/color variants) ---------- */

function getCart(){
  try{ return JSON.parse(localStorage.getItem(STORAGE_CART)) || []; }catch(e){ return []; }
}

function saveCart(cart){
  localStorage.setItem(STORAGE_CART, JSON.stringify(cart));
  updateCartCount();
}

function addToCart(id, qty){
  const cart = getCart();
  const existing = cart.find(l => l.id === id);
  if(existing){ existing.qty += qty; } else { cart.push({ id, qty }); }
  saveCart(cart);
  return cart;
}

function removeCartLine(id){
  let cart = getCart();
  cart = cart.filter(l => l.id !== id);
  saveCart(cart);
  return cart;
}

function setCartLineQty(id, qty){
  const cart = getCart();
  const line = cart.find(l => l.id === id);
  if(line){
    line.qty = qty;
    if(line.qty <= 0){ return removeCartLine(id); }
  }
  saveCart(cart);
  return cart;
}

function cartCount(){
  return getCart().reduce((sum, l) => sum + l.qty, 0);
}

function cartSubtotal(){
  return getCart().reduce((sum, l) => {
    const p = getProduct(l.id);
    return p ? sum + p.price * l.qty : sum;
  }, 0);
}

function updateCartCount(){
  const n = cartCount();
  document.querySelectorAll(".cart-count").forEach(el => {
    el.textContent = n;
    el.style.display = n > 0 ? "flex" : "none";
  });
}

/* ---------- Toast ---------- */

let toastTimer;
function showToast(message, actionHtml){
  let el = document.getElementById("toast");
  if(!el){
    el = document.createElement("div");
    el.id = "toast";
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.innerHTML = `<span>${message}</span>${actionHtml ? actionHtml : ""}`;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

/* ---------- Product media (real photo, or a simple placeholder) ---------- */

function productMedia(p){
  if(p && p.photo){
    return `<img src="${p.photo}" alt="${p.title || ''}" style="width:100%;height:100%;object-fit:cover;">`;
  }
  return `<svg viewBox="0 0 200 180" xmlns="http://www.w3.org/2000/svg" style="background:var(--bg-raised)">
    <rect width="200" height="180" fill="var(--bg-raised)"/>
    <g opacity="0.35"><circle cx="100" cy="80" r="30" fill="none" stroke="currentColor" stroke-width="3"/><path d="M55 140 L145 140 L125 100 L100 125 L80 105 Z" fill="none" stroke="currentColor" stroke-width="3"/></g>
  </svg>`;
}

/* ---------- Cart drawer ---------- */

function buildDrawer(){
  if(document.getElementById("cartDrawer")) return;
  const overlay = document.createElement("div");
  overlay.className = "drawer-overlay";
  overlay.id = "drawerOverlay";

  const drawer = document.createElement("div");
  drawer.className = "drawer";
  drawer.id = "cartDrawer";
  drawer.innerHTML = `
    <div class="drawer-head">
      <h2>Cart</h2>
      <button class="icon-btn" id="drawerClose" aria-label="Close cart">${iconClose()}</button>
    </div>
    <div class="drawer-body" id="drawerBody"></div>
    <div class="drawer-foot" id="drawerFoot"></div>
  `;
  document.body.appendChild(overlay);
  document.body.appendChild(drawer);

  overlay.addEventListener("click", closeDrawer);
  document.getElementById("drawerClose").addEventListener("click", closeDrawer);
}

function renderDrawer(){
  const body = document.getElementById("drawerBody");
  const foot = document.getElementById("drawerFoot");
  const cart = getCart();

  if(cart.length === 0){
    body.innerHTML = `<div style="padding:40px 0; text-align:center; color:var(--ink-soft);">Cart is empty.</div>`;
    foot.innerHTML = `<a href="shop.html" class="btn btn-outline btn-block">Browse products</a>`;
    return;
  }

  body.innerHTML = cart.map(l => {
    const p = getProduct(l.id);
    if(!p) return "";
    return `
      <div class="mini-cart-item">
        <div class="thumb">${productMedia(p)}</div>
        <div class="grow">
          <div>${p.title}</div>
          <div class="qty">Qty ${l.qty}</div>
        </div>
        <div>${formatPrice(p.price * l.qty)}</div>
      </div>
    `;
  }).join("");

  const subtotal = cartSubtotal();
  foot.innerHTML = `
    <div class="summary-line"><span>Subtotal</span><strong>${formatPrice(subtotal)}</strong></div>
    <a href="cart.html" class="btn btn-outline btn-block" style="margin-bottom:10px;">View cart</a>
    <a href="checkout.html" class="btn btn-accent btn-block">Checkout</a>
  `;
}

function openDrawer(){
  buildDrawer();
  renderDrawer();
  document.getElementById("drawerOverlay").classList.add("show");
  document.getElementById("cartDrawer").classList.add("show");
  document.body.style.overflow = "hidden";
}
function closeDrawer(){
  const o = document.getElementById("drawerOverlay");
  const d = document.getElementById("cartDrawer");
  if(o) o.classList.remove("show");
  if(d) d.classList.remove("show");
  document.body.style.overflow = "";
}

/* ---------- Icons ---------- */

function iconClose(){ return `<svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M2 2l14 14M16 2L2 16"/></svg>`; }
function iconSun(){ return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>`; }
function iconMoon(){ return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg>`; }

/* ---------- WhatsApp order submission (used by checkout.html) ---------- */

async function submitWhatsAppOrder(customerName, customerPhone, notes){
  const cart = getCart();
  const items = cart.map(l => {
    const p = getProduct(l.id);
    return p ? { name: p.title, price: p.price, qty: l.qty } : null;
  }).filter(Boolean);

  const res = await fetch((window.BACKEND_URL || "") + "/api/orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      shop_id: window.SHOP_INFO && window.SHOP_INFO.id,
      customer_name: customerName,
      customer_phone: customerPhone,
      items: items,
      notes: notes
    })
  });
  const data = await res.json();
  if(!res.ok) throw new Error(data.error || "Order failed");
  return data;
}

/* ---------- Header wiring (common to all pages) ---------- */

function initHeader(){
  bindThemeToggle();
  updateCartCount();

  document.querySelectorAll(".theme-toggle .knob").forEach(k => {
    k.innerHTML = document.documentElement.getAttribute("data-theme") === "dark" ? iconMoon() : iconSun();
  });
  document.getElementById("themeToggle")?.addEventListener("click", () => {
    setTimeout(() => {
      document.querySelectorAll(".theme-toggle .knob").forEach(k => {
        k.innerHTML = document.documentElement.getAttribute("data-theme") === "dark" ? iconMoon() : iconSun();
      });
    }, 0);
  });

  const cartBtn = document.getElementById("cartOpenBtn");
  if(cartBtn){
    cartBtn.addEventListener("click", (e) => { e.preventDefault(); openDrawer(); });
  }

  const navToggle = document.getElementById("navToggle");
  const mainNav = document.querySelector(".main-nav");
  if(navToggle && mainNav){
    navToggle.addEventListener("click", () => {
      const open = mainNav.style.display === "flex";
      mainNav.style.display = open ? "none" : "flex";
      mainNav.style.cssText += open ? "" : "position:absolute; top:76px; left:0; right:0; background:var(--bg); flex-direction:column; padding:20px 28px; border-bottom:2px solid var(--ink); gap:16px;";
    });
  }

  const searchForm = document.getElementById("headerSearchForm");
  if(searchForm){
    searchForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const q = document.getElementById("headerSearchInput").value.trim();
      window.location.href = "shop.html" + (q ? "?q=" + encodeURIComponent(q) : "");
    });
  }
}

document.addEventListener("DOMContentLoaded", initHeader);
