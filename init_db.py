#!/usr/bin/env python3
import uuid
from werkzeug.security import generate_password_hash
from db import init_database, get_db

def create_master_admin():
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM users WHERE role = 'master_admin'")
        if cursor.fetchone():
            print("Master admin already exists!")
            return
        
        master_uid = str(uuid.uuid4())
        password_hash = generate_password_hash('Master@123')
        
        cursor.execute('''
            INSERT INTO users (uid, username, email, password_hash, role, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (master_uid, 'masteradmin', 'admin@nextgendigital.com', password_hash, 'master_admin', 1))
        
        print("Master admin created successfully!")
        print("Username: masteradmin")
        print("Password: Master@123")
        print("IMPORTANT: Change this password after first login!")

def create_master_settings():
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM master_settings")
        if cursor.fetchone():
            print("Master settings already exist!")
            return
        
        cursor.execute('''
            INSERT INTO master_settings (
                platform_name, platform_tagline, master_name, master_footer,
                homepage_content, about_content, features_content,
                showcase_enabled, showcase_title, showcase_description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            'Next-Gen Digital Solutions',
            'All-in-One Business Management Platform',
            'Next-Gen Digital Solutions',
            'Made by Next-Gen Digital Solutions',
            'Transform your business with our comprehensive digital solutions. Digital visiting cards, lead management, CRM, and more.',
            'We provide cutting-edge SaaS solutions for businesses of all sizes across various industries including real estate, automotive, IT services, and more.',
            'Digital Visiting Cards with QR Codes, Advanced Lead Management, Multi-tenant Company System, Payment Integration, White-label Support, and much more.',
            1,
            'Our Portfolio',
            'Trusted by businesses across industries. See how we have helped companies grow.'
        ))
        
        print("Master settings created successfully!")

def main():
    print("Initializing database...")
    init_database()
    
    print("\nCreating master admin...")
    create_master_admin()
    
    print("\nCreating master settings...")
    create_master_settings()
    
    print("\nDatabase initialization complete!")

if __name__ == "__main__":
    main()
