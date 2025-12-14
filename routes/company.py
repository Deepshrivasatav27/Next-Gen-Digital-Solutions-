from flask import Blueprint, render_template, redirect, url_for, flash, request, session, send_file
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
from config import Config
import uuid
import csv
import io

company_bp = Blueprint('company', __name__)

def get_db():
    from flask import g
    from db import get_db_connection
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db

def company_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') not in ['company_admin', 'master_admin']:
            flash('Access denied.', 'danger')
            return redirect(url_for('auth.auth_login'))
        return f(*args, **kwargs)
    return decorated

def get_company():
    db = get_db()
    if session.get('role') == 'master_admin':
        company_id = request.args.get('company_id', type=int)
        if company_id:
            return db.execute('SELECT * FROM companies WHERE id = ?', (company_id,)).fetchone()
        return None
    return db.execute('SELECT * FROM companies WHERE id = ?', (session.get('company_id'),)).fetchone()

@company_bp.route('/dashboard')
@company_required
def dashboard():
    company = get_company()
    if not company:
        flash('No company selected.', 'warning')
        return redirect(url_for('master.companies'))
    
    db = get_db()
    total_cards = db.execute('SELECT COUNT(*) FROM visiting_cards WHERE company_id = ?', (company['id'],)).fetchone()[0]
    total_leads = db.execute('SELECT COUNT(*) FROM leads WHERE company_id = ?', (company['id'],)).fetchone()[0]
    total_views = db.execute('SELECT COALESCE(SUM(views_count), 0) FROM visiting_cards WHERE company_id = ?', (company['id'],)).fetchone()[0]
    total_sales = db.execute("SELECT COUNT(*) FROM users WHERE company_id = ? AND role = 'sales_person'", (company['id'],)).fetchone()[0]
    
    recent_leads = db.execute('SELECT * FROM leads WHERE company_id = ? ORDER BY created_at DESC LIMIT 10', (company['id'],)).fetchall()
    unassigned_leads = db.execute('SELECT COUNT(*) FROM leads WHERE company_id = ? AND assigned_to IS NULL', (company['id'],)).fetchone()[0]
    
    today = datetime.utcnow().strftime('%Y-%m-%d')
    today_leads = db.execute("SELECT COUNT(*) FROM leads WHERE company_id = ? AND date(created_at) = ?", (company['id'], today)).fetchone()[0]
    
    plan_info = Config.PLANS.get(company['plan'], Config.PLANS['free'])
    days_remaining = 0
    if company['plan_expiry_date']:
        expiry = datetime.strptime(company['plan_expiry_date'], '%Y-%m-%d %H:%M:%S')
        days_remaining = max(0, (expiry - datetime.utcnow()).days)
    
    return render_template('company/dashboard.html', company=company,
        total_cards=total_cards, total_leads=total_leads, total_views=total_views,
        total_sales=total_sales, recent_leads=recent_leads, unassigned_leads=unassigned_leads,
        today_leads=today_leads, plan_info=plan_info, days_remaining=days_remaining)

@company_bp.route('/sales-persons')
@company_required
def sales_persons():
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    db = get_db()
    sales_persons = db.execute("SELECT * FROM users WHERE company_id = ? AND role = 'sales_person'", (company['id'],)).fetchall()
    return render_template('company/sales_persons.html', company=company, sales_persons=sales_persons)

