from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from datetime import datetime

sales_bp = Blueprint('sales', __name__)

def get_db():
    from flask import g
    from db import get_db_connection
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db

def sales_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') not in ['sales_person', 'company_admin', 'master_admin']:
            flash('Access denied.', 'danger')
            return redirect(url_for('auth.auth_login'))
        return f(*args, **kwargs)
    return decorated

@sales_bp.route('/dashboard')
@sales_required
def dashboard():
    if session.get('role') != 'sales_person':
        return redirect(url_for('company.dashboard'))
    
    db = get_db()
    user_id = session['user_id']
    company = db.execute('SELECT * FROM companies WHERE id = ?', (session.get('company_id'),)).fetchone()
    
    total_leads = db.execute('SELECT COUNT(*) FROM leads WHERE assigned_to = ?', (user_id,)).fetchone()[0]
    new_leads = db.execute("SELECT COUNT(*) FROM leads WHERE assigned_to = ? AND status = 'new'", (user_id,)).fetchone()[0]
    
    today = datetime.utcnow().strftime('%Y-%m-%d')
    today_followups = db.execute('''
        SELECT * FROM leads WHERE assigned_to = ? AND date(follow_up_date) = ? 
        ORDER BY follow_up_date
    ''', (user_id, today)).fetchall()
    
    missed_followups = db.execute('''
        SELECT * FROM leads WHERE assigned_to = ? AND date(follow_up_date) < ? 
        AND status NOT IN ('converted', 'closed') ORDER BY follow_up_date DESC
    ''', (user_id, today)).fetchall()
    
    recent_leads = db.execute('SELECT * FROM leads WHERE assigned_to = ? ORDER BY created_at DESC LIMIT 10', (user_id,)).fetchall()
    recent_calls = db.execute('SELECT ch.*, l.name, l.phone FROM call_history ch JOIN leads l ON ch.lead_id = l.id WHERE ch.user_id = ? ORDER BY ch.created_at DESC LIMIT 10', (user_id,)).fetchall()
    
    notifications = db.execute('SELECT * FROM notifications WHERE user_id = ? AND is_read = 0 ORDER BY created_at DESC LIMIT 5', (user_id,)).fetchall()
    
    cards = db.execute('SELECT * FROM visiting_cards WHERE user_id = ?', (user_id,)).fetchall()
    total_card_views = db.execute('SELECT COALESCE(SUM(views_count), 0) FROM visiting_cards WHERE user_id = ?', (user_id,)).fetchone()[0]
    
    return render_template('sales/dashboard.html', company=company,
        total_leads=total_leads, new_leads=new_leads, today_followups=today_followups,
        missed_followups=missed_followups, recent_leads=recent_leads, recent_calls=recent_calls,
        notifications=notifications, cards=cards, total_card_views=total_card_views)

@sales_bp.route('/leads')
@sales_required
def leads():
    if session.get('role') != 'sales_person':
        return redirect(url_for('company.leads'))
    
    db = get_db()
    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    source = request.args.get('source', '')
    per_page = 50
    offset = (page - 1) * per_page
    
    query = 'SELECT * FROM leads WHERE assigned_to = ?'
    params = [user_id]
    
    if status:
        query += ' AND status = ?'
        params.append(status)
    if source:
        query += ' AND source = ?'
        params.append(source)
    
    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page, offset])
    
    leads = db.execute(query, params).fetchall()
    
    return render_template('sales/leads.html', leads=leads, 
                          selected_status=status, selected_source=source, page=page)

@sales_bp.route('/leads/<int:id>')
@sales_required
def view_lead(id):
    db = get_db()
    
    if session.get('role') == 'sales_person':
        lead = db.execute('SELECT * FROM leads WHERE id = ? AND assigned_to = ?', (id, session['user_id'])).fetchone()
    else:
        lead = db.execute('SELECT * FROM leads WHERE id = ?', (id,)).fetchone()
    
    if not lead:
        return render_template('errors/404.html'), 404
    
    call_history = db.execute('SELECT ch.*, u.username FROM call_history ch LEFT JOIN users u ON ch.user_id = u.id WHERE ch.lead_id = ? ORDER BY ch.created_at DESC', (id,)).fetchall()
    
    return render_template('sales/view_lead.html', lead=lead, call_history=call_history)

@sales_bp.route('/leads/<int:id>/update', methods=['POST'])
@sales_required
def update_lead(id):
    db = get_db()
    
    if session.get('role') == 'sales_person':
        lead = db.execute('SELECT * FROM leads WHERE id = ? AND assigned_to = ?', (id, session['user_id'])).fetchone()
    else:
        lead = db.execute('SELECT * FROM leads WHERE id = ?', (id,)).fetchone()
    
    if not lead:
        return render_template('errors/404.html'), 404
    
    follow_up_date = request.form.get('follow_up_date')
    follow_up_time = request.form.get('follow_up_time')
    full_follow_up = None
    
    if follow_up_date:
        if follow_up_time:
            full_follow_up = f'{follow_up_date} {follow_up_time}:00'
        else:
            full_follow_up = f'{follow_up_date} 00:00:00'
    
    db.execute('''
        UPDATE leads SET name = ?, email = ?, status = ?, remarks = ?, 
        follow_up_date = ?, follow_up_time = ?, updated_at = ?
        WHERE id = ?
    ''', (
        request.form.get('name', lead['name']).strip(),
        request.form.get('email', '').strip(),
        request.form.get('status', lead['status']),
        request.form.get('remarks', '').strip(),
        full_follow_up,
        follow_up_time,
        datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        id
    ))
    db.commit()
    
    flash('Lead updated successfully!', 'success')
    return redirect(url_for('sales.view_lead', id=id))

