import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash
)

app = Flask(__name__)
app.secret_key = 'campus_secondhand_trading_secret_key_2024'

# ── Database Abstraction ─────────────────────────────────────────────────────
# Supports both SQLite (local dev) and PostgreSQL (Render production)
USE_PG = bool(os.environ.get('DATABASE_URL'))
DATABASE_URL = os.environ.get('DATABASE_URL')
SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'campus_trade.db')

if USE_PG:
    import psycopg2
    import psycopg2.extras
    from psycopg2.errors import UniqueViolation as PgUniqueViolation

    class DB:
        def __init__(self):
            self.conn = psycopg2.connect(DATABASE_URL)

        def query(self, sql, params=None):
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, params or ())
            return cur

        def execute(self, sql, params=None):
            cur = self.conn.cursor()
            cur.execute(sql, params or ())
            return cur

        def commit(self): self.conn.commit()
        def rollback(self): self.conn.rollback()
        def close(self): self.conn.close()
else:
    class DB:
        def __init__(self):
            self.conn = sqlite3.connect(SQLITE_PATH)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")

        def query(self, sql, params=None):
            sql = sql.replace('%s', '?')
            return self.conn.execute(sql, params or ())

        def execute(self, sql, params=None):
            sql = sql.replace('%s', '?')
            return self.conn.execute(sql, params or ())

        def commit(self): self.conn.commit()
        def rollback(self): self.conn.rollback()
        def close(self): self.conn.close()

def get_db():
    return DB()

def is_unique_error(e):
    """Check if an error is a unique constraint violation"""
    if USE_PG:
        return isinstance(e, PgUniqueViolation)
    return isinstance(e, sqlite3.IntegrityError)

# ── Database Initialization ──────────────────────────────────────────────────
def init_db():
    db = get_db()
    if USE_PG:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(100) NOT NULL,
                balance REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                price VARCHAR(30) NOT NULL,
                seller_id INTEGER REFERENCES users(id),
                status VARCHAR(20) DEFAULT 'available',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                item_id INTEGER NOT NULL REFERENCES items(id),
                purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, item_id)
            )
        """)
        db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS balance REAL DEFAULT 0.0")
    else:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                balance REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price TEXT NOT NULL,
                seller_id INTEGER REFERENCES users(id),
                status TEXT DEFAULT 'available',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                item_id INTEGER NOT NULL REFERENCES items(id),
                purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, item_id)
            )
        """)
        # Migration for existing DBs
        try:
            db.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0")
        except Exception:
            pass

    # Default admin
    existing = db.query("SELECT id FROM admins WHERE username = %s", ('admin1',)).fetchone()
    if not existing:
        db.execute("INSERT INTO admins (username, password) VALUES (%s, %s)", ('admin1', 'adminpass1'))

    # Default items (same 14 as original C project)
    cnt = db.query("SELECT COUNT(*) AS c FROM items").fetchone()['c']
    if cnt == 0:
        default_items = [
            ('苹果笔记本电脑', '5000'),
            ('C语言(第6版)', '50'),
            ('自行车', '300'),
            ('书包', '47'),
            ('迷你电动车', '88.8'),
            ('音响', '500'),
            ('羽毛球', '5'),
            ('羽毛球拍', '100'),
            ('钢笔', '6'),
            ('英语教材', '58'),
            ('数据库教材', '60'),
            ('迷你电动车', '500'),
            ('二手自行车', '200'),
            ('二手摩托车', '2000'),
        ]
        for name, price in default_items:
            db.execute("INSERT INTO items (name, price, seller_id, status) VALUES (%s, %s, NULL, 'available')",
                       (name, price))
    db.commit()
    db.close()

init_db()

# ── Helpers ───────────────────────────────────────────────────────────────────
def is_valid_price(price):
    if not price: return False
    dot_count = 0
    for ch in price:
        if ch == '.': dot_count += 1
        if dot_count > 1: return False
        if ch != '.' and not ch.isdigit(): return False
    return True

def is_valid_item_name(name):
    return 0 < len(name) <= 15

def parse_price(price_str):
    try: return float(price_str)
    except (ValueError, TypeError): return 0.0

def login_required(role='user'):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('index'))
            if role == 'admin' and session.get('role') != 'admin':
                return redirect(url_for('index'))
            if role == 'user' and session.get('role') != 'user':
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return wrapper
    return decorator

# ── Routes: Pages ─────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/user/register')
def user_register_page():
    return render_template('user_register.html')

@app.route('/admin/register')
def admin_register_page():
    return render_template('admin_register.html')

@app.route('/user/dashboard')
@login_required(role='user')
def user_dashboard():
    return render_template('user_dashboard.html', username=session.get('username'))

