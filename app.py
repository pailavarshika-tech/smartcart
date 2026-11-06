
from flask import Flask, render_template, request, redirect, session, flash, send_file
from flask_mail import Mail, Message
import mysql.connector
import bcrypt
import random
import config
import os
import razorpay
from utils.pdf_generator import generate_invoice_pdf

app = Flask(__name__)
app.secret_key = config.SECRET_KEY


# ---------------- EMAIL CONFIGURATION ----------------
app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USE_TLS'] = config.MAIL_USE_TLS
app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
app.config['MAIL_PASSWORD'] = config.MAIL_PASSWORD

mail = Mail(app)

# Razorpay test/live keys are read from config.py. Use YOUR OWN keys.
RAZORPAY_KEY_ID = getattr(config, 'RAZORPAY_KEY_ID', '').strip()
RAZORPAY_KEY_SECRET = getattr(config, 'RAZORPAY_KEY_SECRET', '').strip()
razorpay_client = (
    razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET else None
)


# ---------------- DATABASE CONNECTION ----------------
def get_db_connection():
    return mysql.connector.connect(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME
    )

ADMIN_UPLOAD_FOLDER = os.path.join('static', 'uploads', 'admin_profiles')
USER_UPLOAD_FOLDER = os.path.join('static', 'uploads', 'user_profiles')
PRODUCT_UPLOAD_FOLDER = os.path.join('static', 'uploads', 'product_images')

app.config['ADMIN_UPLOAD_FOLDER'] = ADMIN_UPLOAD_FOLDER
app.config['USER_UPLOAD_FOLDER'] = USER_UPLOAD_FOLDER
app.config['UPLOAD_FOLDER'] = PRODUCT_UPLOAD_FOLDER

os.makedirs(ADMIN_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(USER_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PRODUCT_UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------
# ROUTE 0: HOME / LANDING PAGE
# ---------------------------------------------------------
@app.route('/')
def index():
    if 'admin_id' in session:
        return redirect('/admin-dashboard')
    if 'user_id' in session:
        return redirect('/user-dashboard')
    return render_template('index.html')


# ---------------------------------------------------------
# ROUTE 1: ADMIN SIGNUP - SEND OTP
# ---------------------------------------------------------
@app.route('/admin-signup', methods=['GET', 'POST'])
def admin_signup():

    if request.method == 'GET':
        return render_template('admin/admin_signup.html')

    name = request.form['name'].strip()
    email = request.form['email'].strip().lower()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT admin_id FROM admin WHERE email = %s",
            (email,)
        )
        existing_admin = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if existing_admin:
        flash("This email is already registered. Please login.", "danger")
        return redirect('/admin-signup')

    session['signup_name'] = name
    session['signup_email'] = email

    otp = random.randint(100000, 999999)
    session['otp'] = otp

    try:
        message = Message(
            subject="SmartCart Admin OTP",
            sender=config.MAIL_USERNAME,
            recipients=[email]
        )
        message.body = (
            f"Your OTP for SmartCart Admin Registration is: {otp}"
        )
        mail.send(message)

    except Exception:
        session.pop('otp', None)
        session.pop('signup_name', None)
        session.pop('signup_email', None)
        flash("Unable to send OTP. Check your email settings.", "danger")
        return redirect('/admin-signup')

    flash("OTP sent to your email!", "success")
    return redirect('/verify-otp')


# ---------------------------------------------------------
# ROUTE 2: DISPLAY OTP VERIFICATION PAGE
# ---------------------------------------------------------
@app.route('/verify-otp', methods=['GET'])
def verify_otp_get():

    if 'otp' not in session:
        flash("Please register first.", "danger")
        return redirect('/admin-signup')

    return render_template('admin/verify_otp.html')


# ---------------------------------------------------------
# ROUTE 3: VERIFY OTP AND SAVE ADMIN
# ---------------------------------------------------------
@app.route('/verify-otp', methods=['POST'])
def verify_otp_post():

    if 'otp' not in session or 'signup_email' not in session:
        flash("Your registration session expired. Please register again.", "danger")
        return redirect('/admin-signup')

    user_otp = request.form['otp'].strip()
    password = request.form['password']

    if str(session.get('otp')) != user_otp:
        flash("Invalid OTP. Try again!", "danger")
        return redirect('/verify-otp')

    if not password:
        flash("Password cannot be empty.", "danger")
        return redirect('/verify-otp')

    # Hash password before storing it
    hashed_password = bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO admin (name, email, password) VALUES (%s, %s, %s)",
            (
                session['signup_name'],
                session['signup_email'],
                hashed_password
            )
        )
        conn.commit()

    except mysql.connector.Error:
        conn.rollback()
        flash("Registration failed. Please try again.", "danger")
        return redirect('/admin-signup')

    finally:
        cursor.close()
        conn.close()

    session.pop('otp', None)
    session.pop('signup_name', None)
    session.pop('signup_email', None)

    flash("Admin registered successfully! Please login.", "success")
    return redirect('/admin-login')