@company_bp.route('/sales-persons/add', methods=['GET', 'POST'])
@company_required
def add_sales_person():
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not all([username, email, password]):
            flash('Please fill in all required fields.', 'danger')
            return render_template('company/add_sales_person.html', company=company)
        
        db = get_db()
        if db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            flash('Username already exists.', 'danger')
            return render_template('company/add_sales_person.html', company=company)
        
        if db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone():
            flash('Email already registered.', 'danger')
            return render_template('company/add_sales_person.html', company=company)
        
        user_uid = str(uuid.uuid4())
        password_hash = generate_password_hash(password)
        db.execute('''
            INSERT INTO users (uid, username, email, password_hash, role, company_id, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_uid, username, email, password_hash, 'sales_person', company['id'], 1))
        db.commit()
        
        flash(f'Sales person "{username}" added successfully!', 'success')
        return redirect(url_for('company.sales_persons'))
    
    return render_template('company/add_sales_person.html', company=company)

@company_bp.route('/sales-persons/<int:id>/edit', methods=['GET', 'POST'])
@company_required
def edit_sales_person(id):
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ? AND company_id = ? AND role = 'sales_person'", (id, company['id'])).fetchone()
    if not user:
        return render_template('errors/404.html'), 404
    
    if request.method == 'POST':
        new_email = request.form.get('email', user['email']).strip()
        new_password = request.form.get('password', '').strip()
        is_active = 1 if request.form.get('is_active') == 'on' else 0
        
        if new_password:
            db.execute('UPDATE users SET email = ?, password_hash = ?, is_active = ? WHERE id = ?',
                      (new_email, generate_password_hash(new_password), is_active, id))
        else:
            db.execute('UPDATE users SET email = ?, is_active = ? WHERE id = ?', (new_email, is_active, id))
        db.commit()
        
        flash('Sales person updated successfully!', 'success')
        return redirect(url_for('company.sales_persons'))
    
    return render_template('company/edit_sales_person.html', company=company, user=user)

@company_bp.route('/sales-persons/<int:id>/toggle', methods=['POST'])
@company_required
def toggle_sales_person(id):
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    db = get_db()
    user = db.execute("SELECT is_active FROM users WHERE id = ? AND company_id = ? AND role = 'sales_person'", (id, company['id'])).fetchone()
    if user:
        db.execute('UPDATE users SET is_active = ? WHERE id = ?', (0 if user['is_active'] else 1, id))
        db.commit()
    
    flash('Sales person status updated.', 'success')
    return redirect(url_for('company.sales_persons'))

@company_bp.route('/leads')
@company_required
def leads():
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    db = get_db()
    page = request.args.get('page', 1, type=int)
    source = request.args.get('source', '')
    status = request.args.get('status', '')
    assigned_to = request.args.get('assigned_to', type=int)
    per_page = 50
    offset = (page - 1) * per_page
    
    query = '''SELECT l.*, u.username as assigned_username FROM leads l 
               LEFT JOIN users u ON l.assigned_to = u.id WHERE l.company_id = ?'''
    params = [company['id']]
    
    if source:
        query += ' AND l.source = ?'
        params.append(source)
    if status:
        query += ' AND l.status = ?'
        params.append(status)
    if assigned_to:
        query += ' AND l.assigned_to = ?'
        params.append(assigned_to)
    
    query += ' ORDER BY l.created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page, offset])
    
    leads = db.execute(query, params).fetchall()
    sales_persons = db.execute("SELECT id, username FROM users WHERE company_id = ? AND role = 'sales_person'", (company['id'],)).fetchall()
    
    return render_template('company/leads.html', company=company, leads=leads, sales_persons=sales_persons,
                          selected_source=source, selected_status=status, selected_assigned_to=assigned_to, page=page)

@company_bp.route('/leads/<int:id>')
@company_required
def view_lead(id):
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    db = get_db()
    lead = db.execute('SELECT * FROM leads WHERE id = ? AND company_id = ?', (id, company['id'])).fetchone()
    if not lead:
        return render_template('errors/404.html'), 404
    
    sales_persons = db.execute("SELECT id, username FROM users WHERE company_id = ? AND role = 'sales_person'", (company['id'],)).fetchall()
    call_history = db.execute('SELECT ch.*, u.username FROM call_history ch LEFT JOIN users u ON ch.user_id = u.id WHERE ch.lead_id = ? ORDER BY ch.created_at DESC', (id,)).fetchall()
    
    return render_template('company/view_lead.html', company=company, lead=lead, 
                          sales_persons=sales_persons, call_history=call_history)

@company_bp.route('/leads/<int:id>/assign', methods=['POST'])
@company_required
def assign_lead(id):
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    db = get_db()
    sales_person_id = request.form.get('sales_person_id', type=int)
    
    if sales_person_id:
        db.execute('UPDATE leads SET assigned_to = ?, updated_at = ? WHERE id = ? AND company_id = ?',
                  (sales_person_id, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), id, company['id']))
        
        lead = db.execute('SELECT name, phone FROM leads WHERE id = ?', (id,)).fetchone()
        db.execute('''
            INSERT INTO notifications (user_id, title, message, type, link)
            VALUES (?, ?, ?, ?, ?)
        ''', (sales_person_id, 'New Lead Assigned', 
              f'A new lead ({lead["name"] or lead["phone"]}) has been assigned to you.',
              'lead_assigned', f'/sales/leads/{id}'))
        
        db.commit()
        flash('Lead assigned successfully!', 'success')
    
    return redirect(url_for('company.view_lead', id=id))

@company_bp.route('/leads/export')
@company_required
def export_leads():
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    db = get_db()
    format_type = request.args.get('format', 'csv')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    sales_person_id = request.args.get('sales_person_id', type=int)
    
    query = '''SELECT l.*, u.username as assigned_username FROM leads l 
               LEFT JOIN users u ON l.assigned_to = u.id WHERE l.company_id = ?'''
    params = [company['id']]
    
    if date_from:
        query += ' AND date(l.created_at) >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND date(l.created_at) <= ?'
        params.append(date_to)
    if sales_person_id:
        query += ' AND l.assigned_to = ?'
        params.append(sales_person_id)
    
    leads = db.execute(query, params).fetchall()
    
    data = []
    for lead in leads:
        data.append({
            'Name': lead['name'] or '',
            'Phone': lead['phone'],
            'Email': lead['email'] or '',
            'Source': lead['source'],
            'Status': lead['status'],
            'Assigned To': lead['assigned_username'] or 'Unassigned',
            'Remarks': lead['remarks'] or '',
            'Follow-up Date': lead['follow_up_date'] or '',
            'Created': lead['created_at']
        })
    
    if format_type == 'excel':
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = 'Leads'
        headers = ['Name', 'Phone', 'Email', 'Source', 'Status', 'Assigned To', 'Remarks', 'Follow-up Date', 'Created']
        ws.append(headers)
        for row in data:
            ws.append([row[h] for h in headers])
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        as_attachment=True, download_name=f'leads_{company["slug"]}_{datetime.now().strftime("%Y%m%d")}.xlsx')
    else:
        output = io.StringIO()
        headers = ['Name', 'Phone', 'Email', 'Source', 'Status', 'Assigned To', 'Remarks', 'Follow-up Date', 'Created']
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)
        output.seek(0)
        return send_file(io.BytesIO(output.getvalue().encode()), mimetype='text/csv',
                        as_attachment=True, download_name=f'leads_{company["slug"]}_{datetime.now().strftime("%Y%m%d")}.csv')

@company_bp.route('/cards')
@company_required
def cards():
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    db = get_db()
    cards = db.execute('''SELECT vc.*, u.username FROM visiting_cards vc 
                         LEFT JOIN users u ON vc.user_id = u.id WHERE vc.company_id = ? 
                         ORDER BY vc.created_at DESC''', (company['id'],)).fetchall()
    
    used_cards = len(cards)
    cards_limit = company['cards_limit']
    cards_remaining = float('inf') if cards_limit == -1 else max(0, cards_limit - used_cards)
    
    return render_template('company/cards.html', company=company, cards=cards, cards_remaining=cards_remaining)

@company_bp.route('/cards/create', methods=['GET', 'POST'])
@company_required
def create_card():
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    db = get_db()
    used_cards = db.execute('SELECT COUNT(*) FROM visiting_cards WHERE company_id = ?', (company['id'],)).fetchone()[0]
    
    if company['cards_limit'] != -1 and used_cards >= company['cards_limit']:
        flash('You have reached your card limit. Please upgrade your plan.', 'warning')
        return redirect(url_for('company.cards'))
    
    sales_persons = db.execute("SELECT id, username FROM users WHERE company_id = ? AND role = 'sales_person'", (company['id'],)).fetchall()
    
    if request.method == 'POST':
        user_id = request.form.get('user_id', type=int)
        if not user_id:
            flash('Please select a sales person.', 'danger')
            return render_template('company/create_card.html', company=company, sales_persons=sales_persons)
        
        card_uid = str(uuid.uuid4())
        db.execute('''
            INSERT INTO visiting_cards (uid, user_id, company_id, name, designation, phone, whatsapp, email, address, bio, theme, background_color, text_color)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            card_uid, user_id, company['id'],
            request.form.get('name', '').strip(),
            request.form.get('designation', '').strip(),
            request.form.get('phone', '').strip(),
            request.form.get('whatsapp', '').strip(),
            request.form.get('email', '').strip(),
            request.form.get('address', '').strip(),
            request.form.get('bio', '').strip(),
            request.form.get('theme', 'modern'),
            request.form.get('background_color', '#ffffff'),
            request.form.get('text_color', '#000000')
        ))
        db.commit()
        
        flash('Visiting card created successfully!', 'success')
        return redirect(url_for('company.cards'))
    
    return render_template('company/create_card.html', company=company, sales_persons=sales_persons)

