import base64
import string
import random
import hashlib
from Crypto.Cipher import AES

IV = "@@@@&&&&####$$$$"
BLOCK_SIZE = 16

def generate_random_string(length):
    return ''.join(random.choices(string.ascii_uppercase + string.digits + string.ascii_lowercase, k=length))

def get_pad(s):
    return chr(BLOCK_SIZE - len(s) % BLOCK_SIZE) * (BLOCK_SIZE - len(s) % BLOCK_SIZE)

def encode_base64_string(msg):
    return base64.b64encode(msg)

def decode_base64_string(msg):
    return base64.b64decode(msg)

def encrypt(input_data, key):
    plain_text = input_data + get_pad(input_data)
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, IV.encode('utf-8'))
    encrypted_text = cipher.encrypt(plain_text.encode('utf-8'))
    return encode_base64_string(encrypted_text).decode('utf-8')

def decrypt(input_data, key):
    encrypted_text = decode_base64_string(input_data)
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, IV.encode('utf-8'))
    decrypted_text = cipher.decrypt(encrypted_text)
    unpad = ord(decrypted_text[-1:])
    return decrypted_text[:-unpad].decode('utf-8')

def generate_signature(params, key):
    params_copy = params.copy()
    if 'CHECKSUMHASH' in params_copy:
        del params_copy['CHECKSUMHASH']
    
    sorted_params = sorted(params_copy.items())
    data_str = '|'.join([str(v) for k, v in sorted_params if v is not None and str(v).strip() != ''])
    
    salt = generate_random_string(4)
    data_str_with_salt = data_str + '|' + salt
    
    hash_string = hashlib.sha256(data_str_with_salt.encode('utf-8')).hexdigest()
    
    return encrypt(hash_string + salt, key)

def verify_signature(params, key, checksum):
    params_copy = params.copy()
    if 'CHECKSUMHASH' in params_copy:
        del params_copy['CHECKSUMHASH']
    
    sorted_params = sorted(params_copy.items())
    data_str = '|'.join([str(v) for k, v in sorted_params if v is not None and str(v).strip() != ''])
    
    try:
        decrypted = decrypt(checksum, key)
        received_hash = decrypted[:-4]
        salt = decrypted[-4:]
        
        data_str_with_salt = data_str + '|' + salt
        calculated_hash = hashlib.sha256(data_str_with_salt.encode('utf-8')).hexdigest()
        
        return received_hash == calculated_hash
    except Exception as e:
        print(f"Checksum verification error: {e}")
        return False

def generate_checksum(params, key):
    return generate_signature(params, key)

def verify_checksum(params, key, checksum):
    return verify_signature(params, key, checksum)