# ---------------------------------------------------------
# ROUTE 4: ADMIN LOGIN
# ---------------------------------------------------------
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'GET':
        return render_template('admin/admin_login.html')

    email = request.form['email'].strip().lower()
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT * FROM admin WHERE email = %s",
            (email,)
        )
        admin = cursor.fetchone()

    finally:
        cursor.close()
        conn.close()

    if admin is None:
        flash("Email not found. Please register first.", "danger")
        return redirect('/admin-login')

    stored_hash = admin['password']

    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode('utf-8')

    if not bcrypt.checkpw(password.encode('utf-8'), stored_hash):
        flash("Incorrect password. Try again.", "danger")
        return redirect('/admin-login')

    # Create a fresh session after successful login
    session.clear()
    session['admin_id'] = admin['admin_id']
    session['admin_name'] = admin['name']
    session['admin_email'] = admin['email']
    session['admin_image'] = admin.get('profile_image')

    flash("Login successful!", "success")
    return redirect('/admin-dashboard')


# ---------------------------------------------------------
# ROUTE 5: PROTECTED ADMIN DASHBOARD
# ---------------------------------------------------------
@app.route('/admin-dashboard')
def admin_dashboard():

    if 'admin_id' not in session:
        flash("Please login to access the dashboard.", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM admin WHERE admin_id = %s", (admin_id,))
        admin = cursor.fetchone()

        cursor.execute("SELECT COUNT(*) AS total_products FROM products")
        stats_prod = cursor.fetchone()

        cursor.execute("SELECT COUNT(DISTINCT category) AS total_categories FROM products")
        stats_cat = cursor.fetchone()

        cursor.execute("SELECT COUNT(*) AS total_orders, COALESCE(SUM(amount), 0) AS total_revenue FROM orders")
        stats_orders = cursor.fetchone()

        cursor.execute("SELECT * FROM products ORDER BY product_id DESC LIMIT 6")
        recent_products = cursor.fetchall()

        stats = {
            'total_products': stats_prod['total_products'] if stats_prod else 0,
            'total_categories': stats_cat['total_categories'] if stats_cat else 0,
            'total_orders': stats_orders['total_orders'] if stats_orders else 0,
            'total_revenue': float(stats_orders['total_revenue']) if stats_orders and stats_orders['total_revenue'] else 0.0
        }

        return render_template(
            'admin/dashboard.html',
            admin_name=session.get('admin_name', admin['name'] if admin else 'Admin'),
            admin=admin,
            stats=stats,
            recent_products=recent_products
        )
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------
# ROUTE 6: ADMIN LOGOUT
# ---------------------------------------------------------
@app.route('/admin-logout', methods=['GET', 'POST'])
def admin_logout():

    session.clear()
    flash("Logged out successfully.", "success")
    return redirect('/admin-login')

import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads/product_images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/admin/add-item', methods=['GET'])
def add_item_page():

    # Only logged-in admin can access
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    return render_template("admin/add_item.html")



# =================================================================
# ROUTE 8: ADD PRODUCT INTO DATABASE
# =================================================================
@app.route('/admin/add-item', methods=['POST'])
def add_item():

    # Check admin session
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    # 1️⃣ Get form data
    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']
    image_file = request.files['image']

    # 2️⃣ Validate image upload
    if image_file.filename == "":
        flash("Please upload a product image!", "danger")
        return redirect('/admin/add-item')

    # 3️⃣ Secure the file name
    filename = secure_filename(image_file.filename)

    # 4️⃣ Create full path
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    # 5️⃣ Save image into folder
    image_file.save(image_path)

    # 6️⃣ Insert product into database
    conn = get_db_connection()
    cursor = conn.cursor()

    
    cursor.execute(
    """INSERT INTO products
    (name, description, category, price, image, admin_id)
    VALUES (%s, %s, %s, %s, %s, %s)""",
    (name, description, category, price, filename, session['admin_id'])
    )


    conn.commit()
    cursor.close()
    conn.close()

    flash("Product added successfully!", "success")
    return redirect('/admin/add-item')

# =================================================================
# ROUTE 13:UPDATED PRODUCT LIST WITH SEARCH + CATEGORY FILTER
# =================================================================
@app.route('/admin/item-list')
def item_list():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1️⃣ Fetch category list for dropdown
    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    # 2️⃣ Build dynamic query based on filters
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE %s"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND category = %s"
        params.append(category_filter)

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin/item_list.html",
        products=products,
        categories=categories
    )

# =================================================================
#  route-13 DELETE PRODUCT (DELETE DB ROW + DELETE IMAGE FILE)
# =================================================================
@app.route('/admin/delete-item/<int:item_id>')
def delete_item(item_id):

    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1️⃣ Fetch product to get image name
    cursor.execute("SELECT image FROM products WHERE product_id=%s", (item_id,))
    product = cursor.fetchone()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    image_name = product['image']

    # Delete image from folder
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
    if os.path.exists(image_path):
        os.remove(image_path)

    # 2️⃣ Delete product from DB
    cursor.execute("DELETE FROM products WHERE product_id=%s", (item_id,))
    conn.commit()

    cursor.close()
    conn.close()

    flash("Product deleted successfully!", "success")
    return redirect('/admin/item-list')


