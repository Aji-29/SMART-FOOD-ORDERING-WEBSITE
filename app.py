import random
import string
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_socketio import SocketIO, send, emit, join_room
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import json


app = Flask(__name__)
app.config['SECRET_KEY'] = 'EasyChat'
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'restaurant_app'
socketio = SocketIO(app)
mysql = MySQL(app)

def generate_token():
    return ''.join(random.choices(string.digits, k=10))

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('welcome'))
    return render_template('login.html')

@app.route('/welcome')
def welcome(): 
    if 'user_id' in session:
        return render_template('index.html')
    return redirect(url_for('/'))

@app.route('/menu')
def menu(): 
    if 'user_id' in session:
        return render_template('menu.html')
    return redirect(url_for('/'))

@app.route('/login', methods=['GET', 'POST'])
def login():  
    if 'user_id' in session:
        return redirect(url_for('welcome'))

    if request.method == 'POST':
        name = request.form['name']
        password = request.form['password']
        
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, name, password FROM users WHERE name = %s and password = %s", [name, password])
        user = cur.fetchone()
        cur.close()
        
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('welcome'))
        else:
            flash("Invalid credentials. Please try again.")
    
    return render_template('login.html')

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, name, token FROM users WHERE id != %s", [session['user_id']])
    users = cur.fetchall()
    cur.close()
    
    return render_template('chat.html', users=users, username=session['username'])

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('index'))

@socketio.on('join')
def on_join(data):
    username = session['username']
    room = data['room']
    join_room(room)

@socketio.on('message')
def handle_message(data):
    sender_id = session['user_id']
    receiver_id = data['receiver_id']
    message = data['message']
    room = data['room']
    
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO messages (sender_id, receiver_id, message) VALUES (%s, %s, %s)", (sender_id, receiver_id, message))
    mysql.connection.commit()
    cur.close()
    # Send message to both sender and receiver
    emit('message', {'sender_id': sender_id, 'message': message}, room=room)

@socketio.on('get_messages')
def get_messages(data):
    sender_id = session['user_id']
    receiver_id = data['receiver_id']
    room = data['room']
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT sender_id, message, timestamp FROM messages WHERE (sender_id = %s AND receiver_id = %s) OR (sender_id = %s AND receiver_id = %s) ORDER BY timestamp", 
                (sender_id, receiver_id, receiver_id, sender_id))
    messages = cur.fetchall()
    cur.close()
    
    message_history = [{'sender_id': msg[0], 'message': msg[1], 'timestamp': msg[2].strftime('%Y-%m-%d %H:%M:%S'), 'who':sender_id} for msg in messages]
    
    emit('message_history', {'history': message_history}, to=room)
    # Emit the history to the client

@app.route('/product/<int:category_id>')
def product_by_category(category_id):
    cur = mysql.connection.cursor()
    cur.execute('''
        SELECT p.pid, p.product_name, p.product_img, p.product_price, c.name AS category_name
        FROM product p
        JOIN category c ON p.category_id = c.cat_id
        WHERE p.category_id = %s and p.flag=1
    ''', [category_id])
    products = cur.fetchall()
    cur.close()
    
    # You can either pass the data to a template or return it as JSON
    return render_template('product_by_category.html', products=products, category_id=category_id)

@app.route('/place_order', methods=['POST'])
def place_order():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "User not logged in"}), 401

    user_id = session['user_id']
    data = request.json

    # Convert the productQuantities to the correct format and compute the total
    product_quantities = data['productQuantities']
    overall_total = sum(float(item['total']) for item in product_quantities)
    
    # Convert the data to JSON format for storage
    order_data_in_json = json.dumps(product_quantities)
    
    cursor = mysql.connection.cursor()
    cursor.execute('''INSERT INTO `order` (order_data_in_json, user_id, overall_total, delivery_status, billing_status)
                      VALUES (%s, %s, %s, %s, %s)''', 
                   (order_data_in_json, user_id, overall_total, 'Pending', 'Unpaid'))
                   
    socketio.emit('inserted')
    mysql.connection.commit()
    order_id = cursor.lastrowid
    cursor.close()

    return jsonify({"status": "success", "message": "Order placed successfully!", "order_id": order_id})

@app.route('/order_details_page')
def order_details_page():
    return render_template('order_details.html')

@app.route('/order_details/<int:order_id>', methods=['GET'])
def order_details(order_id):
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT order_id, overall_total, order_data_in_json, delivery_status FROM `order` WHERE order_id = %s', (order_id,))
    order = cursor.fetchone()
    cursor.close()
    
    if order:
        return jsonify({"order_id": order[0], "subtotal": order[1], "order_data_in_json": order[2], "delivery_status": order[3]})
    else:
        return jsonify({"status": "error", "message": "Order not found"}), 404



