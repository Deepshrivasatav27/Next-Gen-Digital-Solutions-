import os

class Config:
    SECRET_KEY = os.environ.get('SESSION_SECRET') or 'dev-secret-key-change-in-production'
    
    PAYTM_MERCHANT_ID = os.environ.get('PAYTM_MERCHANT_ID', '')
    PAYTM_MERCHANT_KEY = os.environ.get('PAYTM_MERCHANT_KEY', '')
    PAYTM_WEBSITE = os.environ.get('PAYTM_WEBSITE', 'WEBSTAGING')
    PAYTM_INDUSTRY_TYPE = os.environ.get('PAYTM_INDUSTRY_TYPE', 'Retail')
    PAYTM_CHANNEL_ID = os.environ.get('PAYTM_CHANNEL_ID', 'WEB')
    PAYTM_ENVIRONMENT = os.environ.get('PAYTM_ENVIRONMENT', 'staging')
    
    PLANS = {
        'free': {
            'name': 'Free',
            'days': 7,
            'price': 0,
            'cards_limit': 2,
            'white_label': False
        },
        'basic': {
            'name': 'Basic',
            'days': 30,
            'price': 499,
            'cards_limit': 10,
            'white_label': False
        },
        'pro': {
            'name': 'Pro',
            'days': 365,
            'price': 4999,
            'cards_limit': -1,
            'white_label': True
        }
    }
    
    @staticmethod
    def get_paytm_urls():
        if Config.PAYTM_ENVIRONMENT == 'production':
            return {
                'txn_url': 'https://securegw.paytm.in/order/process',
                'status_url': 'https://securegw.paytm.in/order/status',
                'website': Config.PAYTM_WEBSITE
            }
        else:
            return {
                'txn_url': 'https://securegw-stage.paytm.in/order/process',
                'status_url': 'https://securegw-stage.paytm.in/order/status',
                'website': 'WEBSTAGING'
            }