#=================================================================
# ROUTE 10: VIEW SINGLE PRODUCT DETAILS
# =================================================================
@app.route('/admin/view-item/<int:item_id>')
def view_item(item_id):

    # Check admin session
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/view_item.html", product=product)


# =================================================================
# ROUTE 11: SHOW UPDATE FORM WITH EXISTING DATA
# =================================================================
@app.route('/admin/update-item/<int:item_id>', methods=['GET'])
def update_item_page(item_id):

    # Check login
    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    # Fetch product data
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/update_item.html", product=product)


# =================================================================
# ROUTE-12: UPDATE PRODUCT + OPTIONAL IMAGE REPLACE
# =================================================================
@app.route('/admin/update-item/<int:item_id>', methods=['POST'])
def update_item(item_id):

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    # 1️⃣ Get updated form data
    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']

    new_image = request.files['image']

    # 2️⃣ Fetch old product data
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    old_image_name = product['image']

    # 3️⃣ If admin uploaded a new image → replace it
    if new_image and new_image.filename != "":
        
        # Secure filename
        from werkzeug.utils import secure_filename
        new_filename = secure_filename(new_image.filename)

        # Save new image
        new_image_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
        new_image.save(new_image_path)

        # Delete old image file
        old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], old_image_name)
        if os.path.exists(old_image_path):
            os.remove(old_image_path)

        final_image_name = new_filename

    else:
        # No new image uploaded → keep old one
        final_image_name = old_image_name

    # 4️⃣ Update product in the database
    cursor.execute("""
        UPDATE products
        SET name=%s, description=%s, category=%s, price=%s, image=%s
        WHERE product_id=%s
    """, (name, description, category, price, final_image_name, item_id))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Product updated successfully!", "success")
    return redirect('/admin/item-list')


# Show Admin Profile
@app.route('/admin/profile', methods=['GET'])
def admin_profile():
    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM admin WHERE admin_id = %s",
        (admin_id,)
    )
    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    if not admin:
        flash("Admin not found!", "danger")
        return redirect('/admin-login')

    return render_template("admin/admin_profile.html", admin=admin)