# Admin Panel Functionality start
@app.route('/admin/login', methods=['GET', 'POST'])
def adminlogin():  
    if 'admin_user_id' in session:
        return redirect(url_for('adminDashboard'))

    if request.method == 'POST':
        name = request.form['name']
        password = request.form['password']
        
        cur = mysql.connection.cursor()
        cur.execute("SELECT admin_id, username, utype FROM admin WHERE username = %s and password = %s", [name, password])
        user = cur.fetchone()
        cur.close()
        
        if user:
            session['admin_user_id'] = user[0]
            session['username'] = user[1]
            if(user[2] == "C"):
                return redirect(url_for('adminDashboard'))
            else:
                return redirect(url_for('admin_delivered_order'))
        else:
            flash("Invalid credentials. Please try again.") 
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def adminDashboard():  
    if 'admin_user_id' in session:
        return render_template('admin_dashboard.html') 
    return redirect(url_for('adminlogin'))

@app.route('/admin/getDashboardInfo')
def getDashboardInfo(): 
    cur = mysql.connection.cursor()
    cur.execute("SELECT (SELECT COUNT(id) FROM `users`) as totalUsers, (SELECT COUNT(cat_id) FROM `category`) as category, (SELECT COUNT(pid) FROM `product`) as product")
    result = cur.fetchone()
    cur.close() 
    data = {
        'totalUsers': result[0],
        'category': result[1],
        'product': result[2]
    } 
    return jsonify(data)

# Admin Panel Functionality start
@app.route('/admin/category-list', methods=['GET'])
def categoryList():  
    return render_template('admin_category.html')

@app.route('/admin/categories', methods=['GET'])
def get_all_categories():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM category")
    categories = cur.fetchall()
    cur.close()
    result = []
    for category in categories:
        result.append({
            'cat_id': category[0],
            'name': category[1],
            'img': category[2],
            'flag': category[3]
        })
    return jsonify(result)

@app.route('/admin/active-categories', methods=['GET'])
def get_active_categories():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM category WHERE flag=1")
    categories = cur.fetchall()
    cur.close()
    result = []
    for category in categories:
        result.append({
            'cat_id': category[0],
            'name': category[1],
            'img': category[2],
            'flag': category[3]
        })
    return jsonify(result)

@app.route('/admin/category', methods=['POST'])
def create_category():
    data = request.json
    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO category (name, cat_img, flag) VALUES (%s, %s, %s)",
        (data['name'], data['cat_img'], data['flag'])
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({'message': 'Category created successfully'}), 201