@company_bp.route('/cards/<int:id>/edit', methods=['GET', 'POST'])
@company_required
def edit_card(id):
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    db = get_db()
    card = db.execute('SELECT * FROM visiting_cards WHERE id = ? AND company_id = ?', (id, company['id'])).fetchone()
    if not card:
        return render_template('errors/404.html'), 404
    
    if request.method == 'POST':
        db.execute('''
            UPDATE visiting_cards SET name = ?, designation = ?, phone = ?, whatsapp = ?,
            email = ?, address = ?, bio = ?, theme = ?, background_color = ?, text_color = ?, is_active = ?
            WHERE id = ?
        ''', (
            request.form.get('name', card['name']).strip(),
            request.form.get('designation', '').strip(),
            request.form.get('phone', card['phone']).strip(),
            request.form.get('whatsapp', '').strip(),
            request.form.get('email', '').strip(),
            request.form.get('address', '').strip(),
            request.form.get('bio', '').strip(),
            request.form.get('theme', 'modern'),
            request.form.get('background_color', '#ffffff'),
            request.form.get('text_color', '#000000'),
            1 if request.form.get('is_active') == 'on' else 0,
            id
        ))
        db.commit()
        
        flash('Card updated successfully!', 'success')
        return redirect(url_for('company.cards'))
    
    return render_template('company/edit_card.html', company=company, card=card)

