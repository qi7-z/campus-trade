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

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'campus_trade.db')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price TEXT NOT NULL,
            seller_id INTEGER REFERENCES users(id),
            status TEXT DEFAULT 'available' CHECK(status IN ('available','sold')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            item_id INTEGER NOT NULL REFERENCES items(id),
            purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, item_id)
        );
    """)
    # 插入默认管理账号 admin1 / adminpass1（同原项目）
    existing = cur.execute("SELECT id FROM admins WHERE username='admin1'").fetchone()
    if not existing:
        cur.execute("INSERT INTO admins (username, password) VALUES (?, ?)",
                    ('admin1', 'adminpass1'))
    # 插入初始商品列表（同原项目 main.c 中的 14 件商品）
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
    existing_count = cur.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    if existing_count == 0:
        cur.executemany("INSERT INTO items (name, price, seller_id, status) VALUES (?, ?, NULL, 'available')",
                        default_items)
    conn.commit()
    conn.close()

init_db()

# ── Helpers ───────────────────────────────────────────────────────────────────
def is_valid_price(price):
    """只允许数字和最多一个小数点"""
    if not price:
        return False
    dot_count = 0
    for ch in price:
        if ch == '.':
            dot_count += 1
            if dot_count > 1:
                return False
        elif not ch.isdigit():
            return False
    return True

def is_valid_item_name(name):
    """商品名称不超过15个字符"""
    return len(name) <= 15 and len(name) > 0

def login_required(role='user'):
    """登录验证装饰器"""
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
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'ok': False, 'msg': '用户名和密码不能为空'})
    conn = get_db()
    user = conn.execute(
        "SELECT id, username FROM users WHERE username=? AND password=?",
        (username, password)
    ).fetchone()
    conn.close()
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = 'user'
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'msg': '用户名或密码错误'})

@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'ok': False, 'msg': '用户名和密码不能为空'})
    conn = get_db()
    admin = conn.execute(
        "SELECT id, username FROM admins WHERE username=? AND password=?",
        (username, password)
    ).fetchone()
    conn.close()
    if admin:
        session['user_id'] = admin['id']
        session['username'] = admin['username']
        session['role'] = 'admin'
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'msg': '用户名或密码错误'})

@app.route('/api/user/register', methods=['POST'])
def api_user_register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'ok': False, 'msg': '用户名和密码不能为空'})
    if len(username) > 15:
        return jsonify({'ok': False, 'msg': '用户名不能超过15个字符'})
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                     (username, password))
        conn.commit()
        return jsonify({'ok': True, 'msg': '注册成功！'})
    except sqlite3.IntegrityError:
        return jsonify({'ok': False, 'msg': '该用户名已被使用'})
    finally:
        conn.close()

@app.route('/api/admin/register', methods=['POST'])
def api_admin_register():
    data = request.get_json()
    auth_code = data.get('auth_code', '').strip()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    # 原项目中的授权码 "regon"
    if auth_code != 'regon':
        return jsonify({'ok': False, 'msg': '授权码错误，无法注册管理员'})
    if not username or not password:
        return jsonify({'ok': False, 'msg': '用户名和密码不能为空'})
    conn = get_db()
    try:
        conn.execute("INSERT INTO admins (username, password) VALUES (?, ?)",
                     (username, password))
        conn.commit()
        return jsonify({'ok': True, 'msg': '管理员注册成功！'})
    except sqlite3.IntegrityError:
        return jsonify({'ok': False, 'msg': '该用户名已被使用'})
    finally:
        conn.close()

@app.route('/api/logout', methods=['GET', 'POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})

# ── API: User Operations ──────────────────────────────────────────────────────
@app.route('/api/user/release', methods=['POST'])
@login_required(role='user')
def api_user_release():
    data = request.get_json()
    name = data.get('name', '').strip()
    price = data.get('price', '').strip()
    if not is_valid_item_name(name):
        return jsonify({'ok': False, 'msg': '商品名称不能为空且不超过15个字符'})
    if not is_valid_price(price):
        return jsonify({'ok': False, 'msg': '价格不合法（只允许数字和最多一个小数点）'})
    conn = get_db()
    conn.execute(
        "INSERT INTO items (name, price, seller_id, status) VALUES (?, ?, ?, 'available')",
        (name, price, session['user_id'])
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'msg': '商品上架成功！'})

@app.route('/api/user/items', methods=['GET'])
@login_required(role='user')
def api_user_items():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    conn = get_db()
    total = conn.execute(
        "SELECT COUNT(*) FROM items WHERE status='available'"
    ).fetchone()[0]
    items = conn.execute(
        "SELECT id, name, price, created_at FROM items WHERE status='available' ORDER BY id DESC LIMIT ? OFFSET ?",
        (per_page, offset)
    ).fetchall()
    conn.close()
    return jsonify({
        'ok': True,
        'items': [dict(row) for row in items],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

@app.route('/api/user/search', methods=['GET'])
@login_required(role='user')
def api_user_search():
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return jsonify({'ok': True, 'items': []})
    conn = get_db()
    items = conn.execute(
        "SELECT id, name, price FROM items WHERE status='available' AND name LIKE ? ORDER BY id",
        (f'%{keyword}%',)
    ).fetchall()
    conn.close()
    return jsonify({
        'ok': True,
        'items': [dict(row) for row in items]
    })

@app.route('/api/user/purchase', methods=['POST'])
@login_required(role='user')
def api_user_purchase():
    data = request.get_json()
    item_id = data.get('item_id', type=int)
    if not item_id:
        return jsonify({'ok': False, 'msg': '无效的商品ID'})
    conn = get_db()
    item = conn.execute(
        "SELECT id, status FROM items WHERE id=?", (item_id,)
    ).fetchone()
    if not item:
        conn.close()
        return jsonify({'ok': False, 'msg': '商品不存在'})
    if item['status'] != 'available':
        conn.close()
        return jsonify({'ok': False, 'msg': '该商品已售出'})
    # 检查是否已经在购物车
    existing = conn.execute(
        "SELECT id FROM purchases WHERE user_id=? AND item_id=?",
        (session['user_id'], item_id)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({'ok': False, 'msg': '该商品已在购物车中'})
    conn.execute(
        "INSERT INTO purchases (user_id, item_id) VALUES (?, ?)",
        (session['user_id'], item_id)
    )
    conn.execute("UPDATE items SET status='sold' WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'msg': '购买成功！商品已添加到您的购物车'})

@app.route('/api/user/cart', methods=['GET'])
@login_required(role='user')
def api_user_cart():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    conn = get_db()
    total = conn.execute(
        "SELECT COUNT(*) FROM purchases WHERE user_id=?",
        (session['user_id'],)
    ).fetchone()[0]
    items = conn.execute("""
        SELECT p.id as pid, i.name, i.price, p.purchased_at
        FROM purchases p
        JOIN items i ON i.id = p.item_id
        WHERE p.user_id=?
        ORDER BY p.purchased_at DESC
        LIMIT ? OFFSET ?
    """, (session['user_id'], per_page, offset)).fetchall()
    conn.close()
    return jsonify({
        'ok': True,
        'items': [dict(row) for row in items],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

# ── API: Admin Operations ─────────────────────────────────────────────────────
@app.route('/api/admin/items', methods=['GET'])
@login_required(role='admin')
def api_admin_items():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    items = conn.execute("""
        SELECT i.id, i.name, i.price, i.status,
               COALESCE(u.username, '管理员') AS seller_name,
               i.created_at
        FROM items i
        LEFT JOIN users u ON u.id = i.seller_id
        ORDER BY i.id DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()
    conn.close()
    return jsonify({
        'ok': True,
        'items': [dict(row) for row in items],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

@app.route('/api/admin/item/add', methods=['POST'])
@login_required(role='admin')
def api_admin_item_add():
    data = request.get_json()
    name = data.get('name', '').strip()
    price = data.get('price', '').strip()
    if not is_valid_item_name(name):
        return jsonify({'ok': False, 'msg': '商品名称不能为空且不超过15个字符'})
    if not is_valid_price(price):
        return jsonify({'ok': False, 'msg': '价格不合法（只允许数字和最多一个小数点）'})
    conn = get_db()
    conn.execute(
        "INSERT INTO items (name, price, seller_id, status) VALUES (?, ?, NULL, 'available')",
        (name, price)
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'msg': '商品添加成功！'})

@app.route('/api/admin/item/delete', methods=['POST'])
@login_required(role='admin')
def api_admin_item_delete():
    data = request.get_json()
    item_id = data.get('item_id', type=int)
    secondary_pwd = data.get('secondary_password', '').strip()
    # 原项目中的二级密码 "accon"
    if secondary_pwd != 'accon':
        return jsonify({'ok': False, 'msg': '二级密码错误，无法删除商品'})
    if not item_id:
        return jsonify({'ok': False, 'msg': '无效的商品ID'})
    conn = get_db()
    conn.execute("DELETE FROM purchases WHERE item_id=?", (item_id,))
    conn.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'msg': '商品删除成功！'})

