from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import uuid

auth_bp = Blueprint('auth', __name__)

def get_db():
    from flask import g
    from db import get_db_connection
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db

@auth_bp.route('/login', methods=['GET', 'POST'])
def auth_login():
    if 'user_id' in session:
        return redirect_to_dashboard()
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Please enter both username and password.', 'danger')
            return render_template('auth/login.html')
        
        db = get_db()
        user = db.execute('''
            SELECT * FROM users WHERE (username = ? OR email = ?) AND is_active = 1
        ''', (username, username)).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            session.permanent = True
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['company_id'] = user['company_id']
            
            db.execute('UPDATE users SET last_login = ? WHERE id = ?', 
                      (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), user['id']))
            db.commit()
            
            flash(f'Welcome back, {user["username"]}!', 'success')
            return redirect_to_dashboard()
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
def auth_logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('public.home'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def auth_register():
    if 'user_id' in session:
        return redirect_to_dashboard()
    
    if request.method == 'POST':
        company_name = request.form.get('company_name', '').strip()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not all([company_name, username, email, password]):
            flash('Please fill in all required fields.', 'danger')
            return render_template('auth/register.html')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html')
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('auth/register.html')
        
        db = get_db()
        
        if db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            flash('Username already exists.', 'danger')
            return render_template('auth/register.html')
        
        if db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone():
            flash('Email already registered.', 'danger')
            return render_template('auth/register.html')
        
        slug = company_name.lower().replace(' ', '-').replace('&', 'and')
        slug = ''.join(c for c in slug if c.isalnum() or c == '-')
        
        base_slug = slug
        counter = 1
        while db.execute('SELECT id FROM companies WHERE slug = ?', (slug,)).fetchone():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        company_uid = str(uuid.uuid4())
        expiry_date = (datetime.utcnow() + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        
        db.execute('''
            INSERT INTO companies (uid, name, slug, email, plan, plan_expiry_date, cards_limit)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (company_uid, company_name, slug, email, 'free', expiry_date, 2))
        
        company_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        
        user_uid = str(uuid.uuid4())
        password_hash = generate_password_hash(password)
        
        db.execute('''
            INSERT INTO users (uid, username, email, password_hash, role, company_id, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_uid, username, email, password_hash, 'company_admin', company_id, 1))
        
        db.commit()
        
        flash('Registration successful! You can now login.', 'success')
        return redirect(url_for('auth.auth_login'))
    
    return render_template('auth/register.html')

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def auth_forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        flash('If this email exists in our system, you will receive reset instructions.', 'info')
        return redirect(url_for('auth.auth_login'))
    return render_template('auth/forgot_password.html')

def redirect_to_dashboard():
    role = session.get('role')
    if role == 'master_admin':
        return redirect(url_for('master.dashboard'))
    elif role == 'company_admin':
        return redirect(url_for('company.dashboard'))
    elif role == 'sales_person':
        return redirect(url_for('sales.dashboard'))
    return redirect(url_for('public.home'))