@company_bp.route('/website', methods=['GET', 'POST'])
@company_required
def website_settings():
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    db = get_db()
    
    if request.method == 'POST':
        db.execute('''
            UPDATE companies SET homepage_title = ?, homepage_subtitle = ?, about_content = ?,
            features_content = ?, pricing_content = ?, contact_content = ?, privacy_policy = ?, terms_conditions = ?
            WHERE id = ?
        ''', (
            request.form.get('homepage_title', '').strip(),
            request.form.get('homepage_subtitle', '').strip(),
            request.form.get('about_content', '').strip(),
            request.form.get('features_content', '').strip(),
            request.form.get('pricing_content', '').strip(),
            request.form.get('contact_content', '').strip(),
            request.form.get('privacy_policy', '').strip(),
            request.form.get('terms_conditions', '').strip(),
            company['id']
        ))
        db.commit()
        flash('Website content updated!', 'success')
        return redirect(url_for('company.website_settings'))
    
    company = db.execute('SELECT * FROM companies WHERE id = ?', (company['id'],)).fetchone()
    return render_template('company/website_settings.html', company=company)

@company_bp.route('/branding', methods=['GET', 'POST'])
@company_required
def branding():
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    db = get_db()
    
    if request.method == 'POST':
        updates = '''
            UPDATE companies SET theme_mode = ?, primary_color = ?, secondary_color = ?,
            font_family = ?, card_theme = ?'''
        params = [
            request.form.get('theme_mode', 'light'),
            request.form.get('primary_color', '#4F46E5'),
            request.form.get('secondary_color', '#10B981'),
            request.form.get('font_family', 'Inter'),
            request.form.get('card_theme', 'modern')
        ]
        
        if company['white_label_enabled']:
            updates += ', custom_logo = ?, custom_footer = ?'
            params.extend([
                request.form.get('custom_logo', '').strip(),
                request.form.get('custom_footer', '').strip()
            ])
        
        updates += ' WHERE id = ?'
        params.append(company['id'])
        
        db.execute(updates, params)
        db.commit()
        flash('Branding settings updated!', 'success')
        return redirect(url_for('company.branding'))
    
    company = db.execute('SELECT * FROM companies WHERE id = ?', (company['id'],)).fetchone()
    return render_template('company/branding.html', company=company)

@company_bp.route('/plan')
@company_required
def plan():
    company = get_company()
    if not company:
        return redirect(url_for('master.companies'))
    
    db = get_db()
    current_plan = Config.PLANS.get(company['plan'], Config.PLANS['free'])
    
    days_remaining = 0
    if company['plan_expiry_date']:
        expiry = datetime.strptime(company['plan_expiry_date'], '%Y-%m-%d %H:%M:%S')
        days_remaining = max(0, (expiry - datetime.utcnow()).days)
    
    payments = db.execute('SELECT * FROM payments WHERE company_id = ? ORDER BY created_at DESC LIMIT 10', (company['id'],)).fetchall()
    
    return render_template('company/plan.html', company=company, plans=Config.PLANS,
                          current_plan=current_plan, days_remaining=days_remaining, payments=payments)