# Update Admin Profile
@app.route('/admin/profile', methods=['POST'])
def admin_profile_update():
    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']
    name = request.form['name'].strip()
    email = request.form['email'].strip()
    new_password = request.form.get('password', '').strip()
    new_image = request.files.get('profile_image')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT * FROM admin WHERE admin_id = %s",
            (admin_id,)
        )
        admin = cursor.fetchone()

        if not admin:
            flash("Admin not found!", "danger")
            return redirect('/admin-login')

        old_password = admin['password']
        old_image_name = admin.get('profile_image')

        if new_password:
            hashed_password = bcrypt.hashpw(
                new_password.encode('utf-8'),
                bcrypt.gensalt()
            )
        else:
            hashed_password = old_password

        final_image_name = old_image_name

        if new_image and new_image.filename:
            from werkzeug.utils import secure_filename

            new_filename = secure_filename(new_image.filename)

            if not new_filename:
                flash("Invalid image filename!", "danger")
                return redirect('/admin/profile')

            extension = os.path.splitext(new_filename)[1].lower()
            allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

            if extension not in allowed_extensions:
                flash("Please upload a valid image file!", "danger")
                return redirect('/admin/profile')

            # Use a unique filename to avoid overwriting files
            new_filename = f"{admin_id}_{new_filename}"
            upload_folder = app.config['ADMIN_UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)

            image_path = os.path.join(upload_folder, new_filename)
            new_image.save(image_path)
            final_image_name = new_filename

        cursor.execute("""
            UPDATE admin
            SET name = %s, email = %s, password = %s,
                profile_image = %s
            WHERE admin_id = %s
        """, (
            name, email, hashed_password,
            final_image_name, admin_id
        ))

        conn.commit()

        session['admin_name'] = name
        session['admin_email'] = email
        if final_image_name:
            session['admin_image'] = final_image_name

        # Delete old image only after database update succeeds
        if new_image and new_image.filename and old_image_name:
            old_image_path = os.path.join(
                app.config['ADMIN_UPLOAD_FOLDER'],
                old_image_name
            )
            if os.path.isfile(old_image_path):
                os.remove(old_image_path)

        flash("Profile updated successfully!", "success")
        return redirect('/admin/profile')

    except Exception:
        conn.rollback()
        app.logger.exception("Admin profile update failed")
        flash("Profile update failed. Please try again.", "danger")
        return redirect('/admin/profile')

    finally:
        cursor.close()
        conn.close()



# ---------------------------------------------------------
# FORGOT PASSWORD: SEND OTP TO REGISTERED ADMIN EMAIL
# ---------------------------------------------------------
@app.route('/admin-forgot-password', methods=['GET', 'POST'])
def admin_forgot_password():
    if request.method == 'GET':
        return render_template('admin/forgot_password.html')

    email = request.form.get('email', '').strip().lower()
    if not email:
        flash("Please enter your registered email.", "danger")
        return redirect('/admin-forgot-password')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT admin_id FROM admin WHERE email = %s", (email,))
        admin = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    # Do not disclose whether an email address is registered.
    if not admin:
        flash("If this email is registered, a reset OTP will be sent.", "info")
        return redirect('/admin-forgot-password')

    otp = str(random.randint(100000, 999999))
    session['reset_email'] = email
    session['reset_otp'] = otp
    session['reset_otp_created'] = __import__('time').time()

    try:
        message = Message(
            subject="SmartCart Password Reset OTP",
            sender=config.MAIL_USERNAME,
            recipients=[email]
        )
        message.body = (
            f"Your SmartCart password reset OTP is {otp}. "
            "It expires in 10 minutes. If you did not request this, ignore this email."
        )
        mail.send(message)
    except Exception:
        app.logger.exception("Could not send password reset OTP")
        session.pop('reset_email', None)
        session.pop('reset_otp', None)
        session.pop('reset_otp_created', None)
        flash("Unable to send the reset OTP. Please check email settings and try again.", "danger")
        return redirect('/admin-forgot-password')

    flash("If this email is registered, a reset OTP has been sent.", "success")
    return redirect('/admin-reset-password')


# ---------------------------------------------------------
# RESET PASSWORD: VERIFY OTP AND SAVE NEW HASHED PASSWORD
# ---------------------------------------------------------
@app.route('/admin-reset-password', methods=['GET', 'POST'])
def admin_reset_password():
    if not session.get('reset_email') or not session.get('reset_otp'):
        flash("Please request a password reset OTP first.", "danger")
        return redirect('/admin-forgot-password')

    if request.method == 'GET':
        return render_template('admin/reset_password.html')

    otp = request.form.get('otp', '').strip()
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    created = session.get('reset_otp_created', 0)
    if __import__('time').time() - created > 600:
        for key in ('reset_email', 'reset_otp', 'reset_otp_created'):
            session.pop(key, None)
        flash("OTP expired. Please request a new one.", "danger")
        return redirect('/admin-forgot-password')

    if otp != str(session.get('reset_otp')):
        flash("Invalid OTP. Please try again.", "danger")
        return redirect('/admin-reset-password')

    if len(new_password) < 8:
        flash("Password must be at least 8 characters long.", "danger")
        return redirect('/admin-reset-password')

    if new_password != confirm_password:
        flash("Passwords do not match.", "danger")
        return redirect('/admin-reset-password')

    hashed_password = bcrypt.hashpw(
        new_password.encode('utf-8'), bcrypt.gensalt()
    ).decode('utf-8')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE admin SET password = %s WHERE email = %s",
            (hashed_password, session['reset_email'])
        )
        if cursor.rowcount != 1:
            conn.rollback()
            flash("Password reset failed. Please request a new OTP.", "danger")
            return redirect('/admin-forgot-password')
        conn.commit()
    except mysql.connector.Error:
        conn.rollback()
        app.logger.exception("Password reset database update failed")
        flash("Unable to reset password right now. Please try again.", "danger")
        return redirect('/admin-reset-password')
    finally:
        cursor.close()
        conn.close()

    for key in ('reset_email', 'reset_otp', 'reset_otp_created'):
        session.pop(key, None)
    flash("Password reset successful. Please log in with your new password.", "success")
    return redirect('/admin-login')

# ROUTE: USER REGISTRATION
# =================================================================
@app.route('/user-register', methods=['GET', 'POST'])
def user_register():

    if request.method == 'GET':
        return render_template("user/user_register.html")

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    profile_image = request.files.get('profile_image')

    if not name or not email or not password:
        flash("Name, email and password are required!", "danger")
        return redirect('/user-register')

    # Check if user already exists
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT user_id FROM users WHERE email=%s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            flash("Email already registered! Please login.", "danger")
            return redirect('/user-register')

        final_image_name = None
        if profile_image and profile_image.filename:
            from werkzeug.utils import secure_filename
            new_filename = secure_filename(profile_image.filename)
            if new_filename:
                ext = os.path.splitext(new_filename)[1].lower()
                allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
                if ext in allowed_extensions:
                    final_image_name = f"user_reg_{random.randint(10000, 99999)}_{new_filename}"
                    upload_folder = app.config['USER_UPLOAD_FOLDER']
                    os.makedirs(upload_folder, exist_ok=True)
                    profile_image.save(os.path.join(upload_folder, final_image_name))

        # Hash password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Insert new user with optional profile image
        cursor.execute(
            "INSERT INTO users (name, email, password, profile_image) VALUES (%s, %s, %s, %s)",
            (name, email, hashed_password, final_image_name)
        )
        conn.commit()
        new_user_id = cursor.lastrowid

        # Auto-login the newly registered user so they instantly see their user profile
        session['user_id'] = new_user_id
        session['user_name'] = name
        session['user_email'] = email
        if final_image_name:
            session['user_image'] = final_image_name

        flash(f"Welcome to SmartCart, {name}! Your profile is ready.", "success")
        return redirect('/user-dashboard')

    except Exception:
        conn.rollback()
        app.logger.exception("User registration failed")
        flash("Registration failed. Please try again.", "danger")
        return redirect('/user-register')
    finally:
        cursor.close()
        conn.close()

