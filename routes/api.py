from flask import Blueprint, request, jsonify
from datetime import datetime
from functools import wraps
import uuid

api_bp = Blueprint('api', __name__)

def get_db():
    from flask import g
    from db import get_db_connection
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not api_key:
            return jsonify({'error': 'API key required', 'status': 'error'}), 401
        
        db = get_db()
        key_record = db.execute('SELECT * FROM api_keys WHERE key = ? AND is_active = 1', (api_key,)).fetchone()
        
        if not key_record:
            return jsonify({'error': 'Invalid API key', 'status': 'error'}), 401
        
        company = db.execute('SELECT * FROM companies WHERE id = ? AND is_active = 1', (key_record['company_id'],)).fetchone()
        if not company:
            return jsonify({'error': 'Company not active', 'status': 'error'}), 403
        
        db.execute('UPDATE api_keys SET last_used = ?, usage_count = usage_count + 1 WHERE id = ?',
                  (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), key_record['id']))
        db.commit()
        
        request.api_key = key_record
        request.company = company
        
        return f(*args, **kwargs)
    return decorated

@api_bp.route('/v1/leads', methods=['POST'])
@require_api_key
def create_lead():
    data = request.get_json() or request.form.to_dict()
    
    phone = data.get('phone', '').strip()
    if not phone:
        return jsonify({'error': 'Phone number is required', 'status': 'error'}), 400
    
    source = data.get('source', request.api_key['source_type'] or 'api')
    
    db = get_db()
    lead_uid = str(uuid.uuid4())
    
    db.execute('''
        INSERT INTO leads (uid, name, phone, email, source, company_id, ip_address, remarks)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        lead_uid,
        data.get('name', '').strip(),
        phone,
        data.get('email', '').strip(),
        source,
        request.company['id'],
        request.remote_addr,
        data.get('remarks', '').strip()
    ))
    db.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'Lead created successfully',
        'data': {
            'lead_id': lead_uid,
            'phone': phone,
            'source': source,
            'created_at': datetime.utcnow().isoformat()
        }
    }), 201

@api_bp.route('/v1/leads', methods=['GET'])
@require_api_key
def list_leads():
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)
    source = request.args.get('source', '')
    offset = (page - 1) * per_page
    
    db = get_db()
    query = 'SELECT * FROM leads WHERE company_id = ?'
    params = [request.company['id']]
    
    if source:
        query += ' AND source = ?'
        params.append(source)
    
    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page, offset])
    
    leads = db.execute(query, params).fetchall()
    total = db.execute('SELECT COUNT(*) FROM leads WHERE company_id = ?', (request.company['id'],)).fetchone()[0]
    
    return jsonify({
        'status': 'success',
        'data': {
            'leads': [{
                'id': lead['uid'],
                'name': lead['name'],
                'phone': lead['phone'],
                'email': lead['email'],
                'source': lead['source'],
                'status': lead['status'],
                'created_at': lead['created_at']
            } for lead in leads],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        }
    })

@api_bp.route('/v1/webhook/google-ads', methods=['POST'])
@require_api_key
def google_ads_webhook():
    data = request.get_json() or request.form.to_dict()
    lead_data = data.get('lead_form_submit_data', data)
    
    phone = ''
    name = ''
    email = ''
    
    if isinstance(lead_data, dict):
        user_column_data = lead_data.get('user_column_data', [])
        for item in user_column_data:
            column_id = item.get('column_id', '').lower()
            value = item.get('string_value', '')
            
            if 'phone' in column_id:
                phone = value
            elif 'name' in column_id or 'full_name' in column_id:
                name = value
            elif 'email' in column_id:
                email = value
        
        if not phone:
            phone = lead_data.get('phone', lead_data.get('phone_number', ''))
        if not name:
            name = lead_data.get('name', lead_data.get('full_name', ''))
        if not email:
            email = lead_data.get('email', '')
    
    if not phone:
        return jsonify({'error': 'Phone number not found in webhook data', 'status': 'error'}), 400
    
    db = get_db()
    lead_uid = str(uuid.uuid4())
    
    db.execute('''
        INSERT INTO leads (uid, name, phone, email, source, company_id, ip_address, remarks)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (lead_uid, name, phone, email, 'google_ads', request.company['id'], request.remote_addr,
          f"Google Ads Lead - Campaign: {data.get('campaign_id', 'Unknown')}"))
    db.commit()
    
    return jsonify({'status': 'success', 'lead_id': lead_uid}), 201

@api_bp.route('/v1/webhook/facebook', methods=['POST', 'GET'])
@require_api_key
def facebook_webhook():
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == request.api_key['key'][:10]:
            return request.args.get('hub.challenge', '')
        return 'Verification failed', 403
    
    data = request.get_json() or {}
    entry = data.get('entry', [{}])[0]
    changes = entry.get('changes', [{}])[0]
    value = changes.get('value', {})
    field_data = value.get('field_data', [])
    
    phone = ''
    name = ''
    email = ''
    
    for field in field_data:
        field_name = field.get('name', '').lower()
        values = field.get('values', [''])
        value_str = values[0] if values else ''
        
        if 'phone' in field_name:
            phone = value_str
        elif 'name' in field_name:
            name = value_str
        elif 'email' in field_name:
            email = value_str
    
    if not phone:
        return jsonify({'error': 'Phone number not found', 'status': 'error'}), 400
    
    db = get_db()
    lead_uid = str(uuid.uuid4())
    
    db.execute('''
        INSERT INTO leads (uid, name, phone, email, source, company_id, ip_address, remarks)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (lead_uid, name, phone, email, 'facebook_ads', request.company['id'], request.remote_addr,
          f"Facebook Lead - Form: {value.get('form_id', 'Unknown')}"))
    db.commit()
    
    return jsonify({'status': 'success', 'lead_id': lead_uid}), 201

@api_bp.route('/v1/webhook/generic', methods=['POST'])
@require_api_key
def generic_webhook():
    data = request.get_json() or request.form.to_dict()
    
    phone = (data.get('phone') or data.get('phone_number') or data.get('mobile') or data.get('contact') or '').strip()
    
    if not phone:
        return jsonify({'error': 'Phone number is required', 'status': 'error'}), 400
    
    name = (data.get('name') or data.get('full_name') or data.get('customer_name') or '').strip()
    email = (data.get('email') or data.get('email_address') or '').strip()
    source = data.get('source', request.api_key['source_type'] or 'webhook')
    
    db = get_db()
    lead_uid = str(uuid.uuid4())
    
    db.execute('''
        INSERT INTO leads (uid, name, phone, email, source, company_id, ip_address, remarks)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (lead_uid, name, phone, email, source, request.company['id'], request.remote_addr,
          data.get('remarks', data.get('message', data.get('notes', '')))))
    db.commit()
    
    return jsonify({'status': 'success', 'message': 'Lead created successfully', 'lead_id': lead_uid}), 201

@api_bp.route('/v1/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})
