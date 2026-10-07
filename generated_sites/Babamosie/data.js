/* =========================================================
   Product catalog — rendered from the real shop's data
   ========================================================= */

const PRODUCTS = [

  {
    id: "p0",
    title: "Cloud Portfolio",
    category: "Website",
    price: 999,
    photo: "http://localhost:5000/static/uploads/1789198254.255206_cloudframe-1.png",
    photos: ["http://127.0.0.1:5000/static/uploads/1789195688.8032_cloudframe-1.png"],
    description: ""
  },

  {
    id: "p1",
    title: "a",
    category: "General",
    price: 11,
    photo: "http://localhost:5000/static/uploads/1789198265.56286_cloudframe-3.png",
    photos: ["http://localhost:5000/static/uploads/1789196666.51692_cloudframe-1.png", "http://localhost:5000/static/uploads/1789196666.535564_cloudframe-2.png", "http://localhost:5000/static/uploads/1789196666.550969_cloudframe-3.png"],
    description: ""
  },

  {
    id: "p2",
    title: "Cube Folio",
    category: "Website",
    price: 99,
    photo: "http://localhost:5000/static/uploads/1789198268.021045_codeorbit-1.png",
    photos: ["http://localhost:5000/static/uploads/1789198268.021045_codeorbit-1.png", "http://localhost:5000/static/uploads/1789198268.038862_codeorbit-2.png", "http://localhost:5000/static/uploads/1789198268.062314_codeorbit-3.png"],
    description: ""
  },

  {
    id: "p3",
    title: "poster",
    category: "General",
    price: 99,
    photo: "http://127.0.0.1:5000/static/uploads/1789538184.239225_gpt-image-2_make_a_minecraft_server_open_graph_image_preview_image_that_shows_interactive_fu-0.jpg",
    photos: ["http://127.0.0.1:5000/static/uploads/1789538184.239225_gpt-image-2_make_a_minecraft_server_open_graph_image_preview_image_that_shows_interactive_fu-0.jpg"],
    description: ""
  }

];

function getProduct(id){
  return PRODUCTS.find(p => p.id === id);
}

function formatPrice(n){
  return "₹" + Number(n || 0).toLocaleString("en-IN");
}