@app.route('/admin/category/<int:cat_id>', methods=['PUT'])
def update_category(cat_id):
    data = request.json
    cur = mysql.connection.cursor()
    cur.execute(
        "UPDATE category SET name = %s, cat_img = %s, flag = %s WHERE cat_id = %s",
        (data['name'], data['cat_img'], data['flag'], cat_id)
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({'message': 'Category updated successfully'}), 200

@app.route('/admin/category/<int:cat_id>', methods=['DELETE'])
def delete_category(cat_id):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM category WHERE cat_id = %s", [cat_id])
    mysql.connection.commit()
    cur.close()
    return jsonify({'message': 'Category deleted successfully'}), 200
# Admin Panel Functionality end


# Product
@app.route('/admin/product', methods=['GET'])
def adminProduct():  
    return render_template('admin_product.html')

@app.route('/admin/product-list', methods=['GET'])
def productList():
    cur = mysql.connection.cursor()
    query = '''
        SELECT p.pid, p.product_name, p.product_img, p.product_price, c.name AS category_name, p.flag, p.category_id
        FROM product p
        JOIN category c ON p.category_id = c.cat_id
    '''
    cur.execute(query)
    products = cur.fetchall()
    cur.close()
    
    result = []
    for product in products:
        result.append({
            'pid': product[0],
            'product_name': product[1],
            'product_img': product[2],
            'product_price': product[3],
            'category_name': product[4],
            'flag': product[5],
            'category_id': product[6]
        })
    
    return jsonify(result)

from flask import request, jsonify

# Insert or update product
@app.route('/admin/product', methods=['POST'])
def create_product():
    data = request.json
    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO product (product_name, category_id, product_img, product_price, flag) VALUES (%s, %s, %s, %s, %s)",
        (data['product_name'], data['category_id'], data['product_img'], data['product_price'], data['flag'])
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({'message': 'Product created successfully'}), 201

@app.route('/admin/product/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    data = request.json
    cur = mysql.connection.cursor()
    cur.execute(
        "UPDATE product SET product_name = %s, category_id = %s, product_img = %s, product_price = %s, flag = %s WHERE pid = %s",
        (data['product_name'], data['category_id'], data['product_img'], data['product_price'], data['flag'], product_id)
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({'message': 'Product updated successfully'}), 200

# Delete product
@app.route('/admin/product/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM product WHERE pid = %s", [product_id])
    mysql.connection.commit()
    cur.close()
    return jsonify({'message': 'Product deleted successfully'}), 200

@app.route('/admin/order')
def admin_order():
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM `order`')
    orders = cursor.fetchall()
    return render_template('admin_order.html', orders=orders)

@app.route('/admin/get_orders', methods=['GET'])
def get_orders():
    cursor = mysql.connection.cursor()
    query = """
        SELECT 
            o.order_id, 
            o.overall_total AS subtotal, 
            o.delivery_status,
            u.name AS name
        FROM `order` o
        JOIN `users` u ON o.user_id = u.id WHERE NOT o.delivery_status = 'Delivered' ORDER BY o.order_id DESC
    """
    cursor.execute(query)
    orders = cursor.fetchall()
    return jsonify({'orders': orders})

@app.route('/admin/order_details/<int:order_id>', methods=['GET'])
def get_order_details(order_id):
    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT order_data_in_json, overall_total AS subtotal, delivery_status
        FROM `order`
        WHERE order_id = %s
    """, [order_id])
    order = cursor.fetchone()
    
    if order:
        order_data = order[0]  # JSON data as a string
        subtotal = order[1]
        delivery_status = order[2]
        
        # Convert JSON string to a Python object
        import json
        order_items = json.loads(order_data)
    else:
        order_items = []
        subtotal = 0
        delivery_status = 'Unknown'
    
    return jsonify({
        'order_items': order_items,
        'subtotal': subtotal,
        'delivery_status': delivery_status
    })

@app.route('/admin/update_order_status', methods=['POST'])
def update_order_status():
    order_id = request.form['order_id']
    status = request.form['status']
    
    # Update the status in the database
    cursor = mysql.connection.cursor()
    cursor.execute("""UPDATE `order` SET delivery_status = %s WHERE order_id = %s""", [status, order_id])
    mysql.connection.commit()
    
    # Fetch user_id for the updated order
    cursor.execute("""SELECT user_id FROM `order` WHERE order_id = %s""", [order_id])
    user_result = cursor.fetchone()  # Returns a tuple if not using DictCursor
    if user_result:
        user_id = user_result[0]  # Access the user_id from the tuple
        # print(session['user_id'])
        # Notify the specific user if the status is "delivered"
        #  and session['user_id'] == user_id
        if status.lower() == 'delivered': 
            socketio.emit('delivered')
        socketio.emit('order_delivered', {'order_id': order_id, "status": status}, room="common")
    
    return jsonify({'message': 'Status updated successfully!'})

@app.route('/admin/delivered_order')
def admin_delivered_order():
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM `order`')
    orders = cursor.fetchall()
    return render_template('admin_delivered.html', orders=orders)

@app.route('/admin/get_delivered_orders')
def get_delivered_orders():
    cursor = mysql.connection.cursor()
    query = """
        SELECT o.order_id, o.overall_total AS subtotal, o.billing_status, u.name AS name FROM `order` o JOIN `users` u ON o.user_id = u.id WHERE o.delivery_status = 'Delivered' ORDER BY o.billing_status DESC, o.updated_at DESC
    """
    cursor.execute(query)
    orders = cursor.fetchall()
    return jsonify({'orders': orders})

    
@app.route('/admin/update_delivery_order_status', methods=['POST'])
def update_delivery_order_status():
    order_id = request.form['order_id']
    status = request.form['status']
    
    # Update the status in the database
    cursor = mysql.connection.cursor()
    cursor.execute("""UPDATE `order` SET billing_status = %s WHERE order_id = %s""", [status, order_id])
    mysql.connection.commit()
    
    # Fetch user_id for the updated order
    cursor.execute("""SELECT user_id FROM `order` WHERE order_id = %s""", [order_id])
    user_result = cursor.fetchone()  # Returns a tuple if not using DictCursor
    if user_result:
        user_id = user_result[0]  # Access the user_id from the tuple
        # print(session['user_id'])
        # Notify the specific user if the status is "delivered"
        #  and session['user_id'] == user_id
        # if status.lower() == 'delivered':
        socketio.emit('delivery_order_delivered', {'order_id': order_id, "status": status}, room="common")
    
    return jsonify({'message': 'Status updated successfully!'})


# SocketIO events
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('join')
def join(user_id):
    user_id = "common"
    join_room(user_id)
    print(f'User {user_id} joined room')


@app.route('/admin/logout')
def adminLogout():
    session.pop('admin_user_id', None)
    session.pop('username', None)
    return redirect(url_for('adminlogin'))
# Admin Panel Functionality end

if __name__ == '__main__':
    socketio.run(app, debug=True) # For Internal Access
    # socketio.run(app, host='192.168.1.8', port=5000, debug=True) # For General Access
