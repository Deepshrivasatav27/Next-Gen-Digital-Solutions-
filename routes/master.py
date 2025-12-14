from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from config import Config
import uuid
import secrets

master_bp = Blueprint('master', __name__)

def get_db():
    from flask import g
    from db import get_db_connection
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db

def master_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'master_admin':
            flash('Access denied. Master Admin privileges required.', 'danger')
            return redirect(url_for('auth.auth_login'))
        return f(*args, **kwargs)
    return decorated

@master_bp.route('/dashboard')
@master_required
def dashboard():
    db = get_db()
    total_companies = db.execute('SELECT COUNT(*) FROM companies').fetchone()[0]
    active_companies = db.execute('SELECT COUNT(*) FROM companies WHERE is_active = 1').fetchone()[0]
    total_users = db.execute("SELECT COUNT(*) FROM users WHERE role != 'master_admin'").fetchone()[0]
    total_leads = db.execute('SELECT COUNT(*) FROM leads').fetchone()[0]
    total_revenue = db.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'success'").fetchone()[0]
    
    recent_companies = db.execute('SELECT * FROM companies ORDER BY created_at DESC LIMIT 5').fetchall()
    recent_payments = db.execute("SELECT p.*, c.name as company_name FROM payments p JOIN companies c ON p.company_id = c.id WHERE p.status = 'success' ORDER BY p.created_at DESC LIMIT 5").fetchall()
    
    plan_stats = {
        'free': db.execute("SELECT COUNT(*) FROM companies WHERE plan = 'free'").fetchone()[0],
        'basic': db.execute("SELECT COUNT(*) FROM companies WHERE plan = 'basic'").fetchone()[0],
        'pro': db.execute("SELECT COUNT(*) FROM companies WHERE plan = 'pro'").fetchone()[0]
    }
    
    api_usage = db.execute('SELECT COALESCE(SUM(usage_count), 0) FROM api_keys').fetchone()[0]
    
    return render_template('master/dashboard.html',
        total_companies=total_companies, active_companies=active_companies,
        total_users=total_users, total_leads=total_leads, total_revenue=total_revenue,
        recent_companies=recent_companies, recent_payments=recent_payments,
        plan_stats=plan_stats, api_usage=api_usage)

@master_bp.route('/companies')
@master_required
def companies():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    per_page = 20
    offset = (page - 1) * per_page
    
    if search:
        companies = db.execute('SELECT * FROM companies WHERE name LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?', 
                              (f'%{search}%', per_page, offset)).fetchall()
        total = db.execute('SELECT COUNT(*) FROM companies WHERE name LIKE ?', (f'%{search}%',)).fetchone()[0]
    else:
        companies = db.execute('SELECT * FROM companies ORDER BY created_at DESC LIMIT ? OFFSET ?', (per_page, offset)).fetchall()
        total = db.execute('SELECT COUNT(*) FROM companies').fetchone()[0]
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('master/companies.html', companies=companies, page=page, 
                          total_pages=total_pages, search=search)

@master_bp.route('/companies/create', methods=['GET', 'POST'])
@master_required
def create_company():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        plan = request.form.get('plan', 'free')
        admin_username = request.form.get('admin_username', '').strip()
        admin_email = request.form.get('admin_email', '').strip()
        admin_password = request.form.get('admin_password', '')
        
        if not all([name, admin_username, admin_email, admin_password]):
            flash('Please fill in all required fields.', 'danger')
            return render_template('master/create_company.html', plans=Config.PLANS)
        
        db = get_db()
        
        slug = name.lower().replace(' ', '-').replace('&', 'and')
        slug = ''.join(c for c in slug if c.isalnum() or c == '-')
        base_slug = slug
        counter = 1
        while db.execute('SELECT id FROM companies WHERE slug = ?', (slug,)).fetchone():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        plan_config = Config.PLANS.get(plan, Config.PLANS['free'])
        expiry_date = (datetime.utcnow() + timedelta(days=plan_config['days'])).strftime('%Y-%m-%d %H:%M:%S')
        
        company_uid = str(uuid.uuid4())
        db.execute('''
            INSERT INTO companies (uid, name, slug, email, phone, address, plan, plan_expiry_date, cards_limit, white_label_enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (company_uid, name, slug, email, phone, address, plan, expiry_date, 
              plan_config['cards_limit'], 1 if plan_config['white_label'] else 0))
        
        company_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        
        user_uid = str(uuid.uuid4())
        password_hash = generate_password_hash(admin_password)
        db.execute('''
            INSERT INTO users (uid, username, email, password_hash, role, company_id, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_uid, admin_username, admin_email, password_hash, 'company_admin', company_id, 1))
        
        db.commit()
        flash(f'Company "{name}" created successfully!', 'success')
        return redirect(url_for('master.companies'))
    
    return render_template('master/create_company.html', plans=Config.PLANS)

