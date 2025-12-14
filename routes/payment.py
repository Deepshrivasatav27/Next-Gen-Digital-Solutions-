from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from datetime import datetime, timedelta
from config import Config
from paytm_checksum import generate_checksum, verify_checksum
import uuid
import json

payment_bp = Blueprint('payment', __name__)

def get_db():
    from flask import g
    from db import get_db_connection
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db

def payment_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') not in ['company_admin', 'master_admin']:
            flash('Access denied.', 'danger')
            return redirect(url_for('auth.auth_login'))
        return f(*args, **kwargs)
    return decorated

@payment_bp.route('/initiate/<plan>', methods=['POST'])
@payment_required
def initiate_payment(plan):
    db = get_db()
    
    if session.get('role') == 'company_admin':
        company = db.execute('SELECT * FROM companies WHERE id = ?', (session.get('company_id'),)).fetchone()
    else:
        company_id = request.form.get('company_id', type=int)
        company = db.execute('SELECT * FROM companies WHERE id = ?', (company_id,)).fetchone()
    
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('company.plan'))
    
    if plan not in Config.PLANS or plan == 'free':
        flash('Invalid plan selected.', 'danger')
        return redirect(url_for('company.plan'))
    
    plan_config = Config.PLANS[plan]
    amount = plan_config['price']
    
    order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{company['id']}{uuid.uuid4().hex[:6].upper()}"
    payment_uid = str(uuid.uuid4())
    
    db.execute('''
        INSERT INTO payments (uid, company_id, order_id, amount, plan, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (payment_uid, company['id'], order_id, amount, plan, 'pending'))
    db.commit()
    
    if not Config.PAYTM_MERCHANT_ID or not Config.PAYTM_MERCHANT_KEY:
        flash('Payment gateway not configured. Please contact admin.', 'danger')
        return redirect(url_for('company.plan'))
    
    paytm_urls = Config.get_paytm_urls()
    callback_url = request.host_url.rstrip('/') + url_for('payment.callback')
    
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    paytm_params = {
        'MID': Config.PAYTM_MERCHANT_ID,
        'ORDER_ID': order_id,
        'TXN_AMOUNT': str(amount),
        'CUST_ID': str(company['id']),
        'INDUSTRY_TYPE_ID': Config.PAYTM_INDUSTRY_TYPE,
        'WEBSITE': paytm_urls['website'],
        'CHANNEL_ID': Config.PAYTM_CHANNEL_ID,
        'CALLBACK_URL': callback_url,
        'EMAIL': company['email'] or user['email'],
        'MOBILE_NO': company['phone'] or ''
    }
    
    checksum = generate_checksum(paytm_params, Config.PAYTM_MERCHANT_KEY)
    paytm_params['CHECKSUMHASH'] = checksum
    
    return render_template('payment/redirect.html', paytm_params=paytm_params, txn_url=paytm_urls['txn_url'])

@payment_bp.route('/callback', methods=['POST'])
def callback():
    paytm_response = request.form.to_dict()
    
    order_id = paytm_response.get('ORDERID')
    txn_id = paytm_response.get('TXNID')
    status = paytm_response.get('STATUS')
    checksum = paytm_response.get('CHECKSUMHASH')
    
    db = get_db()
    payment = db.execute('SELECT * FROM payments WHERE order_id = ?', (order_id,)).fetchone()
    
    if not payment:
        flash('Payment record not found.', 'danger')
        return redirect(url_for('public.home'))
    
    company = db.execute('SELECT * FROM companies WHERE id = ?', (payment['company_id'],)).fetchone()
    
    paytm_response_copy = paytm_response.copy()
    if 'CHECKSUMHASH' in paytm_response_copy:
        del paytm_response_copy['CHECKSUMHASH']
    
    is_checksum_valid = verify_checksum(paytm_response_copy, Config.PAYTM_MERCHANT_KEY, checksum)
    
    db.execute('''
        UPDATE payments SET transaction_id = ?, paytm_response = ?, checksum_verified = ?,
        payment_mode = ?, bank_name = ?, bank_txn_id = ?
        WHERE order_id = ?
    ''', (
        txn_id, json.dumps(paytm_response), 1 if is_checksum_valid else 0,
        paytm_response.get('PAYMENTMODE'), paytm_response.get('BANKNAME'),
        paytm_response.get('BANKTXNID'), order_id
    ))
    
    if status == 'TXN_SUCCESS' and is_checksum_valid:
        invoice_number = f"INV{datetime.now().strftime('%Y%m%d')}{payment['id']:06d}"
        
        db.execute('''
            UPDATE payments SET status = 'success', completed_at = ?, invoice_number = ?
            WHERE order_id = ?
        ''', (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), invoice_number, order_id))
        
        plan_config = Config.PLANS.get(payment['plan'])
        if plan_config:
            expiry_date = (datetime.utcnow() + timedelta(days=plan_config['days'])).strftime('%Y-%m-%d %H:%M:%S')
            db.execute('''
                UPDATE companies SET plan = ?, plan_expiry_date = ?, cards_limit = ?, white_label_enabled = ?
                WHERE id = ?
            ''', (payment['plan'], expiry_date, plan_config['cards_limit'],
                  1 if plan_config['white_label'] else 0, company['id']))
        
        db.commit()
        
        flash(f'Payment successful! Your plan has been upgraded to {plan_config["name"]}.', 'success')
        return redirect(url_for('payment.success', order_id=order_id))
    
    elif status == 'TXN_FAILURE':
        db.execute("UPDATE payments SET status = 'failed' WHERE order_id = ?", (order_id,))
        db.commit()
        
        flash('Payment failed. Please try again.', 'danger')
        return redirect(url_for('payment.failed', order_id=order_id))
    
    elif status == 'PENDING':
        db.commit()
        flash('Payment is pending. We will update you once confirmed.', 'warning')
        return redirect(url_for('company.plan'))
    
    else:
        if not is_checksum_valid:
            db.execute("UPDATE payments SET status = 'checksum_failed' WHERE order_id = ?", (order_id,))
            flash('Payment verification failed. Please contact support.', 'danger')
        else:
            flash('Payment status unknown. Please contact support.', 'warning')
        
        db.commit()
        return redirect(url_for('company.plan'))

@payment_bp.route('/success/<order_id>')
@payment_required
def success(order_id):
    db = get_db()
    payment = db.execute("SELECT * FROM payments WHERE order_id = ? AND status = 'success'", (order_id,)).fetchone()
    
    if not payment:
        return render_template('errors/404.html'), 404
    
    if session.get('role') == 'company_admin' and payment['company_id'] != session.get('company_id'):
        flash('Access denied.', 'danger')
        return redirect(url_for('public.home'))
    
    company = db.execute('SELECT * FROM companies WHERE id = ?', (payment['company_id'],)).fetchone()
    plan_config = Config.PLANS.get(payment['plan'])
    
    return render_template('payment/success.html', payment=payment, company=company, plan_config=plan_config)

@payment_bp.route('/failed/<order_id>')
@payment_required
def failed(order_id):
    db = get_db()
    payment = db.execute('SELECT * FROM payments WHERE order_id = ?', (order_id,)).fetchone()
    
    if not payment:
        return render_template('errors/404.html'), 404
    
    if session.get('role') == 'company_admin' and payment['company_id'] != session.get('company_id'):
        flash('Access denied.', 'danger')
        return redirect(url_for('public.home'))
    
    return render_template('payment/failed.html', payment=payment)

@payment_bp.route('/invoice/<order_id>')
@payment_required
def invoice(order_id):
    db = get_db()
    payment = db.execute("SELECT * FROM payments WHERE order_id = ? AND status = 'success'", (order_id,)).fetchone()
    
    if not payment:
        return render_template('errors/404.html'), 404
    
    if session.get('role') == 'company_admin' and payment['company_id'] != session.get('company_id'):
        flash('Access denied.', 'danger')
        return redirect(url_for('public.home'))
    
    company = db.execute('SELECT * FROM companies WHERE id = ?', (payment['company_id'],)).fetchone()
    plan_config = Config.PLANS.get(payment['plan'])
    
    return render_template('payment/invoice.html', payment=payment, company=company, plan_config=plan_config)