# ROUTE 2: User Login (GET + POST)
# =================================================================
# ROUTE: USER LOGIN
# =================================================================
@app.route('/user-login', methods=['GET', 'POST'])
def user_login():

    if request.method == 'GET':
        return render_template("user/user_login.html")

    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        if not user:
            flash("Email not found! Please register.", "danger")
            return redirect('/user-login')

        # Verify password
        stored_hash = user['password']
        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode('utf-8')

        if not bcrypt.checkpw(password.encode('utf-8'), stored_hash):
            flash("Incorrect password!", "danger")
            return redirect('/user-login')

        # Create user session
        session['user_id'] = user['user_id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']
        session['user_image'] = user.get('profile_image')

        flash(f"Welcome back, {user['name']}!", "success")
        return redirect('/user-dashboard')

    finally:
        cursor.close()
        conn.close()

# ROUTE 3: User Dashboard (Protected)
# =================================================================
# ROUTE: USER DASHBOARD
# =================================================================
@app.route('/user-dashboard')
def user_dashboard():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        # Fetch recent orders for this user
        cursor.execute("""
            SELECT * FROM orders
            WHERE user_id = %s
            ORDER BY order_id DESC
            LIMIT 5
        """, (user_id,))
        recent_orders = cursor.fetchall()

        # Fetch stats for this user
        cursor.execute("""
            SELECT COUNT(*) AS order_count, COALESCE(SUM(amount), 0) AS total_spend
            FROM orders
            WHERE user_id = %s
        """, (user_id,))
        user_stats = cursor.fetchone()

        cart = session.get('cart', {})
        cart_count = sum(int(item.get('quantity', 0)) for item in cart.values())

        stats = {
            'order_count': user_stats['order_count'] if user_stats else 0,
            'total_spend': float(user_stats['total_spend']) if user_stats and user_stats['total_spend'] else 0.0,
            'cart_count': cart_count
        }

        return render_template(
            "user/user_home.html",
            user=user,
            user_name=session.get('user_name', user['name'] if user else 'User'),
            recent_orders=recent_orders,
            stats=stats
        )
    finally:
        cursor.close()
        conn.close()

# ROUTE: USER PROFILE (VIEW + UPDATE)
# =================================================================
@app.route('/user/profile', methods=['GET', 'POST'])
def user_profile():
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            new_password = request.form.get('password', '').strip()
            new_image = request.files.get('profile_image')

            if not name or not email:
                flash("Name and email are required.", "danger")
                return redirect('/user/profile')

            cursor.execute("SELECT user_id FROM users WHERE email=%s AND user_id != %s", (email, user_id))
            if cursor.fetchone():
                flash("This email is already used by another account.", "danger")
                return redirect('/user/profile')

            cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            current_user = cursor.fetchone()
            if not current_user:
                session.clear()
                flash("Account not found. Please log in again.", "danger")
                return redirect('/user-login')

            old_image_name = current_user.get('profile_image')
            final_image_name = old_image_name

            if new_image and new_image.filename:
                from werkzeug.utils import secure_filename
                new_filename = secure_filename(new_image.filename)
                if not new_filename:
                    flash("Invalid image filename!", "danger")
                    return redirect('/user/profile')

                extension = os.path.splitext(new_filename)[1].lower()
                allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
                if extension not in allowed_extensions:
                    flash("Please upload a valid image file (.jpg, .jpeg, .png, .webp)!", "danger")
                    return redirect('/user/profile')

                new_filename = f"user_{user_id}_{random.randint(1000, 9999)}_{new_filename}"
                upload_folder = app.config['USER_UPLOAD_FOLDER']
                os.makedirs(upload_folder, exist_ok=True)

                image_path = os.path.join(upload_folder, new_filename)
                new_image.save(image_path)
                final_image_name = new_filename

            if new_password:
                hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                cursor.execute(
                    "UPDATE users SET name=%s, email=%s, password=%s, profile_image=%s WHERE user_id=%s",
                    (name, email, hashed_password, final_image_name, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE users SET name=%s, email=%s, profile_image=%s WHERE user_id=%s",
                    (name, email, final_image_name, user_id)
                )

            conn.commit()
            session['user_name'] = name
            session['user_email'] = email
            if final_image_name:
                session['user_image'] = final_image_name

            # Delete old image if new one was uploaded
            if new_image and new_image.filename and old_image_name and old_image_name != final_image_name:
                old_path = os.path.join(app.config['USER_UPLOAD_FOLDER'], old_image_name)
                if os.path.isfile(old_path):
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass

            flash("Profile updated successfully!", "success")
            return redirect('/user/profile')

        # GET request
        cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
        user = cursor.fetchone()
        if not user:
            session.clear()
            flash("User account not found. Please login again.", "danger")
            return redirect('/user-login')

        # Fetch all orders for this user for the profile order history
        cursor.execute("""
            SELECT * FROM orders
            WHERE user_id = %s
            ORDER BY order_id DESC
        """, (user_id,))
        orders = cursor.fetchall()

        return render_template('user/user_profile.html', user=user, orders=orders)

    except Exception:
        conn.rollback()
        app.logger.exception("User profile operation failed")
        flash("Unable to update profile. Please try again.", "danger")
        return redirect('/user/profile')
    finally:
        cursor.close()
        conn.close()


# ROUTE 4: User Logout
# =================================================================
# ROUTE: USER LOGOUT
# =================================================================
@app.route('/user-logout')
def user_logout():
    
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('user_email', None)
    session.pop('user_image', None)

    flash("Logged out successfully!", "success")
    return redirect('/user-login')

# ROUTE: USER PRODUCT LISTING (SEARCH + FILTER)
# =================================================================
@app.route('/user/products')
def user_products():

    # Optional: restrict only logged-in users
    if 'user_id' not in session:
        flash("Please login to view products!", "danger")
        return redirect('/user-login')

    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch categories for filter dropdown
    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    # Build dynamic SQL
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE %s"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND category = %s"
        params.append(category_filter)

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "user/user_products.html",
        products=products,
        categories=categories
    )