@master_bp.route('/companies/<int:id>')
@master_required
def view_company(id):
    db = get_db()
    company = db.execute('SELECT * FROM companies WHERE id = ?', (id,)).fetchone()
    if not company:
        return render_template('errors/404.html'), 404
    
    users = db.execute('SELECT * FROM users WHERE company_id = ?', (id,)).fetchall()
    leads_count = db.execute('SELECT COUNT(*) FROM leads WHERE company_id = ?', (id,)).fetchone()[0]
    cards_count = db.execute('SELECT COUNT(*) FROM visiting_cards WHERE company_id = ?', (id,)).fetchone()[0]
    payments = db.execute('SELECT * FROM payments WHERE company_id = ? ORDER BY created_at DESC LIMIT 10', (id,)).fetchall()
    api_keys = db.execute('SELECT * FROM api_keys WHERE company_id = ?', (id,)).fetchall()
    
    return render_template('master/view_company.html', company=company, users=users,
                          leads_count=leads_count, cards_count=cards_count, payments=payments, api_keys=api_keys)

@master_bp.route('/companies/<int:id>/edit', methods=['GET', 'POST'])
@master_required
def edit_company(id):
    db = get_db()
    company = db.execute('SELECT * FROM companies WHERE id = ?', (id,)).fetchone()
    if not company:
        return render_template('errors/404.html'), 404
    
    if request.method == 'POST':
        db.execute('''
            UPDATE companies SET
                name = ?, email = ?, phone = ?, address = ?, custom_domain = ?,
                homepage_title = ?, homepage_subtitle = ?, about_content = ?,
                features_content = ?, pricing_content = ?, contact_content = ?,
                privacy_policy = ?, terms_conditions = ?,
                theme_mode = ?, primary_color = ?, secondary_color = ?,
                font_family = ?, card_theme = ?, is_active = ?
            WHERE id = ?
        ''', (
            request.form.get('name', company['name']).strip(),
            request.form.get('email', '').strip(),
            request.form.get('phone', '').strip(),
            request.form.get('address', '').strip(),
            request.form.get('custom_domain', '').strip() or None,
            request.form.get('homepage_title', '').strip(),
            request.form.get('homepage_subtitle', '').strip(),
            request.form.get('about_content', '').strip(),
            request.form.get('features_content', '').strip(),
            request.form.get('pricing_content', '').strip(),
            request.form.get('contact_content', '').strip(),
            request.form.get('privacy_policy', '').strip(),
            request.form.get('terms_conditions', '').strip(),
            request.form.get('theme_mode', 'light'),
            request.form.get('primary_color', '#4F46E5'),
            request.form.get('secondary_color', '#10B981'),
            request.form.get('font_family', 'Inter'),
            request.form.get('card_theme', 'modern'),
            1 if request.form.get('is_active') == 'on' else 0,
            id
        ))
        db.commit()
        flash('Company updated successfully!', 'success')
        return redirect(url_for('master.view_company', id=id))
    
    return render_template('master/edit_company.html', company=company)

@master_bp.route('/companies/<int:id>/plan', methods=['POST'])
@master_required
def update_company_plan(id):
    db = get_db()
    plan = request.form.get('plan', 'free')
    plan_config = Config.PLANS.get(plan, Config.PLANS['free'])
    expiry_date = (datetime.utcnow() + timedelta(days=plan_config['days'])).strftime('%Y-%m-%d %H:%M:%S')
    
    db.execute('''
        UPDATE companies SET plan = ?, plan_expiry_date = ?, cards_limit = ?, white_label_enabled = ?
        WHERE id = ?
    ''', (plan, expiry_date, plan_config['cards_limit'], 1 if plan_config['white_label'] else 0, id))
    db.commit()
    
    flash(f'Plan updated to {plan_config["name"]}!', 'success')
    return redirect(url_for('master.view_company', id=id))

