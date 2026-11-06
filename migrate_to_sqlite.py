"""
SmartCart Database Migration: MySQL to SQLite
Safely transfers schema and all existing data from MySQL smartcart_db
into the local SQLite database smartcart.db.
Does NOT modify or delete any data from the existing MySQL database.
"""

import os
import sqlite3
import mysql.connector
import config

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SQLITE_DB_PATH = getattr(config, 'DB_PATH', os.path.join(BASE_DIR, 'smartcart.db'))

CREATE_TABLES_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS admin (
    admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    password TEXT,
    profile_image TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    password TEXT,
    profile_image TEXT
);

CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    description TEXT,
    category TEXT,
    price REAL,
    image TEXT,
    admin_id INTEGER,
    FOREIGN KEY (admin_id) REFERENCES admin(admin_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    razorpay_order_id TEXT,
    razorpay_payment_id TEXT,
    amount REAL,
    payment_status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    name TEXT,
    email TEXT,
    phone TEXT,
    door_no TEXT,
    address TEXT,
    city TEXT,
    pincode TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    product_name TEXT,
    quantity INTEGER,
    price REAL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);
"""

def init_sqlite_tables(sqlite_conn):
    sqlite_conn.executescript(CREATE_TABLES_SQL)
    sqlite_conn.commit()

def migrate_mysql_to_sqlite():
    print(f"Connecting to SQLite database: {SQLITE_DB_PATH}")
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    init_sqlite_tables(sqlite_conn)
    sqlite_cur = sqlite_conn.cursor()

    try:
        print("Connecting to existing MySQL database...")
        mysql_conn = mysql.connector.connect(
            host=config.DB_HOST,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME
        )
        mysql_cur = mysql_conn.cursor(dictionary=True)
    except Exception as e:
        print(f"Notice: Could not connect to MySQL ({e}). SQLite schema has been initialized.")
        sqlite_conn.close()
        return

    try:
        # 1. Migrate Admin
        mysql_cur.execute("SELECT * FROM admin")
        admins = mysql_cur.fetchall()
        for a in admins:
            sqlite_cur.execute("""
                INSERT OR REPLACE INTO admin (admin_id, name, email, password, profile_image)
                VALUES (?, ?, ?, ?, ?)
            """, (a['admin_id'], a['name'], a['email'], a['password'], a['profile_image']))
        print(f"✓ Migrated {len(admins)} admin records.")

        # 2. Migrate Users
        mysql_cur.execute("SELECT * FROM users")
        users = mysql_cur.fetchall()
        for u in users:
            sqlite_cur.execute("""
                INSERT OR REPLACE INTO users (user_id, name, email, password, profile_image)
                VALUES (?, ?, ?, ?, ?)
            """, (u['user_id'], u['name'], u['email'], u['password'], u.get('profile_image')))
        print(f"✓ Migrated {len(users)} user records.")

        # 3. Migrate Products
        mysql_cur.execute("SELECT * FROM products")
        products = mysql_cur.fetchall()
        for p in products:
            price = float(p['price']) if p['price'] is not None else 0.0
            sqlite_cur.execute("""
                INSERT OR REPLACE INTO products (product_id, name, description, category, price, image, admin_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (p['product_id'], p['name'], p['description'], p['category'], price, p['image'], p['admin_id']))
        print(f"✓ Migrated {len(products)} products.")

        # 4. Migrate Orders
        mysql_cur.execute("SELECT * FROM orders")
        orders = mysql_cur.fetchall()
        for o in orders:
            amount = float(o['amount']) if o['amount'] is not None else 0.0
            created_at = str(o['created_at']) if o['created_at'] is not None else None
            sqlite_cur.execute("""
                INSERT OR REPLACE INTO orders (
                    order_id, user_id, razorpay_order_id, razorpay_payment_id,
                    amount, payment_status, created_at, name, email, phone,
                    door_no, address, city, pincode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                o['order_id'], o['user_id'], o['razorpay_order_id'], o['razorpay_payment_id'],
                amount, o['payment_status'], created_at, o['name'], o['email'], o['phone'],
                o['door_no'], o['address'], o['city'], o['pincode']
            ))
        print(f"✓ Migrated {len(orders)} orders.")

        # 5. Migrate Order Items
        mysql_cur.execute("SELECT * FROM order_items")
        order_items = mysql_cur.fetchall()
        for item in order_items:
            price = float(item['price']) if item['price'] is not None else 0.0
            sqlite_cur.execute("""
                INSERT OR REPLACE INTO order_items (id, order_id, product_id, product_name, quantity, price)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (item['id'], item['order_id'], item['product_id'], item['product_name'], item['quantity'], price))
        print(f"✓ Migrated {len(order_items)} order items.")

        sqlite_conn.commit()
        print("\nAll data successfully migrated from MySQL to SQLite smartcart.db!")

    finally:
        mysql_cur.close()
        mysql_conn.close()
        sqlite_cur.close()
        sqlite_conn.close()

if __name__ == '__main__':
    migrate_mysql_to_sqlite()