@app.route('/user/release')
@login_required(role='user')
def user_release_page():
    return render_template('item_release.html')

@app.route('/user/items')
@login_required(role='user')
def user_items_page():
    return render_template('item_list.html')

@app.route('/user/purchase')
@login_required(role='user')
def user_purchase_page():
    return render_template('purchase.html')

@app.route('/user/cart')
@login_required(role='user')
def user_cart_page():
    return render_template('cart.html')

@app.route('/admin/dashboard')
@login_required(role='admin')
def admin_dashboard():
    return render_template('admin_dashboard.html', username=session.get('username'))

@app.route('/admin/items')
@login_required(role='admin')
def admin_items_page():
    return render_template('admin_items.html')

@app.route('/admin/users')
@login_required(role='admin')
def admin_users_page():
    return render_template('admin_users.html')

# ── API: Auth ─────────────────────────────────────────────────────────────────
@app.route('/api/user/login', methods=['POST'])
def api_user_login():
    data = request.get_json()
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    if not username or not password:
        return jsonify({'ok': False, 'msg': '用户名和密码不能为空'})
    db = get_db()
    user = db.query("SELECT id, username, balance FROM users WHERE username = %s AND password = %s",
                    (username, password)).fetchone()
    db.close()
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['balance'] = user['balance']
        session['role'] = 'user'
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'msg': '用户名或密码错误'})

@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    data = request.get_json()
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    if not username or not password:
        return jsonify({'ok': False, 'msg': '用户名和密码不能为空'})
    db = get_db()
    admin = db.query("SELECT id, username FROM admins WHERE username = %s AND password = %s",
                     (username, password)).fetchone()
    db.close()
    if admin:
        session['user_id'] = admin['id']
        session['username'] = admin['username']
        session['balance'] = 0
        session['role'] = 'admin'
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'msg': '用户名或密码错误'})

@app.route('/api/user/register', methods=['POST'])
def api_user_register():
    data = request.get_json()
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    if not username or not password:
        return jsonify({'ok': False, 'msg': '用户名和密码不能为空'})
    if len(username) > 15:
        return jsonify({'ok': False, 'msg': '用户名不能超过15个字符'})
    db = get_db()
    try:
        db.execute("INSERT INTO users (username, password, balance) VALUES (%s, %s, 0.0)", (username, password))
        db.commit()
        return jsonify({'ok': True, 'msg': '注册成功！'})
    except Exception as e:
        if is_unique_error(e):
            return jsonify({'ok': False, 'msg': '该用户名已被使用'})
        return jsonify({'ok': False, 'msg': '注册失败，请重试'})
    finally:
        db.close()

@app.route('/api/admin/register', methods=['POST'])
def api_admin_register():
    data = request.get_json()
    auth_code = (data.get('auth_code') or '').strip()
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    if auth_code != 'regon':
        return jsonify({'ok': False, 'msg': '授权码错误，无法注册管理员'})
    if not username or not password:
        return jsonify({'ok': False, 'msg': '用户名和密码不能为空'})
    db = get_db()
    try:
        db.execute("INSERT INTO admins (username, password) VALUES (%s, %s)", (username, password))
        db.commit()
        return jsonify({'ok': True, 'msg': '管理员注册成功！'})
    except Exception as e:
        if is_unique_error(e):
            return jsonify({'ok': False, 'msg': '该用户名已被使用'})
        return jsonify({'ok': False, 'msg': '注册失败，请重试'})
    finally:
        db.close()

