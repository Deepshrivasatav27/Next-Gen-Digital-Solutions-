import os
from flask import Flask, render_template, g, session, redirect, url_for
from datetime import datetime, timedelta
from functools import wraps
from config import Config
from db import get_db_connection, init_database

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

def get_db():
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def get_current_user():
    if 'user_id' not in session:
        return None
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ? AND is_active = 1', (session['user_id'],)).fetchone()
    return user

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.auth_login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return redirect(url_for('auth_login'))
            if user['role'] not in roles:
                return render_template('errors/403.html'), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_master_settings():
    db = get_db()
    settings = db.execute('SELECT * FROM master_settings LIMIT 1').fetchone()
    return settings

def check_plan_expiry():
    db = get_db()
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    db.execute('''
        UPDATE companies 
        SET plan = 'free', cards_limit = 2, white_label_enabled = 0
        WHERE plan != 'free' AND plan_expiry_date < ? AND plan_expiry_date IS NOT NULL
    ''', (now,))
    db.commit()

@app.context_processor
def inject_globals():
    return {
        'current_user': get_current_user(),
        'master_settings': get_master_settings(),
        'current_year': datetime.utcnow().year,
        'plans': Config.PLANS
    }

@app.before_request
def before_request():
    check_plan_expiry()

@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('errors/500.html'), 500

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

from routes.auth import auth_bp
from routes.public import public_bp
from routes.master import master_bp
from routes.company import company_bp
from routes.sales import sales_bp
from routes.card import card_bp
from routes.api import api_bp
from routes.payment import payment_bp

app.register_blueprint(auth_bp)
app.register_blueprint(public_bp)
app.register_blueprint(master_bp, url_prefix='/master')
app.register_blueprint(company_bp, url_prefix='/admin')
app.register_blueprint(sales_bp, url_prefix='/sales')
app.register_blueprint(card_bp, url_prefix='/card')
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(payment_bp, url_prefix='/payment')

if __name__ == '__main__':
    init_database()
    app.run(host='0.0.0.0', port=5000, debug=True)
