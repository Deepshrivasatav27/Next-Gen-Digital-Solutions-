import sqlite3
import os
from contextlib import contextmanager

DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'saas_platform.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def get_db():
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_database():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('master_admin', 'company_admin', 'sales_person')),
            company_id INTEGER,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            email TEXT,
            phone TEXT,
            address TEXT,
            logo_url TEXT,
            custom_domain TEXT UNIQUE,
            
            plan TEXT DEFAULT 'free' CHECK(plan IN ('free', 'basic', 'pro')),
            plan_expiry_date TIMESTAMP,
            cards_limit INTEGER DEFAULT 2,
            white_label_enabled INTEGER DEFAULT 0,
            
            theme_mode TEXT DEFAULT 'light',
            primary_color TEXT DEFAULT '#4F46E5',
            secondary_color TEXT DEFAULT '#10B981',
            font_family TEXT DEFAULT 'Inter',
            card_theme TEXT DEFAULT 'modern',
            
            homepage_title TEXT,
            homepage_subtitle TEXT,
            about_content TEXT,
            features_content TEXT,
            pricing_content TEXT,
            contact_content TEXT,
            privacy_policy TEXT,
            terms_conditions TEXT,
            
            custom_logo TEXT,
            custom_footer TEXT,
            
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE NOT NULL,
            name TEXT,
            phone TEXT NOT NULL,
            email TEXT,
            source TEXT NOT NULL,
            ip_address TEXT,
            
            company_id INTEGER NOT NULL,
            assigned_to INTEGER,
            card_id INTEGER,
            
            status TEXT DEFAULT 'new' CHECK(status IN ('new', 'contacted', 'follow_up', 'interested', 'converted', 'closed')),
            remarks TEXT,
            
            follow_up_date TIMESTAMP,
            follow_up_time TEXT,
            last_contacted TIMESTAMP,
            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (company_id) REFERENCES companies(id),
            FOREIGN KEY (assigned_to) REFERENCES users(id),
            FOREIGN KEY (card_id) REFERENCES visiting_cards(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visiting_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE NOT NULL,
            
            user_id INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            
            name TEXT NOT NULL,
            designation TEXT,
            phone TEXT NOT NULL,
            whatsapp TEXT,
            email TEXT,
            address TEXT,
            bio TEXT,
            photo_url TEXT,
            
            theme TEXT DEFAULT 'modern',
            background_color TEXT DEFAULT '#ffffff',
            text_color TEXT DEFAULT '#000000',
            
            qr_code_path TEXT,
            
            views_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (company_id) REFERENCES companies(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS call_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            call_type TEXT,
            duration INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (lead_id) REFERENCES leads(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            key TEXT UNIQUE NOT NULL,
            name TEXT,
            source_type TEXT,
            webhook_url TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP,
            usage_count INTEGER DEFAULT 0,
            
            FOREIGN KEY (company_id) REFERENCES companies(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE NOT NULL,
            company_id INTEGER NOT NULL,
            
            order_id TEXT UNIQUE NOT NULL,
            transaction_id TEXT,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'INR',
            
            plan TEXT NOT NULL,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'success', 'failed', 'checksum_failed')),
            
            payment_mode TEXT,
            bank_name TEXT,
            bank_txn_id TEXT,
            
            checksum_verified INTEGER DEFAULT 0,
            paytm_response TEXT,
            
            invoice_number TEXT,
            invoice_url TEXT,
            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            
            FOREIGN KEY (company_id) REFERENCES companies(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            type TEXT,
            is_read INTEGER DEFAULT 0,
            link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS master_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform_name TEXT DEFAULT 'Next-Gen Digital Solutions',
            platform_tagline TEXT,
            platform_logo TEXT,
            master_name TEXT DEFAULT 'Next-Gen Digital Solutions',
            master_footer TEXT DEFAULT 'Made by Next-Gen Digital Solutions',
            master_homepage_url TEXT,
            
            homepage_content TEXT,
            about_content TEXT,
            features_content TEXT,
            privacy_policy TEXT,
            terms_conditions TEXT,
            
            showcase_enabled INTEGER DEFAULT 1,
            showcase_title TEXT,
            showcase_description TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS master_showcase_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            image_url TEXT,
            demo_url TEXT,
            is_featured INTEGER DEFAULT 0,
            display_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (company_id) REFERENCES companies(id)
        )
    ''')
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_company ON users(company_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_company ON leads(company_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_assigned ON leads(assigned_to)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cards_company ON visiting_cards(company_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cards_user ON visiting_cards(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_company ON payments(company_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)")
    
    conn.commit()
    conn.close()
    
    print("Database initialized successfully!")

if __name__ == "__main__":
    init_database()