@app.route('/api/logout', methods=['GET', 'POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})

# ── API: User Balance ────────────────────────────────────────────────────────
@app.route('/api/user/balance', methods=['GET'])
@login_required(role='user')
def api_user_balance():
    db = get_db()
    user = db.query("SELECT balance FROM users WHERE id = %s", (session['user_id'],)).fetchone()
    db.close()
    balance = float(user['balance']) if user else 0.0
    session['balance'] = balance
    return jsonify({'ok': True, 'balance': balance})

# ── API: User Operations ──────────────────────────────────────────────────────
@app.route('/api/user/release', methods=['POST'])
@login_required(role='user')
def api_user_release():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    price = (data.get('price') or '').strip()
    if not is_valid_item_name(name):
        return jsonify({'ok': False, 'msg': '商品名称不能为空且不超过15个字符'})
    if not is_valid_price(price):
        return jsonify({'ok': False, 'msg': '价格不合法（只允许数字和最多一个小数点）'})
    db = get_db()
    db.execute("INSERT INTO items (name, price, seller_id, status) VALUES (%s, %s, %s, 'available')",
               (name, price, session['user_id']))
    db.commit()
    db.close()
    return jsonify({'ok': True, 'msg': '商品上架成功！'})

@app.route('/api/user/items', methods=['GET'])
@login_required(role='user')
def api_user_items():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    db = get_db()
    total = db.query("SELECT COUNT(*) AS c FROM items WHERE status = 'available'").fetchone()['c']
    items = db.query(
        "SELECT id, name, price, created_at FROM items WHERE status = 'available' ORDER BY id DESC LIMIT %s OFFSET %s",
        (per_page, offset)
    ).fetchall()
    db.close()
    return jsonify({
        'ok': True,
        'items': [dict(r) for r in items],
        'total': total, 'page': page, 'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

@app.route('/api/user/search', methods=['GET'])
@login_required(role='user')
def api_user_search():
    keyword = (request.args.get('keyword') or '').strip()
    if not keyword:
        return jsonify({'ok': True, 'items': []})
    db = get_db()
    items = db.query(
        "SELECT id, name, price FROM items WHERE status = 'available' AND name LIKE %s ORDER BY id",
        ('%' + keyword + '%',)
    ).fetchall()
    db.close()
    return jsonify({'ok': True, 'items': [dict(r) for r in items]})

@app.route('/api/user/purchase', methods=['POST'])
@login_required(role='user')
def api_user_purchase():
    data = request.get_json()
    item_id = data.get('item_id')
    if not item_id:
        return jsonify({'ok': False, 'msg': '无效的商品ID'})
    db = get_db()
    item = db.query("SELECT id, name, price, seller_id, status FROM items WHERE id = %s", (item_id,)).fetchone()
    if not item:
        db.close(); return jsonify({'ok': False, 'msg': '商品不存在'})
    if item['status'] != 'available':
        db.close(); return jsonify({'ok': False, 'msg': '该商品已售出'})
    exists = db.query("SELECT id FROM purchases WHERE user_id = %s AND item_id = %s",
                      (session['user_id'], item_id)).fetchone()
    if exists:
        db.close(); return jsonify({'ok': False, 'msg': '该商品已在购物车中'})
    buyer = db.query("SELECT balance FROM users WHERE id = %s", (session['user_id'],)).fetchone()
    price_val = parse_price(item['price'])
    if float(buyer['balance']) < price_val:
        db.close()
        return jsonify({'ok': False, 'msg': '余额不足！当前余额：¥%.2f，商品价格：¥%.2f' % (float(buyer['balance']), price_val)})
    db.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (price_val, session['user_id']))
    if item['seller_id'] is not None:
        db.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (price_val, item['seller_id']))
    db.execute("INSERT INTO purchases (user_id, item_id) VALUES (%s, %s)", (session['user_id'], item_id))
    db.execute("UPDATE items SET status = 'sold' WHERE id = %s", (item_id,))
    db.commit()
    session['balance'] = float(buyer['balance']) - price_val
    db.close()
    return jsonify({'ok': True, 'msg': '购买成功！已支付 ¥%.2f' % price_val})

@app.route('/api/user/cart', methods=['GET'])
@login_required(role='user')
def api_user_cart():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    db = get_db()
    total = db.query("SELECT COUNT(*) AS c FROM purchases WHERE user_id = %s", (session['user_id'],)).fetchone()['c']
    items = db.query("""
        SELECT p.id AS pid, i.name, i.price, p.purchased_at
        FROM purchases p JOIN items i ON i.id = p.item_id
        WHERE p.user_id = %s ORDER BY p.purchased_at DESC LIMIT %s OFFSET %s
    """, (session['user_id'], per_page, offset)).fetchall()
    db.close()
    return jsonify({
        'ok': True, 'items': [dict(r) for r in items],
        'total': total, 'page': page, 'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

# ── API: Admin Operations ─────────────────────────────────────────────────────
@app.route('/api/admin/items', methods=['GET'])
@login_required(role='admin')
def api_admin_items():
    page = request.args.get('page', 1, type=int)
    per_page = 10; offset = (page - 1) * per_page
    db = get_db()
    total = db.query("SELECT COUNT(*) AS c FROM items").fetchone()['c']
    items = db.query("""
        SELECT i.id, i.name, i.price, i.status,
               COALESCE(u.username, '管理员') AS seller_name, i.created_at
        FROM items i LEFT JOIN users u ON u.id = i.seller_id
        ORDER BY i.id DESC LIMIT %s OFFSET %s
    """, (per_page, offset)).fetchall()
    db.close()
    return jsonify({
        'ok': True, 'items': [dict(r) for r in items],
        'total': total, 'page': page, 'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

@app.route('/api/admin/item/add', methods=['POST'])
@login_required(role='admin')
def api_admin_item_add():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    price = (data.get('price') or '').strip()
    if not is_valid_item_name(name):
        return jsonify({'ok': False, 'msg': '商品名称不能为空且不超过15个字符'})
    if not is_valid_price(price):
        return jsonify({'ok': False, 'msg': '价格不合法（只允许数字和最多一个小数点）'})
    db = get_db()
    db.execute("INSERT INTO items (name, price, seller_id, status) VALUES (%s, %s, NULL, 'available')", (name, price))
    db.commit(); db.close()
    return jsonify({'ok': True, 'msg': '商品添加成功！'})

@app.route('/api/admin/item/delete', methods=['POST'])
@login_required(role='admin')
def api_admin_item_delete():
    data = request.get_json()
    item_id = data.get('item_id')
    pwd = (data.get('secondary_password') or '').strip()
    if pwd != 'accon':
        return jsonify({'ok': False, 'msg': '二级密码错误，无法删除商品'})
    if not item_id:
        return jsonify({'ok': False, 'msg': '无效的商品ID'})
    db = get_db()
    db.execute("DELETE FROM purchases WHERE item_id = %s", (item_id,))
    db.execute("DELETE FROM items WHERE id = %s", (item_id,))
    db.commit(); db.close()
    return jsonify({'ok': True, 'msg': '商品删除成功！'})

@app.route('/api/admin/item/modify', methods=['POST'])
@login_required(role='admin')
def api_admin_item_modify():
    data = request.get_json()
    item_id = data.get('item_id')
    name = (data.get('name') or '').strip()
    price = (data.get('price') or '').strip()
    if not item_id:
        return jsonify({'ok': False, 'msg': '无效的商品ID'})
    if not is_valid_item_name(name):
        return jsonify({'ok': False, 'msg': '商品名称不能为空且不超过15个字符'})
    if not is_valid_price(price):
        return jsonify({'ok': False, 'msg': '价格不合法（只允许数字和最多一个小数点）'})
    db = get_db()
    db.execute("UPDATE items SET name = %s, price = %s WHERE id = %s", (name, price, item_id))
    db.commit(); db.close()
    return jsonify({'ok': True, 'msg': '商品修改成功！'})

@app.route('/api/admin/users', methods=['GET'])
@login_required(role='admin')
def api_admin_users():
    page = request.args.get('page', 1, type=int)
    per_page = 10; offset = (page - 1) * per_page
    db = get_db()
    total = db.query("SELECT COUNT(*) AS c FROM users").fetchone()['c']
    users = db.query("""
        SELECT u.id, u.username, u.balance, u.created_at,
               (SELECT COUNT(*) FROM purchases WHERE user_id = u.id) AS purchase_count
        FROM users u ORDER BY u.id LIMIT %s OFFSET %s
    """, (per_page, offset)).fetchall()
    db.close()
    return jsonify({
        'ok': True, 'users': [dict(r) for r in users],
        'total': total, 'page': page, 'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

@app.route('/api/admin/user/delete', methods=['POST'])
@login_required(role='admin')
def api_admin_user_delete():
    data = request.get_json()
    user_id = data.get('user_id')
    pwd = (data.get('secondary_password') or '').strip()
    if pwd != 'accon':
        return jsonify({'ok': False, 'msg': '二级密码错误，无法删除用户'})
    if not user_id:
        return jsonify({'ok': False, 'msg': '无效的用户ID'})
    db = get_db()
    db.execute("DELETE FROM purchases WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM items WHERE seller_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit(); db.close()
    return jsonify({'ok': True, 'msg': '用户删除成功！'})

@app.route('/api/admin/user/recharge', methods=['POST'])
@login_required(role='admin')
def api_admin_user_recharge():
    data = request.get_json()
    user_id = data.get('user_id')
    amount = data.get('amount')
    if not user_id:
        return jsonify({'ok': False, 'msg': '无效的用户ID'})
    if not amount or float(amount) <= 0:
        return jsonify({'ok': False, 'msg': '充值金额必须大于0'})
    db = get_db()
    user = db.query("SELECT id FROM users WHERE id = %s", (user_id,)).fetchone()
    if not user:
        db.close(); return jsonify({'ok': False, 'msg': '用户不存在'})
    db.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (float(amount), user_id))
    db.commit()
    new_bal = db.query("SELECT balance FROM users WHERE id = %s", (user_id,)).fetchone()['balance']
    db.close()
    return jsonify({'ok': True, 'msg': '充值成功！已充值 ¥%.2f，当前余额 ¥%.2f' % (float(amount), float(new_bal))})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
