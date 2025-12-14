# Next-Gen Digital Solutions Platform

## Overview

A multi-tenant SaaS platform for business management, featuring digital visiting cards with QR codes, lead management, and CRM capabilities. The platform serves multiple business verticals including real estate, automotive, IT services, and more. Built with Flask and SQLite, it implements a hierarchical user system with Master Admin, Company Admin, and Sales Person roles.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Application Framework
- **Flask** serves as the web framework with Blueprint-based route organization
- Routes are modular: `auth`, `master`, `company`, `sales`, `card`, `payment`, `api`, `public`
- Jinja2 templating with Bootstrap 5 for responsive UI

### Database Layer
- **SQLite** with row factory for dict-like access
- Database file stored at `instance/saas_platform.db`
- Foreign keys enabled via PRAGMA
- Context manager pattern for connection handling in `db.py`

### User Role Hierarchy
1. **Master Admin** - Platform owner with full control over all companies, payments, analytics, and platform settings
2. **Company Admin** - Manages their company's cards, leads, sales persons, and branding
3. **Sales Person** - Handles assigned leads, follow-ups, and call history

### Key Features
- **Digital Visiting Cards** - QR-enabled cards with customizable themes, view tracking, and lead capture
- **Lead Management** - Multi-source lead capture (website, card, API, manual) with assignment and follow-up tracking
- **Subscription Plans** - Free (7 days, 2 cards), Basic (30 days, 10 cards, ₹499), Pro (365 days, unlimited, ₹4999 with white-label)
- **White Label Support** - Pro plan enables custom branding with hidden platform attribution

### Authentication & Sessions
- Session-based auth with 7-day permanent sessions
- Password hashing via Werkzeug security
- Role-based access control decorators (`login_required`, `role_required`, `master_required`)

### API System
- RESTful API at `/api/v1/` with API key authentication
- Per-company API keys with usage tracking and source type classification
- Lead creation endpoint for external integrations

## External Dependencies

### Payment Gateway
- **Paytm** integration for subscription payments
- Configurable staging/production environments
- Custom checksum generation using AES encryption (pycryptodome)

### Frontend Libraries (CDN)
- Bootstrap 5.3.2 for UI components
- Bootstrap Icons 1.11.1
- Google Fonts (Inter family)

### Environment Variables
- `SESSION_SECRET` - Flask secret key
- `PAYTM_MERCHANT_ID` - Paytm merchant identifier
- `PAYTM_MERCHANT_KEY` - Paytm encryption key
- `PAYTM_WEBSITE`, `PAYTM_INDUSTRY_TYPE`, `PAYTM_CHANNEL_ID`, `PAYTM_ENVIRONMENT` - Paytm configuration

### Python Dependencies
- Flask - Web framework
- Werkzeug - Password hashing and utilities
- pycryptodome - AES encryption for Paytm checksum
- qrcode - QR code generation for visiting cards
- openpyxl - Excel file generation for lead exports

## Recent Changes (December 14, 2025)
- Completed full platform implementation with all features
- Fixed login_required decorator to use correct blueprint endpoint
- Replaced pandas with csv/openpyxl for lead exports (lighter dependencies)
- Database initialized with master admin (masteradmin/Master@123)