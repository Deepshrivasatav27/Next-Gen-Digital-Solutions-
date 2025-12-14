from flask import Blueprint, render_template, redirect, url_for, request, send_file, current_app
from datetime import datetime
import qrcode
import io
import os
import uuid

card_bp = Blueprint('card', __name__)

def get_db():
    from flask import g
    from db import get_db_connection
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db

@card_bp.route('/<uid>')
def view_card(uid):
    db = get_db()
    card = db.execute('SELECT * FROM visiting_cards WHERE uid = ? AND is_active = 1', (uid,)).fetchone()
    if not card:
        return render_template('errors/404.html'), 404
    
    db.execute('UPDATE visiting_cards SET views_count = views_count + 1 WHERE uid = ?', (uid,))
    db.commit()
    
    company = db.execute('SELECT * FROM companies WHERE id = ?', (card['company_id'],)).fetchone()
    
    return render_template('card/view.html', card=card, company=company)

@card_bp.route('/<uid>/action', methods=['POST'])
def card_action(uid):
    db = get_db()
    card = db.execute('SELECT * FROM visiting_cards WHERE uid = ? AND is_active = 1', (uid,)).fetchone()
    if not card:
        return render_template('errors/404.html'), 404
    
    action = request.form.get('action')
    visitor_name = request.form.get('name', '').strip()
    visitor_phone = request.form.get('phone', '').strip()
    
    company = db.execute('SELECT * FROM companies WHERE id = ?', (card['company_id'],)).fetchone()
    
    if not visitor_phone:
        return render_template('card/view.html', card=card, company=company, 
                              show_phone_modal=True, action=action)
    
    lead_uid = str(uuid.uuid4())
    db.execute('''
        INSERT INTO leads (uid, name, phone, source, company_id, card_id, ip_address)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (lead_uid, visitor_name, visitor_phone, f'card_{action}', card['company_id'], card['id'], request.remote_addr))
    db.commit()
    
    if action == 'call':
        return render_template('card/action_result.html', card=card, action='call', phone=card['phone'])
    elif action == 'whatsapp':
        whatsapp_number = card['whatsapp'] or card['phone']
        whatsapp_number = ''.join(filter(str.isdigit, whatsapp_number))
        if not whatsapp_number.startswith('91'):
            whatsapp_number = '91' + whatsapp_number
        return redirect(f'https://wa.me/{whatsapp_number}')
    elif action == 'email':
        return render_template('card/action_result.html', card=card, action='email', email=card['email'])
    
    return redirect(url_for('card.view_card', uid=uid))

@card_bp.route('/<uid>/qr')
def get_qr_code(uid):
    db = get_db()
    card = db.execute('SELECT * FROM visiting_cards WHERE uid = ?', (uid,)).fetchone()
    if not card:
        return render_template('errors/404.html'), 404
    
    card_url = f"{request.host_url}card/{card['uid']}"
    
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(card_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

@card_bp.route('/<uid>/vcard')
def download_vcard(uid):
    db = get_db()
    card = db.execute('SELECT * FROM visiting_cards WHERE uid = ? AND is_active = 1', (uid,)).fetchone()
    if not card:
        return render_template('errors/404.html'), 404
    
    company = db.execute('SELECT * FROM companies WHERE id = ?', (card['company_id'],)).fetchone()
    
    vcard = f"""BEGIN:VCARD
VERSION:3.0
FN:{card['name']}
ORG:{company['name']}
TITLE:{card['designation'] or ''}
TEL;TYPE=CELL:{card['phone']}
EMAIL:{card['email'] or ''}
ADR:{card['address'] or ''}
NOTE:{card['bio'] or ''}
END:VCARD"""
    
    return send_file(
        io.BytesIO(vcard.encode()),
        mimetype='text/vcard',
        as_attachment=True,
        download_name=f'{card["name"].replace(" ", "_")}.vcf'
    )
