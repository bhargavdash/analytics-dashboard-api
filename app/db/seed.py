# Standalone script to seed the database with rich analytics data.
# Run this script with: uv run python -m app.db.seed

import random
from datetime import date, timedelta
from faker import Faker
from app.db.connection import DB_PATH, get_connection

faker = Faker()
faker.seed_instance(1234)
random.seed(1234)

REGIONS = ["North", "South", "East", "West", "Central"]
CATEGORIES = ["Electronics", "Clothing", "Food", "Furniture"]
STATUSES = ["completed", "pending", "refunded"]

REGION_COUNTRY_MAP = {
    "North": ["United States", "Canada"],
    "South": ["Brazil", "Mexico"],
    "East": ["India", "Japan", "China"],
    "West": ["United Kingdom", "Germany", "France"],
    "Central": ["Australia", "Spain", "Italy"],
}

PRICE_RANGES = {
    "Electronics": (79, 899),
    "Clothing": (19, 249),
    "Food": (7, 149),
    "Furniture": (129, 1299),
}

PRODUCT_TEMPLATES = {
    "Electronics": {
        "adjectives": ["Aero", "Nova", "Luma", "Pulse", "Vertex", "Echo", "Quantum", "Zen"],
        "nouns": ["Speaker", "Tracker", "Camera", "Router", "Headset", "Display", "Charger", "Beacon"],
    },
    "Clothing": {
        "adjectives": ["Urban", "Summit", "Harbor", "Velvet", "Legacy", "Radiant", "Vivid", "Nomad"],
        "nouns": ["Jacket", "Sneaker", "Cardigan", "Blazer", "Parka", "Dress", "Hoodie", "Scarf"],
    },
    "Food": {
        "adjectives": ["Harvest", "Fresh", "Golden", "Maple", "Orchard", "Savory", "Citrus", "Classic"],
        "nouns": ["Pantry", "Blend", "Bites", "Delight", "Crunch", "Sauce", "Snack", "Fusion"],
    },
    "Furniture": {
        "adjectives": ["Modern", "Heritage", "Oak", "Cedar", "Craft", "Form", "Studio", "Hearth"],
        "nouns": ["Sofa", "Table", "Desk", "Cabinet", "Bench", "Chair", "Dresser", "Shelf"],
    },
}

CUSTOMER_BRANDS = {
    "Enterprise": [
        "Atlas Global", "Summit Dynamics", "Sterling Networks", "Aurora Systems", "Pioneer Logistics", "Nova Enterprises",
        "Horizon Ventures", "Catalyst Group", "Vertex Solutions", "Synergy Holdings",
    ],
    "SMB": [
        "Brightside Boutique", "Maple Street Café", "Cornerstone Studio", "Blue Harbor Market", "Willow & Co.",
        "Harbor Lane Goods", "Urban Grove", "Crafted Kitchen", "Greenfield Organics", "Cobalt Workshop",
    ],
}

TEAM_NAMES = ["Alpha", "Beta", "Gamma", "Orion", "Nexus"]


def make_product_name(category: str, index: int) -> str:
    attrs = PRODUCT_TEMPLATES[category]
    adjective = attrs["adjectives"][index % len(attrs["adjectives"])]
    noun = attrs["nouns"][index % len(attrs["nouns"])]
    return f"{adjective} {noun}"


def make_customer_name(segment: str, index: int) -> str:
    if segment == "Consumer":
        return faker.name()
    if segment == "SMB":
        return faker.unique.company()
    return faker.unique.company() + " Group"


def make_sales_rep_name() -> str:
    return faker.name()


def seed():
    conn = get_connection()

    conn.execute("DROP TABLE IF EXISTS orders")
    conn.execute("DROP TABLE IF EXISTS products")
    conn.execute("DROP TABLE IF EXISTS customers")
    conn.execute("DROP TABLE IF EXISTS sales_reps")

    conn.execute("""
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            name VARCHAR,
            category VARCHAR,
            unit_price DECIMAL(10,2)
        )
    """)

    conn.execute("""
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            name VARCHAR,
            segment VARCHAR,
            country VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE sales_reps (
            sales_rep_id INTEGER PRIMARY KEY,
            name VARCHAR,
            region VARCHAR,
            team VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            product_id INTEGER,
            region VARCHAR,
            sales_rep_id INTEGER,
            order_date DATE,
            amount DECIMAL(10,2),
            status VARCHAR
        )
    """)

    product_rows = []
    for i in range(1, 51):
        category = CATEGORIES[(i - 1) % len(CATEGORIES)]
        name = make_product_name(category, i - 1)
        price = round(random.uniform(*PRICE_RANGES[category]), 2)
        product_rows.append((i, name, category, price))
        conn.execute("INSERT INTO products VALUES (?, ?, ?, ?)", product_rows[-1])

    customer_segments = ["Enterprise", "SMB", "Consumer"]
    customer_rows = []
    for i in range(1, 201):
        segment = random.choice(customer_segments)
        country = random.choice([c for region in REGION_COUNTRY_MAP.values() for c in region])
        name = make_customer_name(segment, i - 1)
        customer_rows.append((i, segment, country))
        conn.execute("INSERT INTO customers VALUES (?, ?, ?, ?)", [
            i,
            name,
            segment,
            country,
        ])

    sales_rep_rows = []
    for i in range(1, 21):
        region = random.choice(REGIONS)
        sales_rep_rows.append((i, region))
        conn.execute("INSERT INTO sales_reps VALUES (?, ?, ?, ?)", [
            i,
            make_sales_rep_name(),
            region,
            TEAM_NAMES[(i - 1) % len(TEAM_NAMES)],
        ])

    reps_by_region = {}
    for rep_id, region in sales_rep_rows:
        reps_by_region.setdefault(region, []).append(rep_id)

    start_date = date(2022, 1, 1)
    for i in range(1, 200001):
        order_date = start_date + timedelta(days=random.randint(0, 1095))
        product_id = random.randint(1, 50)
        product_price = product_rows[product_id - 1][3]
        quantity = random.randint(1, 5)
        amount = round(product_price * quantity * random.uniform(0.95, 1.1), 2)

        customer_id = random.randint(1, 200)
        customer_country = customer_rows[customer_id - 1][2]
        customer_region = next((region for region, countries in REGION_COUNTRY_MAP.items() if customer_country in countries), random.choice(REGIONS))
        sales_rep_id = random.choice(reps_by_region.get(customer_region, [random.randint(1, 20)]))

        conn.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
            i,
            customer_id,
            product_id,
            customer_region,
            sales_rep_id,
            order_date,
            amount,
            random.choice(STATUSES),
        ])

    conn.commit()
    print("Seeded: 200k orders, 50 products, 200 customers, 20 sales reps")
    print(f"DB at: {DB_PATH}")


if __name__ == "__main__":
    seed()