@master_bp.route('/companies/<int:id>/toggle', methods=['POST'])
@master_required
def toggle_company(id):
    db = get_db()
    company = db.execute('SELECT is_active FROM companies WHERE id = ?', (id,)).fetchone()
    new_status = 0 if company['is_active'] else 1
    db.execute('UPDATE companies SET is_active = ? WHERE id = ?', (new_status, id))
    db.commit()
    flash(f'Company {"activated" if new_status else "deactivated"} successfully!', 'success')
    return redirect(url_for('master.view_company', id=id))

@master_bp.route('/companies/<int:id>/api-keys', methods=['GET', 'POST'])
@master_required
def manage_api_keys(id):
    db = get_db()
    company = db.execute('SELECT * FROM companies WHERE id = ?', (id,)).fetchone()
    if not company:
        return render_template('errors/404.html'), 404
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        source_type = request.form.get('source_type', '').strip()
        api_key = secrets.token_hex(32)
        
        db.execute('''
            INSERT INTO api_keys (company_id, key, name, source_type)
            VALUES (?, ?, ?, ?)
        ''', (id, api_key, name, source_type))
        db.commit()
        flash(f'API Key created: {api_key}', 'success')
        return redirect(url_for('master.manage_api_keys', id=id))
    
    api_keys = db.execute('SELECT * FROM api_keys WHERE company_id = ?', (id,)).fetchall()
    return render_template('master/api_keys.html', company=company, api_keys=api_keys)

@master_bp.route('/companies/<int:company_id>/api-keys/<int:key_id>/toggle', methods=['POST'])
@master_required
def toggle_api_key(company_id, key_id):
    db = get_db()
    key = db.execute('SELECT is_active FROM api_keys WHERE id = ? AND company_id = ?', (key_id, company_id)).fetchone()
    if key:
        db.execute('UPDATE api_keys SET is_active = ? WHERE id = ?', (0 if key['is_active'] else 1, key_id))
        db.commit()
    flash('API Key status updated!', 'success')
    return redirect(url_for('master.manage_api_keys', id=company_id))

@master_bp.route('/companies/<int:company_id>/api-keys/<int:key_id>/delete', methods=['POST'])
@master_required
def delete_api_key(company_id, key_id):
    db = get_db()
    db.execute('DELETE FROM api_keys WHERE id = ? AND company_id = ?', (key_id, company_id))
    db.commit()
    flash('API Key deleted!', 'success')
    return redirect(url_for('master.manage_api_keys', id=company_id))

@master_bp.route('/leads')
@master_required
def all_leads():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    company_id = request.args.get('company_id', type=int)
    source = request.args.get('source', '')
    per_page = 50
    offset = (page - 1) * per_page
    
    query = 'SELECT l.*, c.name as company_name, u.username as assigned_username FROM leads l LEFT JOIN companies c ON l.company_id = c.id LEFT JOIN users u ON l.assigned_to = u.id WHERE 1=1'
    params = []
    
    if company_id:
        query += ' AND l.company_id = ?'
        params.append(company_id)
    if source:
        query += ' AND l.source = ?'
        params.append(source)
    
    query += ' ORDER BY l.created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page, offset])
    
    leads = db.execute(query, params).fetchall()
    companies = db.execute('SELECT id, name FROM companies').fetchall()
    
    return render_template('master/leads.html', leads=leads, companies=companies,
                          selected_company=company_id, selected_source=source, page=page)

@master_bp.route('/payments')
@master_required
def all_payments():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    per_page = 50
    offset = (page - 1) * per_page
    
    query = 'SELECT p.*, c.name as company_name FROM payments p LEFT JOIN companies c ON p.company_id = c.id WHERE 1=1'
    params = []
    
    if status:
        query += ' AND p.status = ?'
        params.append(status)
    
    query += ' ORDER BY p.created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page, offset])
    
    payments = db.execute(query, params).fetchall()
    return render_template('master/payments.html', payments=payments, selected_status=status, page=page)