#⭐ ROUTE 2: Single Product Details Page
# =================================================================
# ROUTE: USER PRODUCT DETAILS PAGE
# =================================================================
@app.route('/user/product/<int:product_id>')
def user_product_details(product_id):

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (product_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/user/products')

    return render_template("user/product_details.html", product=product)




#⭐ ROUTE 1: Add to Cart
# =================================================================
# ADD ITEM TO CART
# =================================================================
@app.route('/user/add-to-cart/<int:product_id>')
def add_to_cart(product_id):

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    # Create cart if doesn't exist
    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']

    # Get product
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE product_id=%s", (product_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()

    if not product:
        flash("Product not found.", "danger")
        return redirect(request.referrer)

    pid = str(product_id)

    # If exists → increase quantity
    if pid in cart:
        cart[pid]['quantity'] += 1
    else:
        cart[pid] = {
            'name': product['name'],
            'price': float(product['price']),
            'image': product['image'],
            'quantity': 1
        }

    session['cart'] = cart

    flash("Item added to cart!", "success")
    return redirect('/user/cart') 
    return redirect(request.referrer)   # ⭐ Return to same page________________________________________
#⭐ ROUTE 2: View Cart Page
# =================================================================
# VIEW CART PAGE
# =================================================================
@app.route('/user/cart')
def view_cart():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})

    # Calculate total
    grand_total = sum(item['price'] * item['quantity'] for item in cart.values())

    return render_template("user/cart.html", cart=cart, grand_total=grand_total)

