from flask import Blueprint, render_template, request
import uuid

public_bp = Blueprint('public', __name__)

def get_db():
    from flask import g
    from db import get_db_connection
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db

@public_bp.route('/')
def home():
    db = get_db()
    settings = db.execute('SELECT * FROM master_settings LIMIT 1').fetchone()
    return render_template('public/home.html', settings=settings)

@public_bp.route('/about')
def about():
    db = get_db()
    settings = db.execute('SELECT * FROM master_settings LIMIT 1').fetchone()
    return render_template('public/about.html', settings=settings)

@public_bp.route('/features')
def features():
    db = get_db()
    settings = db.execute('SELECT * FROM master_settings LIMIT 1').fetchone()
    return render_template('public/features.html', settings=settings)

@public_bp.route('/privacy-policy')
def privacy():
    db = get_db()
    settings = db.execute('SELECT * FROM master_settings LIMIT 1').fetchone()
    return render_template('public/privacy.html', settings=settings)

@public_bp.route('/terms-conditions')
def terms():
    db = get_db()
    settings = db.execute('SELECT * FROM master_settings LIMIT 1').fetchone()
    return render_template('public/terms.html', settings=settings)

@public_bp.route('/showcase')
def showcase():
    db = get_db()
    settings = db.execute('SELECT * FROM master_settings LIMIT 1').fetchone()
    projects = db.execute('SELECT * FROM master_showcase_projects ORDER BY display_order').fetchall()
    companies = db.execute('SELECT * FROM companies WHERE is_active = 1').fetchall()
    return render_template('public/showcase.html', settings=settings, projects=projects, companies=companies)

@public_bp.route('/company/<slug>')
def company_home(slug):
    db = get_db()
    company = db.execute('SELECT * FROM companies WHERE slug = ? AND is_active = 1', (slug,)).fetchone()
    if not company:
        return render_template('errors/404.html'), 404
    return render_template('public/company/home.html', company=company)

@public_bp.route('/company/<slug>/about')
def company_about(slug):
    db = get_db()
    company = db.execute('SELECT * FROM companies WHERE slug = ? AND is_active = 1', (slug,)).fetchone()
    if not company:
        return render_template('errors/404.html'), 404
    return render_template('public/company/about.html', company=company)

@public_bp.route('/company/<slug>/features')
def company_features(slug):
    db = get_db()
    company = db.execute('SELECT * FROM companies WHERE slug = ? AND is_active = 1', (slug,)).fetchone()
    if not company:
        return render_template('errors/404.html'), 404
    return render_template('public/company/features.html', company=company)

@public_bp.route('/company/<slug>/pricing')
def company_pricing(slug):
    db = get_db()
    company = db.execute('SELECT * FROM companies WHERE slug = ? AND is_active = 1', (slug,)).fetchone()
    if not company:
        return render_template('errors/404.html'), 404
    return render_template('public/company/pricing.html', company=company)

@public_bp.route('/company/<slug>/contact', methods=['GET', 'POST'])
def company_contact(slug):
    db = get_db()
    company = db.execute('SELECT * FROM companies WHERE slug = ? AND is_active = 1', (slug,)).fetchone()
    if not company:
        return render_template('errors/404.html'), 404
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        message = request.form.get('message', '').strip()
        
        if phone:
            lead_uid = str(uuid.uuid4())
            db.execute('''
                INSERT INTO leads (uid, name, phone, email, source, company_id, ip_address, remarks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (lead_uid, name, phone, email, 'contact_form', company['id'], request.remote_addr, message))
            db.commit()
            
            return render_template('public/company/contact.html', company=company, success=True)
    
    return render_template('public/company/contact.html', company=company)

@public_bp.route('/company/<slug>/privacy')
def company_privacy(slug):
    db = get_db()
    company = db.execute('SELECT * FROM companies WHERE slug = ? AND is_active = 1', (slug,)).fetchone()
    if not company:
        return render_template('errors/404.html'), 404
    return render_template('public/company/privacy.html', company=company)

@public_bp.route('/company/<slug>/terms')
def company_terms(slug):
    db = get_db()
    company = db.execute('SELECT * FROM companies WHERE slug = ? AND is_active = 1', (slug,)).fetchone()
    if not company:
        return render_template('errors/404.html'), 404
    return render_template('public/company/terms.html', company=company)