@app.route('/api/admin/item/modify', methods=['POST'])
@login_required(role='admin')
def api_admin_item_modify():
    data = request.get_json()
    item_id = data.get('item_id', type=int)
    name = data.get('name', '').strip()
    price = data.get('price', '').strip()
    if not item_id:
        return jsonify({'ok': False, 'msg': '无效的商品ID'})
    if not is_valid_item_name(name):
        return jsonify({'ok': False, 'msg': '商品名称不能为空且不超过15个字符'})
    if not is_valid_price(price):
        return jsonify({'ok': False, 'msg': '价格不合法（只允许数字和最多一个小数点）'})
    conn = get_db()
    conn.execute(
        "UPDATE items SET name=?, price=? WHERE id=?",
        (name, price, item_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'msg': '商品修改成功！'})

@app.route('/api/admin/users', methods=['GET'])
@login_required(role='admin')
def api_admin_users():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    users = conn.execute("""
        SELECT u.id, u.username, u.created_at,
               (SELECT COUNT(*) FROM purchases WHERE user_id=u.id) as purchase_count
        FROM users u
        ORDER BY u.id
        LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()
    conn.close()
    return jsonify({
        'ok': True,
        'users': [dict(row) for row in users],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

@app.route('/api/admin/user/delete', methods=['POST'])
@login_required(role='admin')
def api_admin_user_delete():
    data = request.get_json()
    user_id = data.get('user_id', type=int)
    secondary_pwd = data.get('secondary_password', '').strip()
    if secondary_pwd != 'accon':
        return jsonify({'ok': False, 'msg': '二级密码错误，无法删除用户'})
    if not user_id:
        return jsonify({'ok': False, 'msg': '无效的用户ID'})
    conn = get_db()
    conn.execute("DELETE FROM purchases WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM items WHERE seller_id=?", (user_id,))
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'msg': '用户删除成功！'})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