@master_bp.route('/settings', methods=['GET', 'POST'])
@master_required
def settings():
    db = get_db()
    settings = db.execute('SELECT * FROM master_settings LIMIT 1').fetchone()
    
    if request.method == 'POST':
        db.execute('''
            UPDATE master_settings SET
                platform_name = ?, platform_tagline = ?, master_name = ?,
                master_footer = ?, master_homepage_url = ?,
                homepage_content = ?, about_content = ?, features_content = ?,
                privacy_policy = ?, terms_conditions = ?,
                showcase_enabled = ?, showcase_title = ?, showcase_description = ?
            WHERE id = ?
        ''', (
            request.form.get('platform_name', '').strip(),
            request.form.get('platform_tagline', '').strip(),
            request.form.get('master_name', '').strip(),
            request.form.get('master_footer', '').strip(),
            request.form.get('master_homepage_url', '').strip(),
            request.form.get('homepage_content', '').strip(),
            request.form.get('about_content', '').strip(),
            request.form.get('features_content', '').strip(),
            request.form.get('privacy_policy', '').strip(),
            request.form.get('terms_conditions', '').strip(),
            1 if request.form.get('showcase_enabled') == 'on' else 0,
            request.form.get('showcase_title', '').strip(),
            request.form.get('showcase_description', '').strip(),
            settings['id']
        ))
        db.commit()
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('master.settings'))
    
    return render_template('master/settings.html', settings=settings)

@master_bp.route('/showcase')
@master_required
def showcase_projects():
    db = get_db()
    projects = db.execute('SELECT * FROM master_showcase_projects ORDER BY display_order').fetchall()
    return render_template('master/showcase.html', projects=projects)

@master_bp.route('/showcase/add', methods=['GET', 'POST'])
@master_required
def add_showcase():
    db = get_db()
    
    if request.method == 'POST':
        db.execute('''
            INSERT INTO master_showcase_projects (company_id, title, description, image_url, demo_url, is_featured)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            request.form.get('company_id', type=int) or None,
            request.form.get('title', '').strip(),
            request.form.get('description', '').strip(),
            request.form.get('image_url', '').strip(),
            request.form.get('demo_url', '').strip(),
            1 if request.form.get('is_featured') == 'on' else 0
        ))
        db.commit()
        flash('Project added to showcase!', 'success')
        return redirect(url_for('master.showcase_projects'))
    
    companies = db.execute('SELECT id, name FROM companies WHERE is_active = 1').fetchall()
    return render_template('master/add_showcase.html', companies=companies)

@master_bp.route('/profile', methods=['GET', 'POST'])
@master_required
def profile():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_email = request.form.get('email', '').strip()
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        
        if new_username and new_username != user['username']:
            if db.execute('SELECT id FROM users WHERE username = ? AND id != ?', (new_username, user['id'])).fetchone():
                flash('Username already taken.', 'danger')
                return render_template('master/profile.html', user=user)
            db.execute('UPDATE users SET username = ? WHERE id = ?', (new_username, user['id']))
        
        if new_email and new_email != user['email']:
            if db.execute('SELECT id FROM users WHERE email = ? AND id != ?', (new_email, user['id'])).fetchone():
                flash('Email already registered.', 'danger')
                return render_template('master/profile.html', user=user)
            db.execute('UPDATE users SET email = ? WHERE id = ?', (new_email, user['id']))
        
        if new_password:
            if not check_password_hash(user['password_hash'], current_password):
                flash('Current password is incorrect.', 'danger')
                return render_template('master/profile.html', user=user)
            db.execute('UPDATE users SET password_hash = ? WHERE id = ?', 
                      (generate_password_hash(new_password), user['id']))
        
        db.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('master.profile'))
    
    return render_template('master/profile.html', user=user)

@master_bp.route('/analytics')
@master_required
def analytics():
    db = get_db()
    
    leads_by_month = db.execute('''
        SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
        FROM leads GROUP BY month ORDER BY month DESC LIMIT 12
    ''').fetchall()
    
    revenue_by_month = db.execute('''
        SELECT strftime('%Y-%m', completed_at) as month, SUM(amount) as total
        FROM payments WHERE status = 'success' GROUP BY month ORDER BY month DESC LIMIT 12
    ''').fetchall()
    
    leads_by_source = db.execute('''
        SELECT source, COUNT(*) as count FROM leads GROUP BY source
    ''').fetchall()
    
    return render_template('master/analytics.html',
        leads_by_month=leads_by_month, revenue_by_month=revenue_by_month, leads_by_source=leads_by_source)
