/* =========================================================
   Product catalog — rendered from the real shop's data
   ========================================================= */

const PRODUCTS = [
{% for p in products %}
  {
    id: "p{{ loop.index0 }}",
    title: {{ (p.name or "Untitled")|tojson }},
    category: {{ (p.category or "General")|tojson }},
    price: {{ p.price or 0 }},
    photo: {{ (p.photo_url or "")|tojson }},
    photos: {{ (p.photos if p.photos else ([p.photo_url] if p.photo_url else []))|tojson }},
    description: {{ (p.description or "")|tojson }}
  }{% if not loop.last %},{% endif %}
{% endfor %}
];

function getProduct(id){
  return PRODUCTS.find(p => p.id === id);
}

function formatPrice(n){
  return "₹" + Number(n || 0).toLocaleString("en-IN");
}
