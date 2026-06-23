import frappe
import json

WHATSAPP_NUMBER = "254725507764"

# Sizes map to actual ERPNext item codes: prefix + size (e.g. MT-Red-M)
PRODUCTS = [
    {
        "item_code": "MT-Red",
        "item_name": "Men's Running T-Shirt — Red",
        "description": "Lightweight performance crew-neck tee in Kenyan racing red. Features the iconic 254 Runner speed-sash diagonal and runners silhouette motif. Greek-key sublimation pattern throughout. Quick-dry micro-mesh fabric.",
        "price": 2000,
        "currency": "KES",
        "colorway": "Red",
        "gender": "Men",
        "sizes": ["XS", "S", "M", "L", "XL", "XXL"],
        "in_stock": True,
        "image": "/assets/sports_254/images/mt-red.jpg",
        "images": [
            "/assets/sports_254/images/mt-red.jpg",
            "/assets/sports_254/images/mt-red-2.jpg",
        ],
        "is_set": False,
    },
    {
        "item_code": "MT-White",
        "item_name": "Men's Running T-Shirt — White",
        "description": "Classic performance crew-neck tee on a clean white base. The bold 254 Runner speed-sash diagonal cuts across the chest in Kenya green and black. Greek-key sublimation weave throughout for that unmistakable heritage look.",
        "price": 2000,
        "currency": "KES",
        "colorway": "White",
        "gender": "Men",
        "sizes": ["XS", "S", "M", "L", "XL", "XXL"],
        "in_stock": True,
        "image": "/assets/sports_254/images/mt-white.jpg",
        "images": [
            "/assets/sports_254/images/mt-white.jpg",
        ],
        "is_set": False,
    },
    {
        "item_code": "WT-Red",
        "item_name": "Women's Running T-Shirt — Red",
        "description": "Women's cut performance tee in vivid Kenyan red. Slim athletic fit with the 254 Runner runners silhouette and speed-sash design. 'Born Kenyan, Born to Run' and spear crest on back. Moisture-wicking fabric.",
        "price": 2000,
        "currency": "KES",
        "colorway": "Red",
        "gender": "Women",
        "sizes": ["XS", "S", "M", "L", "XL", "XXL"],
        "in_stock": True,
        "image": "/assets/sports_254/images/wt-red.jpg",
        "images": [
            "/assets/sports_254/images/wt-red.jpg",
        ],
        "is_set": False,
    },
    {
        "item_code": "WT-White",
        "item_name": "Women's Running T-Shirt — White",
        "description": "Women's cut tee on a crisp white base with the bold speed-sash diagonal and Maasai shield crest on the back. 'Born Kenyan, Born to Run' printed across the shoulders. Lightweight and breathable.",
        "price": 2000,
        "currency": "KES",
        "colorway": "White",
        "gender": "Women",
        "sizes": ["XS", "S", "M", "L", "XL", "XXL"],
        "in_stock": True,
        "image": "/assets/sports_254/images/wt-white.jpg",
        "images": [
            "/assets/sports_254/images/wt-white.jpg",
        ],
        "is_set": False,
    },
    {
        "item_code": "MV-Red",
        "item_name": "Men's Running Vest — Red",
        "description": "Sleeveless racing vest for maximum arm-swing freedom. Kenyan red with the full speed-sash diagonal across the torso. Spear motif and 'Born Kenyan, Born to Run' on the back. Ideal for race day and hot-weather training.",
        "price": 2000,
        "currency": "KES",
        "colorway": "Red",
        "gender": "Men",
        "sizes": ["XS", "S", "M", "L", "XL", "XXL"],
        "in_stock": True,
        "image": "/assets/sports_254/images/mv-red.jpg",
        "images": [
            "/assets/sports_254/images/mv-red.jpg",
            "/assets/sports_254/images/mv-red-2.jpg",
            "/assets/sports_254/images/mv-red-back.jpg",
        ],
        "is_set": False,
    },
    {
        "item_code": "MV-White",
        "item_name": "Men's Running Vest — White",
        "description": "Sleeveless racing vest on a white Greek-key sublimation base. Speed-sash diagonal in green and red across the lower chest. Maasai shield crest on back with 'Born Kenyan, Born to Run'. Featherlight and race-ready.",
        "price": 2000,
        "currency": "KES",
        "colorway": "White",
        "gender": "Men",
        "sizes": ["XS", "S", "M", "L", "XL", "XXL"],
        "in_stock": True,
        "image": "/assets/sports_254/images/mv-white.jpg",
        "images": [
            "/assets/sports_254/images/mv-white.jpg",
            "/assets/sports_254/images/set-white-mockup.jpg",
        ],
        "is_set": False,
    },
    {
        "item_code": "WV-Red",
        "item_name": "Women's Running Vest — Red",
        "description": "Women's fit sleeveless vest in bold Kenyan red. Speed-sash diagonal with Greek-key pattern. Spear crest on back. Shown front + back at the 254 Runner store in Nairobi.",
        "price": 2000,
        "currency": "KES",
        "colorway": "Red",
        "gender": "Women",
        "sizes": ["XS", "S", "M", "L", "XL", "XXL"],
        "in_stock": True,
        "image": "/assets/sports_254/images/wv-red.jpg",
        "images": [
            "/assets/sports_254/images/wv-red.jpg",
            "/assets/sports_254/images/set-red-mockup.jpg",
        ],
        "is_set": False,
    },
    {
        "item_code": "WV-White",
        "item_name": "Women's Running Vest — White",
        "description": "Women's fit sleeveless vest on a white Greek-key base. Bold speed-sash diagonal in black, red and green. Maasai shield and crossed spears crest on back. Shown front + back at the 254 Runner store.",
        "price": 2000,
        "currency": "KES",
        "colorway": "White",
        "gender": "Women",
        "sizes": ["XS", "S", "M", "L", "XL", "XXL"],
        "in_stock": True,
        "image": "/assets/sports_254/images/wv-white.jpg",
        "images": [
            "/assets/sports_254/images/wv-white.jpg",
            "/assets/sports_254/images/wv-white-2.jpg",
            "/assets/sports_254/images/set-white-mockup.jpg",
        ],
        "is_set": False,
    },
]

SLIDES = [
    {
        "src": "/assets/sports_254/images/mv-red.jpg",
        "title": "Men's Vest — Red",
        "desc": "Sleeveless race-day vest. Speed-sash diagonal. Spear crest on back.",
    },
    {
        "src": "/assets/sports_254/images/wv-white.jpg",
        "title": "Women's Vest — White",
        "desc": "White Greek-key vest with Maasai shield. Front + back at the 254 Runner store.",
    },
    {
        "src": "/assets/sports_254/images/mt-red.jpg",
        "title": "Men's T-Shirt — Red",
        "desc": "Classic performance tee. 254 Runner runners silhouette on Kenyan red.",
    },
    {
        "src": "/assets/sports_254/images/wt-white.jpg",
        "title": "Women's T-Shirt — White",
        "desc": "Women's white tee with speed-sash and Maasai crest on the back.",
    },
]


def get_context(context):
    context.no_cache = 1
    context.products = PRODUCTS
    context.products_json = json.dumps(PRODUCTS)
    context.slides = SLIDES
    context.wa_number = WHATSAPP_NUMBER
    context.session_user = frappe.session.user
    context.is_guest = frappe.session.user == "Guest"