@sales_bp.route('/leads/<int:id>/call', methods=['POST'])
@sales_required
def log_call(id):
    db = get_db()
    
    db.execute('''
        INSERT INTO call_history (lead_id, user_id, call_type, duration, notes)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        id, session['user_id'],
        request.form.get('call_type', 'outgoing'),
        request.form.get('duration', type=int),
        request.form.get('notes', '').strip()
    ))
    
    db.execute('UPDATE leads SET last_contacted = ? WHERE id = ?',
              (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), id))
    db.commit()
    
    flash('Call logged successfully!', 'success')
    return redirect(url_for('sales.view_lead', id=id))

@sales_bp.route('/follow-ups')
@sales_required
def follow_ups():
    if session.get('role') != 'sales_person':
        return redirect(url_for('company.leads'))
    
    db = get_db()
    user_id = session['user_id']
    today = datetime.utcnow().strftime('%Y-%m-%d')
    
    today_followups = db.execute('''
        SELECT * FROM leads WHERE assigned_to = ? AND date(follow_up_date) = ?
        ORDER BY follow_up_date
    ''', (user_id, today)).fetchall()
    
    upcoming_followups = db.execute('''
        SELECT * FROM leads WHERE assigned_to = ? AND date(follow_up_date) > ?
        ORDER BY follow_up_date LIMIT 20
    ''', (user_id, today)).fetchall()
    
    missed_followups = db.execute('''
        SELECT * FROM leads WHERE assigned_to = ? AND date(follow_up_date) < ?
        AND status NOT IN ('converted', 'closed') ORDER BY follow_up_date DESC
    ''', (user_id, today)).fetchall()
    
    return render_template('sales/follow_ups.html',
        today_followups=today_followups, upcoming_followups=upcoming_followups,
        missed_followups=missed_followups)

@sales_bp.route('/call-history')
@sales_required
def call_history():
    if session.get('role') != 'sales_person':
        return redirect(url_for('company.dashboard'))
    
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page
    
    calls = db.execute('''
        SELECT ch.*, l.name, l.phone FROM call_history ch 
        JOIN leads l ON ch.lead_id = l.id 
        WHERE ch.user_id = ? ORDER BY ch.created_at DESC LIMIT ? OFFSET ?
    ''', (session['user_id'], per_page, offset)).fetchall()
    
    return render_template('sales/call_history.html', calls=calls, page=page)

@sales_bp.route('/my-cards')
@sales_required
def my_cards():
    if session.get('role') != 'sales_person':
        return redirect(url_for('company.cards'))
    
    db = get_db()
    cards = db.execute('SELECT * FROM visiting_cards WHERE user_id = ?', (session['user_id'],)).fetchall()
    return render_template('sales/my_cards.html', cards=cards)

@sales_bp.route('/notifications')
@sales_required
def notifications():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page
    
    notifications = db.execute('''
        SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?
    ''', (session['user_id'], per_page, offset)).fetchall()
    
    return render_template('sales/notifications.html', notifications=notifications, page=page)

@sales_bp.route('/notifications/<int:id>/read', methods=['POST'])
@sales_required
def mark_notification_read(id):
    db = get_db()
    notification = db.execute('SELECT * FROM notifications WHERE id = ? AND user_id = ?', (id, session['user_id'])).fetchone()
    
    if notification:
        db.execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (id,))
        db.commit()
        
        if notification['link']:
            return redirect(notification['link'])
    
    return redirect(url_for('sales.notifications'))

@sales_bp.route('/notifications/mark-all-read', methods=['POST'])
@sales_required
def mark_all_read():
    db = get_db()
    db.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0', (session['user_id'],))
    db.commit()
    
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('sales.notifications'))

@sales_bp.route('/profile', methods=['GET', 'POST'])
@sales_required
def profile():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    if request.method == 'POST':
        from werkzeug.security import check_password_hash, generate_password_hash
        
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        
        if new_password:
            if not check_password_hash(user['password_hash'], current_password):
                flash('Current password is incorrect.', 'danger')
                return render_template('sales/profile.html', user=user)
            
            if len(new_password) < 8:
                flash('New password must be at least 8 characters.', 'danger')
                return render_template('sales/profile.html', user=user)
            
            db.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                      (generate_password_hash(new_password), session['user_id']))
            db.commit()
            flash('Password updated successfully!', 'success')
        
        return redirect(url_for('sales.profile'))
    
    return render_template('sales/profile.html', user=user)