#⭐ ROUTE 3: Increase Quantity
# =================================================================
# INCREASE QUANTITY
# =================================================================
@app.route('/user/cart/increase/<pid>')
def increase_quantity(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart[pid]['quantity'] += 1

    session['cart'] = cart
    return redirect('/user/cart')

 #ROUTE 4: Decrease Quantity
# =================================================================
# DECREASE QUANTITY
# =================================================================
@app.route('/user/cart/decrease/<pid>')
def decrease_quantity(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart[pid]['quantity'] -= 1

        # If quantity becomes 0 → remove item
        if cart[pid]['quantity'] <= 0:
            cart.pop(pid)

    session['cart'] = cart
    return redirect('/user/cart')

#⭐ ROUTE 5: Remove Item Completely
# =================================================================
# REMOVE ITEM
# =================================================================
@app.route('/user/cart/remove/<pid>')
def remove_from_cart(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart.pop(pid)

    session['cart'] = cart

    flash("Item removed!", "success")
    return redirect('/user/cart')






# =================================================================
# CHECKOUT: SELECTED CART ITEMS -> ADDRESS -> RAZORPAY PAYMENT
# =================================================================
def get_selected_checkout_items():
    cart = session.get('cart', {})
    selected_ids = session.get('checkout_selected', [])
    selected_items = {pid: cart[pid] for pid in selected_ids if pid in cart}
    total = sum(float(item['price']) * int(item['quantity']) for item in selected_items.values())
    return selected_items, round(total, 2)



@app.route('/user/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})
    selected_ids = request.form.getlist('selected_products') or request.form.getlist('selected_items')
    selected_items = {pid: cart[pid] for pid in selected_ids if pid in cart}

    if not selected_items:
        flash("Please select at least one product.", "warning")
        return redirect('/user/cart')

    session['checkout_selected'] = list(selected_items.keys())
    total = sum(float(item['price']) * int(item['quantity']) for item in selected_items.values())
    return render_template(
        'user/checkout_address.html',
        selected_items=selected_items,
        selected_total=round(total, 2),
        user_name=session.get('user_name', ''),
        form_data=session.get('checkout_address', {})
    )


@app.route('/user/save-address', methods=['POST'])
def save_address():
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    selected_items, selected_total = get_selected_checkout_items()
    if not selected_items:
        flash("Please select products from your cart first.", "warning")
        return redirect('/user/cart')

    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()
    city = request.form.get('city', '').strip()
    state = request.form.get('state', '').strip()
    pincode = request.form.get('pincode', '').strip()

    if not all([full_name, phone, address, city, state, pincode]):
        flash("Please fill in all address details.", "danger")
        return render_template('user/checkout_address.html', selected_items=selected_items,
            selected_total=selected_total, user_name=session.get('user_name', ''), form_data=request.form)
    if not phone.isdigit() or len(phone) != 10 or phone[0] not in '6789':
        flash("Enter a valid 10-digit mobile number.", "danger")
        return render_template('user/checkout_address.html', selected_items=selected_items,
            selected_total=selected_total, user_name=session.get('user_name', ''), form_data=request.form)
    if not pincode.isdigit() or len(pincode) != 6:
        flash("PIN code must contain 6 digits.", "danger")
        return render_template('user/checkout_address.html', selected_items=selected_items,
            selected_total=selected_total, user_name=session.get('user_name', ''), form_data=request.form)

    session['checkout_address'] = {
        'full_name': full_name, 'phone': phone, 'address': address,
        'city': city, 'state': state, 'pincode': pincode,
        'email': session.get('user_email', '')
    }
    return redirect('/user/pay')


@app.route('/user/pay')
def user_pay():
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    selected_items, total = get_selected_checkout_items()
    delivery = session.get('checkout_address')
    if not selected_items:
        flash("Please select products first.", "warning")
        return redirect('/user/cart')
    if not delivery:
        return redirect('/user/cart')
    if razorpay_client is None:
        flash("Add your own Razorpay test Key ID and Key Secret in config.py to enable payment.", "warning")
        return render_template('user/checkout_review.html', selected_items=selected_items,
            selected_total=total, delivery_address=delivery, payment_setup_needed=True)

    amount_paise = int(round(total * 100))
    try:
        order = razorpay_client.order.create({
            'amount': amount_paise, 'currency': 'INR', 'payment_capture': 1
        })
    except Exception as exc:
        app.logger.exception("Razorpay order creation failed: %s", exc)
        flash("Could not start payment. Check your Razorpay test keys and try again.", "danger")
        return render_template('user/checkout_review.html', selected_items=selected_items,
            selected_total=total, delivery_address=delivery, payment_setup_needed=True)

    session['razorpay_order_id'] = order['id']
    return render_template('user/payment.html', items=[
        {'name': item['name'], 'price': float(item['price']), 'quantity': int(item['quantity']),
         'total': round(float(item['price']) * int(item['quantity']), 2)}
        for item in selected_items.values()
    ], total=total, delivery=delivery, amount_paise=amount_paise,
       key_id=RAZORPAY_KEY_ID, order_id=order['id'])


@app.route('/payment-success', methods=['POST'])
def payment_success():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    if razorpay_client is None:
        flash("Razorpay is not configured!", "danger")
        return redirect('/user/cart')

    payment_id = request.form.get('razorpay_payment_id')
    order_id = request.form.get('razorpay_order_id')
    signature = request.form.get('razorpay_signature')

    if not payment_id or not order_id or not signature:
        flash("Payment details are missing.", "danger")
        return redirect('/user/cart')

    if order_id != session.get('razorpay_order_id'):
        flash("Invalid payment order.", "danger")
        return redirect('/user/cart')

    try:
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        })
    except Exception:
        app.logger.exception("Payment verification failed")
        flash("Payment verification failed.", "danger")
        return redirect('/user/cart')

    selected_items, total = get_selected_checkout_items()
    delivery = session.get('checkout_address', {})

    if not selected_items or not delivery:
        flash("Checkout details are missing.", "danger")
        return redirect('/user/products')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT order_id FROM orders
            WHERE razorpay_payment_id = %s
        """, (payment_id,))

        existing_order = cursor.fetchone()

        if existing_order:
            database_order_id = existing_order[0]
        else:
            cursor.execute("""
                INSERT INTO orders
                (user_id, razorpay_order_id, razorpay_payment_id,
                 amount, payment_status, name, email, phone,
                 door_no, address, city, pincode)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session['user_id'], order_id, payment_id,
                total, 'paid', delivery.get('full_name', ''),
                delivery.get('email', ''), delivery.get('phone', ''),
                '', delivery.get('address', ''),
                delivery.get('city', ''), delivery.get('pincode', '')
            ))

            database_order_id = cursor.lastrowid

            for pid, item in selected_items.items():
                cursor.execute("""
                    INSERT INTO order_items
                    (order_id, product_id, product_name, quantity, price)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    database_order_id, int(pid), item['name'],
                    int(item['quantity']), float(item['price'])
                ))

        conn.commit()

    except Exception:
        conn.rollback()
        app.logger.exception("Order database saving failed")
        flash("Unable to save order. Please contact support.", "danger")
        return redirect('/user/cart')

    finally:
        cursor.close()
        conn.close()

    session['last_order'] = {
        'database_order_id': database_order_id,
        'payment_id': payment_id,
        'order_id': order_id,
        'name': delivery.get('full_name', ''),
        'email': delivery.get('email', ''),
        'phone': delivery.get('phone', ''),
        'address': delivery.get('address', ''),
        'city': delivery.get('city', ''),
        'state': delivery.get('state', ''),
        'pincode': delivery.get('pincode', ''),
        'items': [
            {
                'name': item['name'],
                'price': float(item['price']),
                'quantity': int(item['quantity']),
                'total': round(float(item['price']) * int(item['quantity']), 2)
            }
            for item in selected_items.values()
        ],
        'total': total
    }

    cart = session.get('cart', {})

    for pid in selected_items:
        cart.pop(pid, None)

    session['cart'] = cart

    for key in ('checkout_selected', 'checkout_address', 'razorpay_order_id'):
        session.pop(key, None)

    return redirect('/order-success')







    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')
    if razorpay_client is None:
        flash("Razorpay is not configured yet.", "danger")
        return redirect('/user/cart')

    payment_id = request.form.get('razorpay_payment_id')
    order_id = request.form.get('razorpay_order_id')
    signature = request.form.get('razorpay_signature')
    if not payment_id or not order_id or not signature or order_id != session.get('razorpay_order_id'):
        flash("Payment details could not be verified.", "danger")
        return redirect('/user/cart')
    try:
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        })
    except Exception:
        app.logger.exception("Razorpay signature verification failed")
        flash("Payment verification failed. Please contact support if money was deducted.", "danger")
        return redirect('/user/cart')

    selected_items, total = get_selected_checkout_items()
    delivery = session.get('checkout_address', {})
    if not selected_items or not delivery:
        flash("Checkout session expired. Please contact support if payment was deducted.", "danger")
        return redirect('/user/products')

    session['last_order'] = {
        'payment_id': payment_id, 'order_id': order_id,
        'name': delivery.get('full_name', ''), 'email': delivery.get('email', ''),
        'phone': delivery.get('phone', ''), 'address': delivery.get('address', ''),
        'city': delivery.get('city', ''), 'state': delivery.get('state', ''),
        'pincode': delivery.get('pincode', ''),
        'items': [{'name': item['name'], 'price': float(item['price']),
                   'quantity': int(item['quantity']),
                   'total': round(float(item['price']) * int(item['quantity']), 2)}
                  for item in selected_items.values()],
        'total': total
    }
    cart = session.get('cart', {})
    for pid in selected_items:
        cart.pop(pid, None)
    session['cart'] = cart
    for key in ('checkout_selected', 'checkout_address', 'razorpay_order_id'):
        session.pop(key, None)
    return redirect('/order-success')


@app.route('/order-success')
def order_success():
    if 'user_id' not in session:
        return redirect('/user-login')
    order = session.get('last_order')
    if not order:
        return redirect('/user/products')
    return render_template('user/order_success.html', order=order)


@app.context_processor
def inject_cart_count():
    cart = session.get('cart', {})
    return {'cart_count': sum(int(item.get('quantity', 0)) for item in cart.values())}


@app.route('/user/download-invoice/<int:order_id>')
def download_invoice(order_id):

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT * FROM orders
            WHERE order_id = %s AND user_id = %s
        """, (order_id, session['user_id']))

        order = cursor.fetchone()

        if not order:
            flash("Order not found!", "danger")
            return redirect('/user/products')

        cursor.execute("""
            SELECT product_name, quantity, price
            FROM order_items
            WHERE order_id = %s
        """, (order_id,))

        order['items'] = cursor.fetchall()

        pdf_file = generate_invoice_pdf(order)

        if pdf_file is None:
            flash("Unable to generate invoice!", "danger")
            return redirect('/user/products')

        return send_file(
            pdf_file,
            as_attachment=True,
            download_name=f"SmartCart_Invoice_{order_id}.pdf",
            mimetype='application/pdf'
        )

    finally:
        cursor.close()
        conn.close()


# ------------------------- RUN APP ------------------------
if __name__ == '__main__':
    app.run(debug=True)

