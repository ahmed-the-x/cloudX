import os
import sys
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify, Response, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import mysql
from mysql.connector import pooling
from functools import wraps
import shutil
import tempfile
import tarfile
import rarfile
import py7zr
import gzip
import bz2
import lzma
import zstandard
import tarfile
import json
from io import BytesIO
from flask_compress import Compress
from io import BufferedReader
from concurrent.futures import ThreadPoolExecutor
import time
import shlex
import subprocess
from gevent import monkey
from mimetypes import guess_type
import requests
import hashlib
import pyclamd as clamd
from flask import abort
import secrets
from datetime import datetime, timedelta, timezone
import random
from contact import send_welcome_email, send_password_reset_email, send_password_change_confirmation_email, send_subscription_confirmation_email, send_subscription_cancellation_email, send_verification_email
import user_agents
import requests
import pycountry
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
import inspect

monkey.patch_all()
load_dotenv()

app = Flask(__name__)

REQUIRED_SECRETS = [
    'FLASK_SECRET_KEY',
    'MYSQL_USER',
    'MYSQL_PASSWORD',
    'MASTER_ENCRYPTION_KEY_HEX',
    'PAYPAL_CLIENT_ID',
    'PAYPAL_CLIENT_SECRET',
    'RECAPTCHA_SECRET_KEY',
    'ADMIN_EMAIL',
    'ADMIN_PASSWORD',
    'PUBLIC_UPLOAD_FOLDER', # <-- ADDED
    'PUBLIC_USER_EMAIL'     # <-- ADDED
]
missing_secrets = [key for key in REQUIRED_SECRETS if not os.environ.get(key)]
if missing_secrets:
    app.logger.error(f"FATAL ERROR: Missing required environment variables: {', '.join(missing_secrets)}")
    sys.exit(f"Error: Missing required environment variables: {', '.join(missing_secrets)}")

app.secret_key = os.environ.get('FLASK_SECRET_KEY')
app.config['UPLOAD_FOLDER'] = '/srv/sharex_data/user_files'
app.config['PUBLIC_UPLOAD_FOLDER'] = os.environ.get('PUBLIC_UPLOAD_FOLDER') # <-- ADDED

# MariaDB/MySQL Configuration
app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.environ.get('MYSQL_DB', 'cloudx_db')

server_name = os.environ.get('SERVER_NAME')
if server_name:
    app.config['SERVER_NAME'] = server_name

app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = (
    os.environ.get('MAIL_SENDER_NAME', 'CloudX Team'),
    os.environ.get('MAIL_SENDER_EMAIL', 'contact@cloudxhq.com')
)

MASTER_ENCRYPTION_KEY_HEX = os.environ.get('MASTER_ENCRYPTION_KEY_HEX')
app.config['MASTER_ENCRYPTION_KEY'] = bytes.fromhex(MASTER_ENCRYPTION_KEY_HEX)

# START: PAYPAL CONFIGURATION
app.config['PAYPAL_CLIENT_ID'] = os.environ.get('PAYPAL_CLIENT_ID')
app.config['PAYPAL_CLIENT_SECRET'] = os.environ.get('PAYPAL_CLIENT_SECRET')
app.config['PAYPAL_ENVIRONMENT'] = os.environ.get('PAYPAL_ENVIRONMENT', 'sandbox')
app.config['PAYPAL_BASIC_PLAN_ID'] = os.environ.get('PAYPAL_BASIC_PLAN_ID')
app.config['PAYPAL_PLUS_PLAN_ID'] = os.environ.get('PAYPAL_PLUS_PLAN_ID')
app.config['PAYPAL_PRO_PLAN_ID'] = os.environ.get('PAYPAL_PRO_PLAN_ID')

app.config['RECAPTCHA_SITE_KEY'] = os.environ.get('RECAPTCHA_SITE_KEY')
app.config['RECAPTCHA_SECRET_KEY'] = os.environ.get('RECAPTCHA_SECRET_KEY')

app.config['CLAMAV_MAX_FILE_SIZE_BYTES'] = 30 * 1024 * 1024
app.config['CLAMAV_MAX_FOLDER_ITEMS'] =  300
app.config['CLAMD_SOCKET'] = '/run/clamav/clamd.ctl'


os.umask(0o022)

db_pool = pooling.MySQLConnectionPool(
    pool_name="cloudx_pool",
    pool_size=5,
    host=app.config['MYSQL_HOST'],
    user=app.config['MYSQL_USER'],
    password=app.config['MYSQL_PASSWORD'],
    database=app.config['MYSQL_DB']
)

app.config['FREE_USER_QUOTA'] = 5 * 1024 * 1024 * 1024
app.config['BASIC_USER_QUOTA'] = 50 * 1024 * 1024 * 1024
app.config['PLUS_USER_QUOTA'] = 200 * 1024 * 1024 * 1024
app.config['PRO_USER_QUOTA'] = 500 * 1024 * 1024 * 1024

app.config['FREE_USER_UPLOAD_LIMIT'] = 1 * 1024 * 1024 * 1024
app.config['BASIC_USER_UPLOAD_LIMIT'] = 5 * 1024 * 1024 * 1024
app.config['PLUS_USER_UPLOAD_LIMIT'] = 20 * 1024 * 1024 * 1024
app.config['PRO_USER_UPLOAD_LIMIT'] = 50 * 1024 * 1024 * 1024

app.config['FREE_USER_BANDWIDTH'] = 2  * 1024 * 1024
app.config['BASIC_USER_BANDWIDTH'] = 4 * 1024 * 1024
app.config['PLUS_USER_BANDWIDTH'] = 6 * 1024 * 1024
app.config['PRO_USER_BANDWIDTH'] = 10  * 1024 * 1024

app.config['BUFFER_SIZE'] = 16 * 1024 * 1024
app.config['CHUNK_SIZE'] = 64 * 1024 * 1024
app.config['UPLOAD_CHUNK'] = 8 * 1024 * 1024
app.config['MAX_WORKERS'] = 20
app.config['ENCRYPTION_CHUNK_SIZE'] = 8 * 1024 * 1024


compress = Compress(app)
executor = ThreadPoolExecutor(max_workers=app.config['MAX_WORKERS'])

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PUBLIC_UPLOAD_FOLDER'], exist_ok=True) # <-- ADDED

def get_user_udek(user_id):
    if 'udek' in g and g.udek_user_id == user_id:
        return g.udek

    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT encrypted_udek FROM users WHERE id = %s', (user_id,))
        result = c.fetchone()
        if not result or not result[0]:
            raise ValueError(f"UDEK not found for user_id: {user_id}")

        encrypted_udek = result[0]
        nonce = encrypted_udek[:12]
        ciphertext_with_tag = encrypted_udek[12:]
        
        master_key = app.config['MASTER_ENCRYPTION_KEY']
        aesgcm = AESGCM(master_key)
        
        decrypted_udek = aesgcm.decrypt(nonce, ciphertext_with_tag, None)

        g.udek = decrypted_udek
        g.udek_user_id = user_id
        
        return decrypted_udek

    except mysql.connector.Error as err:
        app.logger.error(f"DB error fetching UDEK for user {user_id}: {err}")
        raise
    except InvalidTag:
        app.logger.error(f"FATAL: Master key failed to decrypt UDEK for user {user_id}. Master key may have changed.")
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


def encrypt_file_stream(source_path, dest_path, key):
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)

    with open(source_path, 'rb') as f_in, open(dest_path, 'wb') as f_out:
        f_out.write(nonce)
        
        while True:
            plaintext_chunk = f_in.read(app.config['ENCRYPTION_CHUNK_SIZE'])
            if not plaintext_chunk:
                break
            
            ciphertext_chunk = aesgcm.encrypt(nonce, plaintext_chunk, None)
            f_out.write(ciphertext_chunk)

def generate_decrypted_stream(encrypted_path, key, speed_limit=None):
    try:
        with open(encrypted_path, 'rb') as f:
            nonce = f.read(12)
            ciphertext_with_tag = f.read()
        
        aesgcm = AESGCM(key)
        decrypted_data = aesgcm.decrypt(nonce, ciphertext_with_tag, None)

        if speed_limit:
            chunk_size = app.config['CHUNK_SIZE']
            for i in range(0, len(decrypted_data), chunk_size):
                chunk = decrypted_data[i:i+chunk_size]
                yield chunk
                time.sleep(len(chunk) / speed_limit)
        else:
            yield decrypted_data

    except InvalidTag:
        app.logger.error(f"DECRYPTION FAILED: Invalid authentication tag for file {encrypted_path}")
        return
    except FileNotFoundError:
        app.logger.error(f"DECRYPTION FAILED: File not found at {encrypted_path}")
        return
        

def country_code_to_flag(iso_code):
    if not isinstance(iso_code, str) or len(iso_code) != 2:
        return '🌍'
    
    OFFSET = 0x1F1E6 - ord('A')
    
    return chr(ord(iso_code[0].upper()) + OFFSET) + chr(ord(iso_code[1].upper()) + OFFSET)

def safe_path_component(name):
    if not name:
        return 'unnamed'

    dangerous_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in dangerous_chars:
        name = name.replace(char, '_')

    name = name.strip('. ')

    if not name:
        name = 'unnamed'

    return name

def format_bytes_filter(size):
    if not isinstance(size, (int, float)) or size < 0:
        return "0 Bytes"
    if size == 0:
        return "0 Bytes"
    power = 1024
    n = 0
    power_labels = {0: 'Bytes', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size >= power and n < len(power_labels) -1 :
        size /= power
        n += 1
    return f"{size:.1f} {power_labels[n]}"

def generate_archive(path, archive_format, speed_limit=None):
    basename = os.path.basename(path.rstrip('/'))
    dirname = os.path.dirname(path)

    if archive_format == "zip":
        cmd = f"zip -r -q -3 - {shlex.quote(basename)}"
        mimetype = "application/zip"
        ext = ".zip"
    else:
        cmd = f"tar -cf - {shlex.quote(basename)} | zstd -6 -T1 -"
        mimetype = "application/zstd"
        ext = ".tar.zst"

    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=dirname,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=app.config['CHUNK_SIZE']
    )

    def stream():
        try:
            while True:
                chunk = proc.stdout.read(app.config['CHUNK_SIZE'])
                if not chunk:
                    break
                yield chunk
                if speed_limit:
                    time.sleep(len(chunk) / speed_limit)
        finally:
            proc.kill()

    return {
        'stream': stream(),
        'mimetype': mimetype,
        'filename': f"{basename}{ext}"
    }

def humanize_timedelta_filter(dt):
    if not dt:
        return "Never"

    now = datetime.now(timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    if dt <= now:
        return "Expired"

    delta = dt - now
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, _ = divmod(rem, 60)

    if days > 0:
        return f"in {days} day{'s' if days > 1 else ''}"
    if hours > 0:
        return f"in {hours} hour{'s' if hours > 1 else ''}"
    if minutes > 0:
        return f"in {minutes} minute{'s' if minutes > 1 else ''}"
    return "soon"

app.jinja_env.filters['filesizeformat'] = format_bytes_filter
app.jinja_env.filters['humanize_timedelta'] = humanize_timedelta_filter

def scan_file_with_clamav(file_path: str):
    try:
        if os.path.getsize(file_path) > app.config['CLAMAV_MAX_FILE_SIZE_BYTES']:
            app.logger.info(f"ClamAV: Skipping scan for large file {file_path}.")
            return {'status': 'skipped_large'}

        os.chmod(file_path, 0o644)
        
        sock_path = app.config.get('CLAMD_SOCKET')
        if not sock_path:
            raise RuntimeError("FATAL: CLAMD_SOCKET path is not configured.")
        cd = clamd.ClamdUnixSocket(sock_path)

        if not cd.ping():
            raise ConnectionError("ClamAV daemon did not respond to PING.")

        with open(file_path, 'rb') as f:
            scan_result = cd.scan_stream(f)

        if scan_result is not None:
            verdict = scan_result.get('stream', ('OK', None))
            if verdict[0] == 'FOUND':
                app.logger.warning(f"Malicious file FOUND: {file_path}. Details: {verdict[1]}")
                return {'status': 'malicious', 'positives': 1}

        return {'status': 'clean'}

    except ConnectionError as e:
        app.logger.error(f"ClamAV Connection Error: Could not connect to daemon at {sock_path}. {e}")
        return {'status': 'error', 'message': "ClamAV daemon not responding"}

    except Exception as e:
        app.logger.error(f"An unexpected ClamAV scanning exception occurred: {e}")
        return {'status': 'error', 'message': str(e)}

def get_db_connection():
    return db_pool.get_connection()

def init_db():
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()

        # 1. Create Users Table (With storage_used column enabled)
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(255) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    quota BIGINT DEFAULT %s,
                    tier VARCHAR(50) DEFAULT 'free',
                    reset_token VARCHAR(100) NULL,
                    reset_token_expiration DATETIME NULL,
                    fingerprint_hash VARCHAR(64) NULL UNIQUE,
                    paypal_subscription_id VARCHAR(255) NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    encrypted_udek VARBINARY(256) NULL,
                    country VARCHAR(100) NULL,
                    storage_used BIGINT DEFAULT 0
                    )''', (app.config['FREE_USER_QUOTA'],))
        
        # 2. Ensure columns exist (Migration Checks)
        c.execute("SHOW COLUMNS FROM users LIKE 'encrypted_udek'")
        if not c.fetchone():
            c.execute("ALTER TABLE users ADD COLUMN encrypted_udek VARBINARY(256) NULL")

        c.execute("SHOW COLUMNS FROM users LIKE 'paypal_subscription_id'")
        if not c.fetchone():
            c.execute("ALTER TABLE users ADD COLUMN paypal_subscription_id VARCHAR(255) NULL")

        c.execute("SHOW COLUMNS FROM users LIKE 'country'")
        if not c.fetchone():
            c.execute("ALTER TABLE users ADD COLUMN country VARCHAR(100) NULL")

        # 3. CRITICAL FIX: Restore/Add the storage_used column
        c.execute("SHOW COLUMNS FROM users LIKE 'storage_used'")
        if not c.fetchone():
            c.execute("ALTER TABLE users ADD COLUMN storage_used BIGINT DEFAULT 0")
            app.logger.info("Added 'storage_used' column for fast quota checking.")
        
        # Note: We REMOVED the code that drops this column.

        # 4. Create Shares Table
        c.execute('''CREATE TABLE IF NOT EXISTS shares (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    token VARCHAR(32) UNIQUE NOT NULL,
                    user_id INT NOT NULL,
                    username VARCHAR(255) NOT NULL,
                    item_path TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NULL DEFAULT NULL,
                    permissions VARCHAR(50) NOT NULL,
                    password_hash VARCHAR(255) NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )''')

        c.execute("SHOW COLUMNS FROM shares LIKE 'password_hash'")
        if not c.fetchone():
            c.execute("ALTER TABLE shares ADD COLUMN password_hash VARCHAR(255) NULL")
        
        # 5. Create Analytics Table
        c.execute('''CREATE TABLE IF NOT EXISTS share_analytics (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    share_token VARCHAR(32) NOT NULL,
                    interaction_type ENUM('view', 'preview', 'download') NOT NULL,
                    ip_address VARCHAR(45),
                    user_agent TEXT,
                    country VARCHAR(100),
                    device_type VARCHAR(50),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX token_idx (share_token)
                    )''')
        
        conn.commit()
        app.logger.info("Database initialized successfully (Fast Upload Mode)")

    except mysql.connector.Error as err:
        app.logger.error(f"Error initializing database: {err}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

init_db()

def create_admin_user():
    conn = None
    try:
        admin_email = os.environ.get('ADMIN_EMAIL')
        admin_pass = os.environ.get('ADMIN_PASSWORD')
        
        if not admin_email or not admin_pass:
            app.logger.warning("ADMIN_EMAIL or ADMIN_PASSWORD not set. Admin user will not be created.")
            return

        conn = get_db_connection()
        conn.start_transaction()
        c = conn.cursor()
        
        c.execute('SELECT id FROM users WHERE email = %s FOR UPDATE', (admin_email,))
        
        hashed_password = generate_password_hash(admin_pass)

        if c.fetchone():
            app.logger.info(f"Admin user '{admin_email}' already exists. Ensuring tier and password are up to date.")
            c.execute(
                "UPDATE users SET tier = 'admin', password = %s WHERE email = %s",
                (hashed_password, admin_email)
            )
        else:
            app.logger.info(f"Creating new admin user: {admin_email}")
            
            udek = os.urandom(32)
            aesgcm = AESGCM(app.config['MASTER_ENCRYPTION_KEY'])
            nonce = os.urandom(12)
            encrypted_udek = nonce + aesgcm.encrypt(nonce, udek, None)
            
            c.execute(
                'INSERT INTO users (username, email, password, tier, quota, encrypted_udek) VALUES (%s, %s, %s, %s, %s, %s)',
                ('Admin', admin_email, hashed_password, 'admin', 0, encrypted_udek)
            )
            app.logger.info(f"Admin user {admin_email} created successfully.")

        conn.commit()

    except mysql.connector.Error as err:
        app.logger.error(f"Error creating/updating admin user: {err}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# --- NEW FUNCTION ---
def create_public_user():
    conn = None
    try:
        public_email = os.environ.get('PUBLIC_USER_EMAIL')
        if not public_email:
            app.logger.error("PUBLIC_USER_EMAIL not set. Cannot create public user.")
            return

        conn = get_db_connection()
        conn.start_transaction()
        c = conn.cursor()
        
        c.execute('SELECT id FROM users WHERE email = %s FOR UPDATE', (public_email,))
        
        if c.fetchone():
            app.logger.info(f"Public Uploader user '{public_email}' already exists.")
        else:
            app.logger.info(f"Creating new Public Uploader user: {public_email}")
            
            # Generate a new UDEK for this user
            udek = os.urandom(32)
            aesgcm = AESGCM(app.config['MASTER_ENCRYPTION_KEY'])
            nonce = os.urandom(12)
            encrypted_udek = nonce + aesgcm.encrypt(nonce, udek, None)
            
            # Create the user with a 100GB quota and 'public' tier
            # Tier 'public' is used to identify it, e.g. in get_user_dir
            c.execute(
                'INSERT INTO users (username, email, password, tier, quota, encrypted_udek) VALUES (%s, %s, %s, %s, %s, %s)',
                ('Public Uploader', public_email, generate_password_hash(secrets.token_hex(32)), 'public', 100 * 1024 * 1024 * 1024, encrypted_udek)
            )
            app.logger.info(f"Public Uploader user {public_email} created successfully.")

        conn.commit()

        # CRITICAL: Find and log the ID for the .env file
        c.execute('SELECT id FROM users WHERE email = %s', (public_email,))
        user = c.fetchone()
        if user:
            app.logger.warning(f"CRITICAL: Set PUBLIC_UPLOADER_USER_ID={user[0]} in your .env file.")
        
    except mysql.connector.Error as err:
        app.logger.error(f"Error creating/updating public user: {err}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

create_admin_user()
create_public_user() # <-- ADDED

def log_share_interaction(token, interaction_type, ip_address, ua_string):
    try:
        ua = user_agents.parse(ua_string)
        device_type = 'Desktop'
        if ua.is_mobile:
            device_type = 'Mobile'
        elif ua.is_tablet:
            device_type = 'Tablet'

        country = None
        try:
            response = requests.get(f'http://ip-api.com/json/{ip_address}', timeout=2)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    country = data.get('country')
        except requests.RequestException:
            pass

        conn = None
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute(
                """INSERT INTO share_analytics 
                   (share_token, interaction_type, ip_address, user_agent, country, device_type) 
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (token, interaction_type, ip_address, ua_string, country, device_type)
            )
            conn.commit()
        except mysql.connector.Error as err:
            app.logger.error(f"Analytics DB error: {err}")
        finally:
            if conn:
                conn.close()

    except Exception as e:
        app.logger.error(f"Error in log_share_interaction: {e}")

def get_best_archive_format(user_agent):
    ua = user_agent.lower()
    if any(keyword in ua for keyword in ["windows", "android", "iphone", "ipad", "ipod", "mobile", "ios"]):
        return "zip"
    return "tar.zst"


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        conn = None
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('SELECT tier FROM users WHERE id = %s', (session['user_id'],))
            result = c.fetchone()
            if not result or result[0] != 'admin':
                flash("You do not have permission to access this page.", "error")
                return redirect(url_for('mycloud'))
        except mysql.connector.Error as err:
            app.logger.error(f"DB error in admin_required: {err}")
            flash("An error occurred while verifying permissions.", "error")
            return redirect(url_for('mycloud'))
        finally:
            if conn:
                conn.close()
                
        return f(*args, **kwargs)
    return decorated_function

# --- MODIFIED FUNCTION ---
def get_user_dir(user_id):
    """
    Gets the base directory for a user.
    Routes the PUBLIC_UPLOADER_USER_ID to PUBLIC_UPLOAD_FOLDER.
    Routes all other users to UPLOAD_FOLDER/<user_id>.
    """
    public_user_id = os.environ.get('PUBLIC_UPLOADER_USER_ID')
    
    # Check if this is the public uploader
    if public_user_id and str(user_id) == str(public_user_id):
        public_dir = app.config.get('PUBLIC_UPLOAD_FOLDER')
        os.makedirs(public_dir, exist_ok=True)
        return public_dir
    
    # Original logic for all other registered users
    user_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def get_user_speed_limit(user_id):
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT tier FROM users WHERE id = %s', (user_id,))
        result = c.fetchone()
        if not result:
            return app.config['FREE_USER_BANDWIDTH']

        user_tier = result[0]
        if user_tier == 'basic':
            return app.config['BASIC_USER_BANDWIDTH']
        elif user_tier == 'plus':
            return app.config['PLUS_USER_BANDWIDTH']
        elif user_tier == 'pro':
            return app.config['PRO_USER_BANDWIDTH']
        else: # 'free', 'admin', 'public'
            return app.config['FREE_USER_BANDWIDTH']

    except mysql.connector.Error as err:
        app.logger.error(f"Database error in get_user_speed_limit: {err}")
        return app.config['FREE_USER_BANDWIDTH']
    finally:
        if conn:
            conn.close()

def get_file_size(filepath):
    try:
        encrypted_size = os.path.getsize(filepath)
        # 12 bytes (nonce) + 16 bytes (tag) = 28 bytes overhead
        return max(0, encrypted_size - 28)
    except FileNotFoundError:
        return 0

def get_folder_size(folder_path):
    total_size = 0
    if not os.path.exists(folder_path):
        return total_size

    try:
        for root, dirs, files in os.walk(folder_path):
            for f in files:
                fp = os.path.join(root, f)
                if not os.path.islink(fp): # avoid symlink loops
                    total_size += get_file_size(fp)
    except Exception as e:
        app.logger.error(f"Error calculating folder size for {folder_path}: {e}")
    return total_size

def get_unique_filename(path):
    if not os.path.exists(path):
        return path

    directory, filename = os.path.split(path)
    name, ext = os.path.splitext(filename)

    new_name = f"{name}_copy{ext}"
    new_path = os.path.join(directory, new_name)
    if not os.path.exists(new_path):
        return new_path

    i = 2
    while True:
        new_name = f"{name}_copy({i}){ext}"
        new_path = os.path.join(directory, new_name)
        if not os.path.exists(new_path):
            return new_path
        i += 1

def get_file_icon(filename, for_filter=False):
    if not filename:
        return "/static/icons/file.svg"

    ext = os.path.splitext(filename)[1].lower().strip('.')

    if ext == '':
        return "folder" if for_filter else "/static/icons/folder.svg"
    image_icons = {
        'jpg': '/static/icons/image.svg', 'jpeg': '/static/icons/image.svg',
        'png': '/static/icons/image.svg', 'gif': '/static/icons/image.svg',
        'bmp': '/static/icons/image.svg', 'svg': '/static/icons/image.svg',
        'webp': '/static/icons/image.svg'
    }
    if ext in image_icons:
        return "image" if for_filter else image_icons[ext]

    doc_icons = {
        'pdf': '/static/icons/pdf.svg', 'doc': '/static/icons/docx.svg',
        'docx': '/static/icons/docx.svg', 'xls': '/static/icons/xls.svg',
        'xlsx': '/static/icons/xlsx.svg', 'ppt': '/static/icons/ppt.svg',
        'pptx': '/static/icons/pptx.svg'
    }
    if ext in doc_icons:
        return "description" if for_filter else doc_icons[ext]

    text_icons = {'txt': '/static/icons/txt.svg', 'md': '/static/icons/txt.svg', 'rtf': '/static/icons/txt.svg'}
    if ext in text_icons:
        return "article" if for_filter else text_icons[ext]

    audio_icons = {
        'mp3': '/static/icons/mp3.svg', 'wav': '/static/icons/mp3.svg', 'ogg': '/static/icons/mp3.svg',
        'flac': '/static/icons/mp3.svg', 'aac': '/static/icons/mp3.svg', 'm4a': '/static/icons/mp3.svg',
        'wma': '/static/icons/mp3.svg'
    }
    if ext in audio_icons:
        return "audiotrack" if for_filter else audio_icons[ext]

    video_exts = ['mp4', 'mov', 'avi', 'mkv', 'flv', 'wmv']
    if ext in video_exts:
        return "movie" if for_filter else "/static/icons/mp4.svg"

    archive_exts = ['zip', 'rar', '7z', 'tar', 'gz', 'zst']
    if ext in archive_exts:
        return "archive" if for_filter else "/static/icons/compressed.svg"

    code_exts = ['html', 'htm', 'css', 'js', 'json', 'py', 'java', 'cpp', 'c', 'h', 'php', 'sh', 'bat']
    if ext in code_exts:
        return "code" if for_filter else "/static/icons/code.svg"

    return "/static/icons/file.svg"


app.jinja_env.globals.update(get_file_emoji=get_file_icon)

def get_client_ip(request):
    if request.headers.get('X-Forwarded-For'):
        ips = request.headers.get('X-Forwarded-For').split(',')
        return ips[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP').strip()
    else:
        return request.remote_addr

def generate_public_share_url(token):
    public_domain = os.environ.get('PUBLIC_DOMAIN', 'cloudxhq.com')
    path = f"/shared/{token}"
    return f"https://{public_domain}{path}"

@app.route('/')
@login_required
def home():
    user_id = session['user_id']
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT tier FROM users WHERE id = %s', (user_id,))
        result = c.fetchone()
        if result and result[0] == 'admin':
            return redirect(url_for('admin_dashboard'))
    except mysql.connector.Error as err:
        app.logger.error(f"DB error in home route redirect: {err}")
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for('mycloud'))

@app.route('/mycloud')
@login_required
def mycloud():
    user_id = session['user_id']
    username = session['username']
    current_dir = request.args.get('path', '')
    user_base = get_user_dir(user_id)
    full_path = os.path.join(user_base, current_dir)

    # Cleanup logic (keep as is)
    try:
        for root, dirs, files in os.walk(user_base):
            for file in files:
                if file.endswith('.part'):
                    part_file_path = os.path.join(root, file)
                    try:
                        if os.path.getmtime(part_file_path) < time.time() - 3600: # Only delete old parts
                            os.remove(part_file_path)
                    except Exception: pass
    except Exception: pass

    if not os.path.abspath(full_path).startswith(os.path.abspath(user_base)):
        return "Invalid path", 400

    items = []
    if os.path.exists(full_path):
        for item in os.listdir(full_path):
            if not item.endswith('.part'):
                item_path = os.path.join(full_path, item)
                try:
                    is_dir = os.path.isdir(item_path)
                    # Note: Listing individual file sizes is okay, scanning the WHOLE quota is the bottleneck.
                    # We keep get_folder_size here for single folder display, or you can remove it for more speed.
                    total_size = get_folder_size(item_path) if is_dir else get_file_size(item_path)
                    items.append({
                        'name': item,
                        'is_dir': is_dir,
                        'size': total_size,
                        'path': os.path.join(current_dir, item),
                        'date': str(int(os.path.getmtime(item_path)))
                    })
                except FileNotFoundError:
                    continue

    parent_dir = os.path.dirname(current_dir) if current_dir else ''

    conn = None
    user_tier = 'free'
    quota = app.config['FREE_USER_QUOTA']
    user_used = 0
    upload_limit = app.config['FREE_USER_UPLOAD_LIMIT']
    bandwidth = app.config['FREE_USER_BANDWIDTH']

    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        # FAST FIX: Select storage_used from DB
        c.execute('SELECT tier, quota, storage_used FROM users WHERE id = %s', (user_id,))
        result = c.fetchone()
        if result:
            user_tier = result['tier']
            quota = result['quota']
            # FAST FIX: Use DB value
            user_used = result['storage_used'] if result['storage_used'] is not None else 0

            if user_tier == 'admin':
                return redirect(url_for('admin_dashboard'))
            
            # Check if usage is 0 but files exist (Migration/Sync check)
            # Only runs if DB says 0 to self-heal once.
            if user_used == 0 and os.path.exists(user_base) and len(os.listdir(user_base)) > 0:
                 real_size = get_folder_size(user_base)
                 if real_size > 0:
                     c.execute('UPDATE users SET storage_used = %s WHERE id = %s', (real_size, user_id))
                     conn.commit()
                     user_used = real_size

            if user_tier == 'basic':
                upload_limit = app.config['BASIC_USER_UPLOAD_LIMIT']
                bandwidth = app.config['BASIC_USER_BANDWIDTH']
            elif user_tier == 'plus':
                upload_limit = app.config['PLUS_USER_UPLOAD_LIMIT']
                bandwidth = app.config['PLUS_USER_BANDWIDTH']
            elif user_tier == 'pro':
                upload_limit = app.config['PRO_USER_UPLOAD_LIMIT']
                bandwidth = app.config['PRO_USER_BANDWIDTH']
    except mysql.connector.Error as err:
        app.logger.error(f"Database error in mycloud: {err}")
    finally:
        if conn: conn.close()

    percent_used = min(round(float(user_used) / float(quota) * 100, 2), 100) if quota > 0 else 0
    
    template_params = {
        'items': items,
        'current_dir': current_dir,
        'parent_dir': parent_dir,
        'username': username,
        'used': user_used,
        'quota': quota,
        'percent_used': percent_used,
        'upload_limit': upload_limit,
        'bandwidth': bandwidth
    }

    if user_tier == 'pro':
        return render_template('pro_user.html', **template_params)
    elif user_tier == 'plus':
        return render_template('plus_user.html', **template_params)
    elif user_tier == 'basic':
        return render_template('basic_user.html', **template_params)
    else:
        template_params.pop('bandwidth', None)
        return render_template('free_user.html', **template_params)

@app.route('/upgrade')
@login_required
def upgrade():
    user_id = session['user_id']
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT tier FROM users WHERE id = %s', (user_id,))
        current_tier = c.fetchone()[0]
    except mysql.connector.Error as err:
        app.logger.error(f"Database error retrieving tier for upgrade: {err}")
        flash("Error retrieving your current tier.")
        return redirect(url_for('mycloud'))
    finally:
        if conn:
            conn.close()

    return render_template('upgrade.html',
                           current_tier=current_tier,
                           paypal_client_id=app.config['PAYPAL_CLIENT_ID'],
                           basic_plan_id=app.config['PAYPAL_BASIC_PLAN_ID'],
                           plus_plan_id=app.config['PAYPAL_PLUS_PLAN_ID'],
                           pro_plan_id=app.config['PAYPAL_PRO_PLAN_ID'])

@app.route('/cancel_subscription', methods=['POST'])
@login_required
def cancel_subscription():
    user_id = session['user_id']
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute('SELECT username, email, paypal_subscription_id FROM users WHERE id = %s', (user_id,))
        user = c.fetchone()

        if not user:
            flash("User not found.", "error")
            return redirect(url_for('account'))

        subscription_id = user.get('paypal_subscription_id')
        username = user.get('username')
        user_email = user.get('email')

        if subscription_id and subscription_id.startswith('I-'):
            access_token = get_paypal_access_token()
            if not access_token:
                flash('Could not connect to payment provider. Please try again later.', 'error')
                return redirect(url_for('account'))

            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            }
            base_url = "https://api-m.sandbox.paypal.com" if app.config['PAYPAL_ENVIRONMENT'] == 'sandbox' else "https://api-m.paypal.com"
            url = f"{base_url}/v1/billing/subscriptions/{subscription_id}/cancel"
            body = {'reason': 'Cancelled by user from website'}

            response = requests.post(url, headers=headers, json=body)

            if response.status_code != 204:
                app.logger.error(f"PayPal cancellation failed for user {user_id}: {response.text}")
                flash('Failed to cancel subscription with our payment provider. Please contact support.', 'error')
                return redirect(url_for('account'))

        c.execute(
            'UPDATE users SET tier = %s, quota = %s, paypal_subscription_id = NULL WHERE id = %s',
            ('free', app.config['FREE_USER_QUOTA'], user_id)
        )
        conn.commit()

        if user_email and username:
            executor.submit(send_subscription_cancellation_email, app, user_email, username)

        flash('Your subscription has been successfully cancelled. Your plan has been changed to Free.', 'success')

    except requests.exceptions.RequestException as e:
        app.logger.error(f"PayPal API request error during cancellation: {e}")
        flash('A network error occurred while trying to cancel. Please try again.', 'error')
    except mysql.connector.Error as e:
        if conn: conn.rollback()
        app.logger.error(f"Database error during subscription cancellation: {e}")
        flash('A database error occurred. Please try again.', 'error')
    finally:
        if conn: conn.close()

    return redirect(url_for('account'))

@app.route('/payment')
@login_required
def payment():
    user_id = session['user_id']
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT tier FROM users WHERE id = %s', (user_id,))
        current_tier = c.fetchone()[0]
    except mysql.connector.Error as err:
        app.logger.error(f"Database error retrieving tier for payment: {err}")
        flash("Error retrieving your current tier.")
        return redirect(url_for('mycloud'))
    finally:
        if conn:
            conn.close()

    return render_template('payment.html',
                           current_tier=current_tier,
                           paypal_client_id=app.config['PAYPAL_CLIENT_ID'],
                           basic_plan_id=app.config['PAYPAL_BASIC_PLAN_ID'],
                           plus_plan_id=app.config['PAYPAL_PLUS_PLAN_ID'],
                           pro_plan_id=app.config['PAYPAL_PRO_PLAN_ID'])

@app.route('/api/process-card-payment', methods=['POST'])
@login_required
def process_card_payment():
    data = request.json
    plan_tier = data.get('plan')
    user_id = session['user_id']

    time.sleep(2)

    if plan_tier in ['basic', 'plus', 'pro']:
        if plan_tier == 'basic':
            new_tier = 'basic'
            new_quota = app.config['BASIC_USER_QUOTA']
        elif plan_tier == 'plus':
            new_tier = 'plus'
            new_quota = app.config['PLUS_USER_QUOTA']
        else:
            new_tier = 'pro'
            new_quota = app.config['PRO_USER_QUOTA']

        conn = None
        try:
            conn = get_db_connection()
            c = conn.cursor()
            test_subscription_id = f"dev-card-{secrets.token_hex(8)}"

            c.execute('UPDATE users SET tier = %s, quota = %s, paypal_subscription_id = %s WHERE id = %s',
                     (new_tier, new_quota, test_subscription_id, user_id))
            conn.commit()

            flash(f"Successfully upgraded to the {new_tier.capitalize()} plan!", 'success')
            return jsonify({
                'success': True,
                'redirectUrl': url_for('mycloud')
            })
        except mysql.connector.Error as e:
            if conn:
                conn.rollback()
            app.logger.error(f"DB Error during card payment upgrade: {e}")
            return jsonify({'success': False, 'error': 'Database update failed'}), 500
        finally:
            if conn:
                conn.close()

    return jsonify({'success': False, 'error': 'Invalid plan specified'}), 400

def get_paypal_access_token():
    auth = (app.config['PAYPAL_CLIENT_ID'], app.config['PAYPAL_CLIENT_SECRET'])
    data = {'grant_type': 'client_credentials'}
    url = 'https://api-m.sandbox.paypal.com/v1/oauth2/token' if app.config['PAYPAL_ENVIRONMENT'] == 'sandbox' else 'https://api-m.paypal.com/v1/oauth2/token'
    
    try:
        response = requests.post(url, auth=auth, data=data, headers={'Accept': 'application/json', 'Accept-Language': 'en_US'})
        response.raise_for_status()
        return response.json()['access_token']
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Failed to get PayPal access token: {e}")
        return None

@app.route('/api/paypal/create-subscription', methods=['POST'])
@login_required
def create_paypal_subscription():
    access_token = get_paypal_access_token()
    if not access_token:
        return jsonify({'error': 'Could not authenticate with PayPal.'}), 500
        
    plan_id = request.json.get('plan_id')
    if not plan_id:
        return jsonify({'error': 'Plan ID is missing.'}), 400

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'PayPal-Request-Id': str(random.randint(1, 100000))
    }
    
    url = 'https://api-m.sandbox.paypal.com/v1/billing/subscriptions' if app.config['PAYPAL_ENVIRONMENT'] == 'sandbox' else 'https://api-m.paypal.com/v1/billing/subscriptions'
    
    subscription_data = {
        'plan_id': plan_id,
        'application_context': {
            'brand_name': 'CloudX',
            'locale': 'en-US',
            'shipping_preference': 'NO_SHIPPING',
            'user_action': 'SUBSCRIBE_NOW',
            'return_url': url_for('upgrade', _external=True),
            'cancel_url': url_for('upgrade', _external=True)
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=subscription_data)
        response.raise_for_status()
        subscription = response.json()
        return jsonify({'id': subscription['id']})
    except requests.exceptions.HTTPError as e:
        app.logger.error(f"PayPal API Error during subscription creation: {e.response.text}")
        return jsonify({'error': 'Failed to create subscription with PayPal.', 'details': e.response.json()}), 500
    except Exception as e:
        app.logger.error(f"Generic error during subscription creation: {e}")
        return jsonify({'error': 'An unexpected error occurred.'}), 500


@app.route('/api/paypal/capture-subscription', methods=['POST'])
@login_required
def capture_paypal_subscription():
    data = request.json
    subscription_id = data.get('subscriptionID')
    plan_tier = data.get('planTier')
    user_id = session['user_id']

    if not all([subscription_id, plan_tier, user_id]):
        return jsonify({'error': 'Missing data required for subscription capture.'}), 400

    if plan_tier == 'basic':
        new_tier = 'basic'
        new_quota = app.config['BASIC_USER_QUOTA']
    elif plan_tier == 'plus':
        new_tier = 'plus'
        new_quota = app.config['PLUS_USER_QUOTA']
    elif plan_tier == 'pro':
        new_tier = 'pro'
        new_quota = app.config['PRO_USER_QUOTA']
    else:
        return jsonify({'error': 'Invalid plan name specified.'}), 400

    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()

        c.execute('SELECT username, email FROM users WHERE id = %s', (user_id,))
        user_details = c.fetchone()
        if not user_details:
            return jsonify({'error': 'User not found.'}), 404
        username, user_email = user_details

        c.execute(
            'UPDATE users SET tier = %s, quota = %s, paypal_subscription_id = %s WHERE id = %s',
            (new_tier, new_quota, subscription_id, user_id)
        )
        conn.commit()

        executor.submit(send_subscription_confirmation_email, app, user_email, username, new_tier.capitalize())

        flash(f"Successfully upgraded to the {new_tier.capitalize()} plan!", 'success')
        return jsonify({'success': True, 'redirectUrl': url_for('mycloud')})
    except mysql.connector.Error as e:
        if conn: conn.rollback()
        app.logger.error(f"DB Error during user tier update (PayPal): {e}")
        return jsonify({'error': 'Database update failed while saving subscription.'}), 500
    finally:
        if conn: conn.close()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = None
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('SELECT id, username, email, password, tier FROM users WHERE email = %s', (email,))
            user = c.fetchone()

            if user and check_password_hash(user[3], password):
                session['user_id'] = user[0]
                session['username'] = user[1]
                
                user_tier = user[4]
                if user_tier == 'admin':
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('mycloud'))
            else:
                flash('Invalid email or password')
        except mysql.connector.Error as err:
            app.logger.error(f"Database error during login: {err}")
            flash("An error occurred during login. Please try again.")
        finally:
            if conn:
                conn.close()

    return render_template('login.html')

def is_reputable_domain(email):
    disposable_domains = {'mailinator.com', 'temp-mail.org', '10minutemail.com', 'guerrillamail.com'}
    domain = email.split('@')[-1]
    return domain.lower() not in disposable_domains

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        visitor_id = request.form.get('fp_visitor_id')
        recaptcha_response = request.form.get('g-recaptcha-response')

        if not all([username, email, password, visitor_id]):
            flash('A problem occurred. Please fill out the form again.')
            return redirect(url_for('register'))

        if not recaptcha_response:
            flash('Please complete the reCAPTCHA challenge to continue.')
            return redirect(url_for('register'))

        if not is_reputable_domain(email):
            flash('Please use a reputable email provider. Disposable email services are not allowed.')
            return redirect(url_for('register'))

        if len(password) < 8:
            flash('Password must be at least 8 characters long.')
            return redirect(url_for('register'))

        conn = None
        try:
            conn = get_db_connection()
            c = conn.cursor()

            c.execute('SELECT id FROM users WHERE fingerprint_hash = %s', (visitor_id,))
            if c.fetchone():
                app.logger.warning(f"Duplicate registration attempt blocked for visitor ID: {visitor_id}")
                return render_template('register.html', duplicate_found=True, site_key=app.config['RECAPTCHA_SITE_KEY'])

            c.execute('SELECT id FROM users WHERE email = %s', (email,))
            if c.fetchone():
                flash('An account with this email already exists.')
                return redirect(url_for('register'))

            ip_address = get_client_ip(request)

            user_country = None
            try:
                response = requests.get(f'http://ip-api.com/json/{ip_address}', timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'success':
                        user_country = data.get('country')
            except requests.RequestException as e:
                app.logger.warning(f"Could not get country for IP {ip_address}: {e}")
                
            verify_url = 'https://www.google.com/recaptcha/api/siteverify'
            payload = {
                'secret': app.config['RECAPTCHA_SECRET_KEY'],
                'response': recaptcha_response,
                'remoteip': ip_address
            }
            response = requests.post(verify_url, data=payload)
            result = response.json()
            if not result.get('success'):
                flash('reCAPTCHA verification failed. Please try again.')
                return redirect(url_for('register'))

            verification_code = f"{random.randint(100000, 999999)}"
            session['registration_data'] = {
                'username': username,
                'email': email,
                'password_hash': generate_password_hash(password),
                'fingerprint_hash': visitor_id,
                'verification_code': verification_code,
                'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                'country': user_country
            }

            executor.submit(send_verification_email, app, email, username, verification_code)
            flash(f'A verification code has been sent to {email}. Please check your inbox.', 'info')
            return redirect(url_for('verify_email'))

        except requests.exceptions.RequestException as e:
            app.logger.error(f"reCAPTCHA request failed: {e}")
            flash('Could not verify reCAPTCHA. Please check your connection and try again.')
            return redirect(url_for('register'))
        except mysql.connector.Error as e:
            flash(f'A database error occurred during registration. Please try again later.')
            app.logger.error(f"Registration DB error: {e}")
            return redirect(url_for('register'))
        finally:
            if conn:
                conn.close()

    return render_template('register.html', duplicate_found=False, site_key=app.config['RECAPTCHA_SITE_KEY'])

@app.route('/verify', methods=['GET', 'POST'])
def verify_email():
    if 'registration_data' not in session:
        flash('Your registration session has expired. Please start over.', 'warning')
        return redirect(url_for('register'))

    reg_data = session['registration_data']
    expires_at = datetime.fromisoformat(reg_data['expires_at'])

    if datetime.now(timezone.utc) > expires_at:
        session.pop('registration_data', None)
        flash('The verification code has expired. Please register again.', 'error')
        return redirect(url_for('register'))

    if request.method == 'POST':
        submitted_code = request.form.get('verification_code')
        if submitted_code == reg_data['verification_code']:
            conn = None
            try:
                conn = get_db_connection()
                c = conn.cursor()
                
                udek = os.urandom(32)
                aesgcm = AESGCM(app.config['MASTER_ENCRYPTION_KEY'])
                nonce = os.urandom(12)
                encrypted_udek = nonce + aesgcm.encrypt(nonce, udek, None)

                c.execute('INSERT INTO users (username, email, password, fingerprint_hash, encrypted_udek, country) VALUES (%s, %s, %s, %s, %s, %s)',
                         (reg_data['username'], reg_data['email'], reg_data['password_hash'],
                          reg_data.get('fingerprint_hash'), encrypted_udek, reg_data.get('country')))
                conn.commit()

                executor.submit(send_welcome_email, app, reg_data['email'], reg_data['username'])

                new_user_id = c.lastrowid
                user_dir = get_user_dir(new_user_id) # This will create their /user_files/<id> folder
                os.makedirs(user_dir, exist_ok=True)

                session.pop('registration_data', None)
                flash('Account verified successfully! Please log in.', 'success')
                return redirect(url_for('login'))

            except mysql.connector.Error as e:
                if conn:
                    conn.rollback()
                if e.errno == 1062:
                    flash('An account with this email or device ID was created while you were verifying. Please log in or register with a different email.')
                else:
                    flash(f'An error occurred: {str(e)}')
                app.logger.error(f"Verification DB error: {str(e)}")
                return redirect(url_for('register'))
            finally:
                if conn:
                    conn.close()
        else:
            flash('Invalid verification code. Please try again.', 'error')

    return render_template('verify_email.html')

@app.route('/forgot_password', methods=['POST'])
def forgot_password():
    email = request.form.get('email')
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute('SELECT id, username, email FROM users WHERE email = %s', (email,))
        user = c.fetchone()

        if user:
            token = secrets.token_urlsafe(24)
            expires = datetime.now(timezone.utc) + timedelta(hours=1)

            c.execute('UPDATE users SET reset_token = %s, reset_token_expiration = %s WHERE id = %s',
                      (token, expires, user['id']))
            conn.commit()

            executor.submit(send_password_reset_email, app, user['email'], user['username'], token)

        flash('If an account with that email exists, a password reset link has been sent.', 'info')
        return redirect(url_for('login'))

    except mysql.connector.Error as err:
        app.logger.error(f"Database error during password reset request: {err}")
        if conn: conn.rollback()
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('login'))
    finally:
        if conn: conn.close()


@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset_with_token(token):
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute('SELECT id, username, email FROM users WHERE reset_token = %s AND reset_token_expiration > %s',
                  (token, datetime.now(timezone.utc)))
        user = c.fetchone()

        if not user:
            flash('This password reset link is invalid or has expired.', 'error')
            return redirect(url_for('login'))

        if request.method == 'POST':
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')

            if not password or len(password) < 8:
                flash('Password must be at least 8 characters long.', 'error')
                return render_template('reset_password.html', token=token)

            if password != confirm_password:
                flash('Passwords do not match.', 'error')
                return render_template('reset_password.html', token=token)

            hashed_password = generate_password_hash(password)
            c.execute('UPDATE users SET password = %s, reset_token = NULL, reset_token_expiration = NULL WHERE id = %s',
                      (hashed_password, user['id']))
            conn.commit()

            executor.submit(send_password_change_confirmation_email, app, user['email'], user['username'])

            flash('Your password has been successfully updated! You can now log in.', 'success')
            return redirect(url_for('login'))

        return render_template('reset_password.html', token=token)

    except mysql.connector.Error as err:
        app.logger.error(f"Database error during token validation/reset: {err}")
        if conn: conn.rollback()
        flash('A database error occurred. Please try again.', 'error')
        return redirect(url_for('login'))
    finally:
        if conn: conn.close()

@app.route('/logout')
def logout():
    session.clear()
    response = redirect(url_for('login'))
    response.set_cookie('bannerClosed', '', expires=0)
    return response

def count_files_in_folder(folder_path):
    count = 0
    try:
        for _, _, files in os.walk(folder_path):
            count += len(files)
    except FileNotFoundError:
        return 0
    return count

@app.route('/cancel_upload', methods=['POST'])
@login_required
def cancel_upload():
    user_id = session['user_id']
    user_dir = get_user_dir(user_id)

    data = request.get_data(as_text=True)
    if not data:
        return jsonify(success=False, message="No data received"), 400

    try:
        upload_info = json.loads(data)
        filename = upload_info.get('filename')
        current_dir = upload_info.get('current_dir', '')
        relative_path = upload_info.get('relativePath')

        if not filename:
            return jsonify(success=False, message="Filename missing"), 400

        secure_name = secure_filename(filename)

        if relative_path:
            path_parts = [secure_filename(p) for p in relative_path.split('/')]
            target_dir = os.path.join(user_dir, current_dir, *path_parts[:-1])
            final_path = os.path.join(target_dir, secure_name)
        else:
            final_path = os.path.join(user_dir, current_dir, secure_name)

        temp_path = f"{final_path}.part"

        if not os.path.abspath(temp_path).startswith(os.path.abspath(user_dir)):
            app.logger.warning(f"User {user_id} attempted invalid path deletion: {temp_path}")
            return jsonify(success=False, message="Invalid path"), 403

        if os.path.exists(temp_path):
            os.remove(temp_path)
            app.logger.info(f"Removed aborted upload part file for user {user_id}: {temp_path}")
            return jsonify(success=True)
        else:
            return jsonify(success=False, message="Part file not found"), 404

    except (json.JSONDecodeError, KeyError) as e:
        return jsonify(success=False, message=f"Invalid data format: {e}"), 400
    except Exception as e:
        app.logger.error(f"Error in /cancel_upload: {e}")
        return jsonify(success=False, message="Server error"), 500
    
@app.route('/shared-files')
@login_required
def shared_files():
    user_id = session['user_id']
    username = session.get('username', 'User')
    user_dir = get_user_dir(user_id)
    shares_list = []
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)

        c.execute('SELECT tier FROM users WHERE id = %s', (user_id,))
        user_data = c.fetchone()
        tier = user_data['tier'] if user_data else 'free'

        tier_details = {
            'free': {'plan_name': 'Free'},
            'basic': {'plan_name': 'Basic'},
            'plus': {'plan_name': 'Plus'},
            'pro': {'plan_name': 'Pro'},
            'admin': {'plan_name': 'Admin'}
        }
        details = tier_details.get(tier, tier_details['free'])

        c.execute(
            'SELECT token, item_path, created_at FROM shares WHERE user_id = %s AND (expires_at IS NULL OR expires_at > NOW()) ORDER BY created_at DESC',
            (user_id,)
        )
        shares = c.fetchall()

        if not shares:
            return render_template('shared_files.html', shares=[], username=username, details=details, tier=tier)

        share_tokens = [s['token'] for s in shares]
        format_strings = ','.join(['%s'] * len(share_tokens))
        c.execute(f"""
            SELECT
                share_token,
                COUNT(CASE WHEN interaction_type = 'view' THEN 1 END) as total_views,
                COUNT(CASE WHEN interaction_type = 'download' THEN 1 END) as total_downloads,
                COUNT(DISTINCT ip_address) as unique_visitors
            FROM share_analytics
            WHERE share_token IN ({format_strings})
            GROUP BY share_token
        """, tuple(share_tokens))
        
        analytics_results = c.fetchall()
        analytics_map = {res['share_token']: res for res in analytics_results}

        for share in shares:
            full_path = os.path.join(user_dir, share['item_path'])
            is_dir = os.path.isdir(full_path)
            
            share_analytics = analytics_map.get(share['token'], {
                'total_views': 0,
                'total_downloads': 0,
                'unique_visitors': 0
            })

            shares_list.append({
                'file_name': os.path.basename(share['item_path']),
                'file_icon': get_file_icon(share['item_path']),
                'share_date': share['created_at'].strftime('%b %d, %Y'),
                'share_link': generate_public_share_url(share['token']),
                'item_path': share['item_path'],
                'is_dir': is_dir,
                'token': share['token'],
                'total_views': share_analytics['total_views'],
                'total_downloads': share_analytics['total_downloads'],
                'unique_visitors': share_analytics['unique_visitors']
            })

    except mysql.connector.Error as err:
        app.logger.error(f"DB error fetching shared files: {err}")
        flash('Could not load your shared files.', 'error')
    finally:
        if conn:
            conn.close()
    
    return render_template('shared_files.html', shares=shares_list, username=username, details=details, tier=tier)


@app.route('/analytics/<token>')
@login_required
def analytics(token):
    user_id = session['user_id']
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)

        c.execute('SELECT user_id, item_path FROM shares WHERE token = %s', (token,))
        share = c.fetchone()
        if not share or share['user_id'] != user_id:
            flash('You do not have permission to view these analytics.', 'error')
            return redirect(url_for('shared_files'))
            
        file_name = os.path.basename(share['item_path'])
        file_icon = get_file_icon(file_name)
        share_url = url_for('show_shared_link', token=token, _external=True)

        c.execute("SELECT COUNT(*) as count FROM share_analytics WHERE share_token = %s AND interaction_type IN ('preview', 'download')", (token,))
        total_views = c.fetchone()['count'] or 0

        c.execute("SELECT COUNT(*) as count FROM share_analytics WHERE share_token = %s AND interaction_type = 'view'", (token,))
        total_page_views = c.fetchone()['count'] or 0

        c.execute("SELECT COUNT(DISTINCT ip_address) as count FROM share_analytics WHERE share_token = %s", (token,))
        unique_visitors = c.fetchone()['count'] or 0
        
        c.execute("SELECT COUNT(*) as count FROM share_analytics WHERE share_token = %s AND interaction_type = 'download'", (token,))
        total_downloads = c.fetchone()['count'] or 0

        c.execute("SELECT COUNT(*) as count FROM share_analytics WHERE share_token = %s AND interaction_type = 'preview'", (token,))
        total_previews = c.fetchone()['count'] or 0
        
        engagement_total = total_previews + total_downloads
        preview_perc = (total_previews / engagement_total * 100) if engagement_total > 0 else 0
        download_perc = (total_downloads / engagement_total * 100) if engagement_total > 0 else 0
        
        c.execute("""
            SELECT country, COUNT(*) as count 
            FROM share_analytics 
            WHERE share_token = %s AND country IS NOT NULL AND country != ''
            GROUP BY country 
            ORDER BY count DESC 
            LIMIT 5
        """, (token,))
        locations_raw = c.fetchall()
        
        locations = []
        if locations_raw:
            top_location_count = locations_raw[0]['count']
            
            for loc in locations_raw:
                db_country_identifier = loc['country']
                display_name = db_country_identifier
                flag_emoji = '🌍'

                try:
                    country_matches = pycountry.countries.search_fuzzy(db_country_identifier)
                    
                    if country_matches:
                        matched_country = country_matches[0]
                        display_name = matched_country.name
                        
                        flag_emoji = country_code_to_flag(matched_country.alpha_2)

                except Exception as e:
                    app.logger.warning(f"Could not find a country match for '{db_country_identifier}': {e}")

                locations.append({
                    'name': display_name,
                    'count': loc['count'],
                    'bar_width': (loc['count'] / top_location_count * 100) if top_location_count > 0 else 0,
                    'flag': flag_emoji
                })
            
        c.execute("""
            SELECT device_type, COUNT(DISTINCT ip_address) as count 
            FROM share_analytics 
            WHERE share_token = %s AND device_type IS NOT NULL
            GROUP BY device_type
        """, (token,))
        devices_raw = c.fetchall()

        total_devices = sum(d['count'] for d in devices_raw)
        devices = {
            'Desktop': {'count': 0, 'percentage': 0},
            'Mobile': {'count': 0, 'percentage': 0},
            'Tablet': {'count': 0, 'percentage': 0}
        }
        for dev in devices_raw:
            if dev['device_type'] in devices:
                devices[dev['device_type']]['count'] = dev['count']
                devices[dev['device_type']]['percentage'] = round((dev['count'] / total_devices * 100) if total_devices > 0 else 0)


        stats = {
            'file_name': file_name,
            'file_icon': file_icon,
            'share_url': share_url,
            'total_views': total_views,
            'total_page_views': total_page_views,
            'unique_visitors': unique_visitors,
            'total_downloads': total_downloads,
            'visitors_download_perc': round((total_downloads / unique_visitors * 100), 1) if unique_visitors > 0 else 0,
            'total_previews': total_previews,
            'preview_perc': preview_perc,
            'download_perc': download_perc,
            'locations': locations,
            'devices': devices
        }

        return render_template('analytics.html', **stats)
        
    except mysql.connector.Error as err:
        app.logger.error(f"DB error on analytics page: {err}")
        flash('Could not load analytics data.', 'error')
        return redirect(url_for('shared_files'))
    finally:
        if conn: conn.close()

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    try:
        user_id = session['user_id']
        # Optimization: Removed initial DB call here
        
        current_dir = request.form.get('current_dir', '')
        user_dir = get_user_dir(user_id)

        if '../' in current_dir or current_dir.startswith('/'):
            return jsonify({'success': False, 'message': 'invalid_path'})

        full_path = os.path.join(user_dir, current_dir)
        if not os.path.abspath(full_path).startswith(os.path.abspath(user_dir)):
            return jsonify({'success': False, 'message': 'invalid_path'})

        # --- COMBINED DB QUERY (Speed Limit + Quota) ---
        conn = None
        user_tier = 'free'
        speed_limit = app.config['FREE_USER_BANDWIDTH']
        
        try:
            conn = get_db_connection()
            c = conn.cursor(dictionary=True)
            c.execute('SELECT tier, quota, storage_used FROM users WHERE id = %s', (user_id,))
            user_data = c.fetchone()
            
            if user_data:
                user_tier = user_data['tier']
                quota = user_data['quota']
                user_used = user_data['storage_used'] if user_data['storage_used'] is not None else 0
                
                if user_tier == 'basic': speed_limit = app.config['BASIC_USER_BANDWIDTH']
                elif user_tier == 'plus': speed_limit = app.config['PLUS_USER_BANDWIDTH']
                elif user_tier == 'pro': speed_limit = app.config['PRO_USER_BANDWIDTH']
            else:
                quota = 0
                user_used = 0

        except mysql.connector.Error as err:
            app.logger.error(f"DB error during upload quota check: {err}")
            return jsonify({'success': False, 'message': 'database_error'})
        finally:
            if conn: conn.close()

        if user_tier != 'admin' and user_used >= quota:
             return jsonify({'success': False, 'message': 'storage_full', 'redirect': url_for('upgrade')})

        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'no_file_selected'})

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'no_file_selected'})

        filename = request.form.get('filename', file.filename)
        secure_name = secure_filename(filename)
        if not secure_name:
            return jsonify({'success': False, 'message': 'invalid_filename'})

        chunk_number = int(request.form.get('chunkNumber', 0))
        total_chunks = int(request.form.get('totalChunks', 1))
        relative_path_form = request.form.get('relative_path')
        overwrite_action = request.form.get('overwrite_action')
        folder_conflict_action = request.form.get('folder_conflict_action')
        is_first_file_of_batch = request.form.get('is_first_file_of_batch') == 'true'
        new_folder_name = request.form.get('new_folder_name')

        # --- Path Logic ---
        if relative_path_form:
            path_parts = [safe_path_component(p) for p in relative_path_form.split('/')]

            if is_first_file_of_batch and chunk_number == 0 and not folder_conflict_action:
                top_level_folder = path_parts[0]
                folder_path_to_check = os.path.join(full_path, top_level_folder)
                if os.path.isdir(folder_path_to_check):
                    suggested_path = get_unique_filename(folder_path_to_check)
                    return jsonify({
                        'success': False, 'message': 'folder_exists',
                        'foldername': top_level_folder, 'suggestion': os.path.basename(suggested_path)
                    })

            if folder_conflict_action == 'replace' and is_first_file_of_batch and chunk_number == 0:
                folder_to_delete = os.path.join(full_path, path_parts[0])
                if os.path.isdir(folder_to_delete):
                    deleted_size = get_folder_size(folder_to_delete)
                    shutil.rmtree(folder_to_delete)
                    try:
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute('UPDATE users SET storage_used = GREATEST(0, storage_used - %s) WHERE id = %s', (deleted_size, user_id))
                        conn.commit()
                        conn.close()
                    except: pass

            elif folder_conflict_action == 'upload_anyway' and new_folder_name:
                path_parts[0] = safe_path_component(new_folder_name)

            target_dir = os.path.join(full_path, *path_parts[:-1])
            final_path = os.path.join(target_dir, secure_name)
        else:
            target_dir = full_path
            final_path = os.path.join(target_dir, secure_name)

        os.makedirs(target_dir, exist_ok=True)
        temp_path = f"{final_path}.part"

        if not relative_path_form and chunk_number == 0 and os.path.exists(final_path) and not overwrite_action:
            return jsonify({'success': False, 'message': 'file_exists', 'filename': secure_name})

        # --- Write Chunk ---
        try:
            buffer_size = 4 * 1024 * 1024
            with open(temp_path, 'ab') as f:
                f.seek(chunk_number * app.config['UPLOAD_CHUNK'])
                
                # CRITICAL FIX: Skip throttling for chunk 0 so upload starts instantly
                should_throttle = speed_limit and chunk_number > 0
                
                while True:
                    data_chunk = file.stream.read(buffer_size)
                    if not data_chunk: break
                    f.write(data_chunk)
                    if should_throttle:
                        time.sleep(len(data_chunk) / speed_limit)

            # --- Finalize Upload ---
            if chunk_number == total_chunks - 1:
                should_scan = True
                scan_status = 'not_scanned'
                if relative_path_form:
                    folder_root = safe_path_component(relative_path_form.split("/")[0])
                    folder_full_path = os.path.join(full_path, folder_root)
                    if count_files_in_folder(folder_full_path) >= app.config['CLAMAV_MAX_FOLDER_ITEMS']:
                        should_scan = False
                        scan_status = 'skipped_folder_limit'

                if should_scan:
                    scan_result = scan_file_with_clamav(temp_path)
                else:
                    scan_result = {'status': scan_status}

                if scan_result['status'] == 'malicious':
                    os.remove(temp_path)
                    return jsonify({'success': False, 'message': 'virus_detected', 'filename': filename})
                elif scan_result['status'] == 'error':
                    os.remove(temp_path)
                    return jsonify({'success': False, 'message': 'virus_scan_error'})

                size_removed = 0
                if not relative_path_form:
                    if overwrite_action == 'upload_anyway': final_path = get_unique_filename(final_path)
                    if os.path.exists(final_path) and overwrite_action == 'replace':
                        size_removed = os.path.getsize(final_path)
                        os.remove(final_path)
                
                original_file_size = os.path.getsize(temp_path)

                try:
                    user_udek = get_user_udek(user_id)
                    encrypt_file_stream(temp_path, final_path, user_udek)
                except Exception as e:
                    if os.path.exists(temp_path): os.remove(temp_path)
                    return jsonify({'success': False, 'message': 'Encryption failed.'})
                finally:
                    if os.path.exists(temp_path): os.remove(temp_path)
                
                final_file_size = os.path.getsize(final_path)
                try:
                    conn = get_db_connection()
                    c = conn.cursor()
                    size_diff = final_file_size - size_removed
                    c.execute('UPDATE users SET storage_used = storage_used + %s WHERE id = %s', (size_diff, user_id))
                    conn.commit()
                    conn.close()
                except: pass

                if scan_result['status'] == 'skipped_large':
                     executor.submit(check_and_notify_large_upload, final_path, filename, user_id, original_file_size)
                elif scan_result['status'] == 'skipped_folder_limit':
                     folder_root = safe_path_component(relative_path_form.split("/")[0])
                     folder_full_path = os.path.join(user_dir, current_dir, folder_root)
                     executor.submit(check_and_notify_large_folder, folder_full_path, folder_root, user_id, count_files_in_folder(folder_full_path))

                return jsonify({'success': True, 'filename': os.path.basename(final_path), 'is_folder': bool(relative_path_form)})

            return jsonify({'success': True})

        except IOError as e:
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass
            return jsonify({'success': False, 'message': f'io_error: {str(e)}'})

    except Exception as e:
        app.logger.error(f"Upload error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


def check_and_notify_large_upload(file_path, filename, user_id, file_size):
    try:
        LARGE_FILE_THRESHOLD = 50 * 1024 * 1024
        if file_size > LARGE_FILE_THRESHOLD:
            app.logger.info(f"User {user_id} uploaded large file: {filename} ({file_size} bytes)")
    except Exception as e:
        app.logger.error(f"Error in large file notification: {e}")

def check_and_notify_large_folder(folder_path, folder_name, user_id, file_count):
    try:
        LARGE_FOLDER_THRESHOLD = 200 * 1024 * 1024
        LARGE_FOLDER_FILE_COUNT = 100
        folder_size = get_folder_size(folder_path)

        if folder_size > LARGE_FOLDER_THRESHOLD or file_count > LARGE_FOLDER_FILE_COUNT:
            app.logger.info(f"User {user_id} uploaded large folder: {folder_name} ({folder_size} bytes, {file_count} files)")
    except Exception as e:
        app.logger.error(f"Error in large folder notification: {e}")

def process_folder_upload_parallel(folder_path, target_dir, speed_limit=None):
    import concurrent.futures

    def process_file(file_info):
        file_path, relative_path = file_info
        target_path = os.path.join(target_dir, relative_path)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        try:
            shutil.copy2(file_path, target_path)
            if speed_limit:
                file_size = os.path.getsize(file_path)
                time.sleep(file_size / speed_limit)
            return True
        except Exception as e:
            app.logger.error(f"Error copying file {file_path}: {e}")
            return False

    file_list = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, folder_path)
            file_list.append((full_path, rel_path))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(process_file, file_list))

    return all(results)


@app.route('/download/<path:filename>')
@login_required
def download(filename):
    user_id = session['user_id']
    user_dir = get_user_dir(user_id)
    full_path = os.path.join(user_dir, filename)

    if not os.path.abspath(full_path).startswith(os.path.abspath(user_dir)) or not os.path.isfile(full_path):
        abort(404)

    user_udek = get_user_udek(user_id)
    speed_limit = get_user_speed_limit(user_id)
    
    decrypted_stream = generate_decrypted_stream(full_path, user_udek, speed_limit)
    
    response = Response(decrypted_stream, mimetype='application/octet-stream')
    response.headers['Content-Disposition'] = f'attachment; filename="{os.path.basename(filename)}"'
    response.headers['Content-Length'] = get_file_size(full_path)
    return response

@app.route('/download_folder/<path:folder_path>')
@login_required
def download_folder(folder_path):
    user_id = session['user_id']
    user_dir = get_user_dir(user_id)
    full_path = os.path.join(user_dir, folder_path)

    if not os.path.abspath(full_path).startswith(os.path.abspath(user_dir)) or not os.path.isdir(full_path):
        abort(404)

    user_udek = get_user_udek(user_id)
    speed_limit = get_user_speed_limit(user_id)
    archive_format = get_best_archive_format(request.headers.get('User-Agent', ''))

    temp_dir = tempfile.mkdtemp()

    try:
        decrypted_folder_path = os.path.join(temp_dir, os.path.basename(folder_path))
        os.makedirs(decrypted_folder_path)

        for root, _, files in os.walk(full_path):
            for file in files:
                encrypted_file_path = os.path.join(root, file)
                relative_path = os.path.relpath(encrypted_file_path, full_path)
                decrypted_file_path = os.path.join(decrypted_folder_path, relative_path)

                os.makedirs(os.path.dirname(decrypted_file_path), exist_ok=True)

                with open(decrypted_file_path, 'wb') as f_out:
                    for chunk in generate_decrypted_stream(encrypted_file_path, user_udek):
                        f_out.write(chunk)

        basename = os.path.basename(folder_path.rstrip('/'))

        if archive_format == "zip":
            command = ['zip', '-r', '-0', '-q', '-', '.']
            mimetype, ext = "application/zip", ".zip"
            proc = subprocess.Popen(
                command,
                cwd=decrypted_folder_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        else:
            cmd = f"tar -cf - {shlex.quote(basename)} | zstd -6 -T1 -"
            mimetype, ext = "application/zstd", ".tar.zst"
            proc = subprocess.Popen(cmd, shell=True, cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        def stream_and_cleanup():
            try:
                while True:
                    chunk = proc.stdout.read(app.config['CHUNK_SIZE'])
                    if not chunk: break
                    yield chunk
                    if speed_limit: time.sleep(len(chunk) / speed_limit)
            finally:
                proc.kill()
                shutil.rmtree(temp_dir)

        response = Response(stream_and_cleanup(), mimetype=mimetype)
        response.headers['Content-Disposition'] = f"attachment; filename={basename}{ext}"
        return response

    except Exception as e:
        app.logger.error(f"Error during folder download: {e}")
        shutil.rmtree(temp_dir)
        abort(500)

@app.route('/preview/<path:filename>')
@login_required
def preview_file(filename):
    user_id = session['user_id']
    user_dir = get_user_dir(user_id)
    full_path = os.path.join(user_dir, filename)

    if not os.path.abspath(full_path).startswith(os.path.abspath(user_dir)):
        abort(400, "Invalid path")

    return _serve_preview(full_path, user_id, filename)

def _serve_preview(full_path, user_id_for_key, relative_filename):
    if not os.path.exists(full_path):
        abort(404, "File not found")

    try:
        udek = get_user_udek(user_id_for_key)
    except ValueError:
        abort(500, "Could not retrieve decryption key.")

    fn_lower = relative_filename.lower()

    archive_extensions = ('.zip', '.rar', '.7z', '.tar', '.gz', '.tgz', '.bz2', '.xz', '.zst', '.tar.zst')
    if fn_lower.endswith(archive_extensions):
        return jsonify({'type': 'error', 'message': 'Live preview is not available for encrypted archives.'})

    office_extensions = ('.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp')
    if fn_lower.endswith(office_extensions) and request.args.get('convert') == 'pdf':
        temp_decrypted_file = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(relative_filename)[1]) as temp_decrypted_file:
                for chunk in generate_decrypted_stream(full_path, udek):
                    temp_decrypted_file.write(chunk)
            
            with tempfile.TemporaryDirectory() as temp_dir:
                cmd = ['libreoffice', '--headless', '--convert-to', 'pdf', '--outdir', temp_dir, temp_decrypted_file.name]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)

                if result.returncode != 0:
                    raise RuntimeError(f"LibreOffice conversion failed: {result.stderr.decode()}")

                pdf_files = [f for f in os.listdir(temp_dir) if f.lower().endswith('.pdf')]
                if not pdf_files:
                    raise FileNotFoundError("No PDF was generated by LibreOffice")

                return send_from_directory(temp_dir, pdf_files[0], mimetype='application/pdf')
        except Exception as e:
            app.logger.error(f"Encrypted office conversion error for '{relative_filename}': {str(e)}")
            abort(500)
        finally:
            if temp_decrypted_file and os.path.exists(temp_decrypted_file.name):
                os.remove(temp_decrypted_file.name)

    mime_type, _ = guess_type(full_path)
    return Response(generate_decrypted_stream(full_path, udek), mimetype=mime_type or "application/octet-stream")

@app.route('/bulk_download', methods=['POST'])
@login_required
def bulk_download():
    user_id = session['user_id']
    paths = request.form.getlist('paths[]')
    user_dir = get_user_dir(user_id)

    if not paths:
        return "No files selected", 400

    user_udek = get_user_udek(user_id)
    speed_limit = get_user_speed_limit(user_id)
    archive_format = get_best_archive_format(request.headers.get('User-Agent', ''))
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        for item_rel_path in paths:
            item_full_path = os.path.join(user_dir, item_rel_path)
            if not os.path.abspath(item_full_path).startswith(os.path.abspath(user_dir)):
                continue

            decrypted_item_path = os.path.join(temp_dir, item_rel_path)

            if os.path.isdir(item_full_path):
                os.makedirs(decrypted_item_path, exist_ok=True)
                for root, _, files in os.walk(item_full_path):
                    for file in files:
                        enc_file = os.path.join(root, file)
                        rel_path = os.path.relpath(enc_file, item_full_path)
                        dec_file = os.path.join(decrypted_item_path, rel_path)
                        os.makedirs(os.path.dirname(dec_file), exist_ok=True)
                        with open(dec_file, 'wb') as f_out:
                            for chunk in generate_decrypted_stream(enc_file, user_udek):
                                f_out.write(chunk)
            elif os.path.isfile(item_full_path):
                os.makedirs(os.path.dirname(decrypted_item_path), exist_ok=True)
                with open(decrypted_item_path, 'wb') as f_out:
                    for chunk in generate_decrypted_stream(item_full_path, user_udek):
                        f_out.write(chunk)

        archive_basename = f"cloudx_{int(time.time())}"
        
        if archive_format == "zip":
            command = ['zip', '-r', '-0', '-q', '-', '.']
            mimetype, ext = "application/zip", ".zip"
            proc = subprocess.Popen(
                command,
                cwd=temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        else:
            quoted_paths = ' '.join([shlex.quote(p) for p in paths])
            cmd = f"tar -cf - {quoted_paths} | zstd -6 -T1 -"
            mimetype, ext = "application/zstd", ".tar.zst"
            proc = subprocess.Popen(cmd, shell=True, cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        def stream_and_cleanup():
            try:
                while True:
                    chunk = proc.stdout.read(app.config['CHUNK_SIZE'])
                    if not chunk: break
                    yield chunk
                    if speed_limit: time.sleep(len(chunk) / speed_limit)
            finally:
                proc.kill()
                shutil.rmtree(temp_dir)

        response = Response(stream_and_cleanup(), mimetype=mimetype)
        response.headers['Content-Disposition'] = f"attachment; filename={archive_basename}{ext}"
        return response

    except Exception as e:
        app.logger.error(f"Error during bulk download: {e}")
        shutil.rmtree(temp_dir)
        abort(500)

@app.route('/delete', methods=['POST'])
@login_required
def delete():
    user_id = session['user_id']
    item_path = request.form.get('item_path')
    user_dir = get_user_dir(user_id)
    full_path = os.path.join(user_dir, item_path)

    if not os.path.abspath(full_path).startswith(os.path.abspath(user_dir)):
        flash("Invalid path for deletion.")
        return redirect(url_for('mycloud', path=''))

    try:
        if os.path.exists(full_path):
            # FAST FIX: Calculate size before deleting to update DB
            size_freed = 0
            if os.path.isdir(full_path):
                size_freed = get_folder_size(full_path)
                shutil.rmtree(full_path)
            else:
                size_freed = os.path.getsize(full_path)
                os.remove(full_path)
            
            # Update DB
            conn = None
            try:
                conn = get_db_connection()
                c = conn.cursor()
                # Ensure we don't go below 0
                c.execute('UPDATE users SET storage_used = GREATEST(0, storage_used - %s) WHERE id = %s', (size_freed, user_id))
                conn.commit()
            except Exception as e:
                app.logger.error(f"DB Error updating quota on delete: {e}")
            finally:
                if conn: conn.close()

            flash('Item deleted successfully')
        else:
            flash('Item not found')
    except Exception as e:
        flash(f'Error deleting item: {str(e)}')

    return redirect(url_for('mycloud', path=os.path.dirname(item_path)))

@app.route('/mkdir', methods=['POST'])
@login_required
def mkdir():
    user_id = session['user_id']
    current_dir = request.form.get('current_dir', '')
    dirname = request.form.get('dirname')

    if not dirname:
        flash('Directory name cannot be empty')
        return redirect(url_for('mycloud', path=current_dir))

    user_dir = get_user_dir(user_id)
    safe_dirname = safe_path_component(dirname)
    full_path = os.path.join(user_dir, current_dir, safe_dirname)

    if not os.path.abspath(full_path).startswith(os.path.abspath(user_dir)):
        flash("Invalid path for directory creation.")
        return redirect(url_for('mycloud', path=current_dir))

    try:
        os.makedirs(full_path, exist_ok=True)
        flash('Directory created successfully')
    except Exception as e:
        flash(f'Error creating directory: {str(e)}')

    return redirect(url_for('mycloud', path=current_dir))

@app.route('/rename_item', methods=['POST'])
@login_required
def rename_item():
    user_id = session['user_id']
    current_path = request.form.get('current_path')
    current_dir = request.form.get('current_dir', '')
    new_name_from_form = request.form.get('new_name')

    if not new_name_from_form:
        flash('New name cannot be empty')
        return redirect(url_for('mycloud', path=current_dir))

    user_dir = get_user_dir(user_id)
    old_full_path = os.path.join(user_dir, current_path)

    if not os.path.exists(old_full_path) or not os.path.abspath(old_full_path).startswith(os.path.abspath(user_dir)):
        flash("Invalid source path for renaming.")
        return redirect(url_for('mycloud', path=current_dir))

    if os.path.isfile(old_full_path):
        _ , original_extension = os.path.splitext(os.path.basename(current_path))
        final_new_name = new_name_from_form + original_extension
    else:
        final_new_name = new_name_from_form

    new_full_path = os.path.join(os.path.dirname(old_full_path), secure_filename(final_new_name))

    if not os.path.abspath(new_full_path).startswith(os.path.abspath(user_dir)):
        flash("Invalid destination path for renaming.")
        return redirect(url_for('mycloud', path=current_dir))

    try:
        if os.path.exists(new_full_path):
            flash('An item with that name already exists in the target location')
        else:
            os.rename(old_full_path, new_full_path)
            flash('Item renamed successfully')
    except Exception as e:
        flash(f'Error renaming item: {str(e)}')

    return redirect(url_for('mycloud', path=current_dir))

@app.route('/move_item', methods=['POST'])
@login_required
def move_item():
    user_id = session['user_id']
    current_path = request.form.get('current_path')
    target_folder = request.form.get('target_folder', '').strip()
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    user_dir = get_user_dir(user_id)
    source_path = os.path.join(user_dir, current_path)
    current_dir_ui = os.path.dirname(current_path)

    if not os.path.exists(source_path) or not os.path.abspath(source_path).startswith(os.path.abspath(user_dir)):
        error = 'Invalid source path.'
        return jsonify(success=False, error=error) if is_ajax else (flash(error), redirect(url_for('mycloud', path=current_dir_ui)))

    if target_folder in ("", "ROOT"):
        target_path = os.path.join(user_dir, os.path.basename(source_path))
    else:
        target_dir_full_path = os.path.join(user_dir, target_folder)
        if not os.path.isdir(target_dir_full_path) or not os.path.abspath(target_dir_full_path).startswith(os.path.abspath(user_dir)):
            error = 'Invalid or non-existent target folder.'
            return jsonify(success=False, error=error) if is_ajax else (flash(error), redirect(url_for('mycloud', path=current_dir_ui)))
        target_path = os.path.join(target_dir_full_path, os.path.basename(source_path))

    if os.path.isdir(source_path) and os.path.realpath(os.path.dirname(target_path)).startswith(os.path.realpath(source_path)):
        error = 'Cannot move a folder into itself or its subfolder.'
        return jsonify(success=False, error=error) if is_ajax else (flash(error), redirect(url_for('mycloud', path=current_dir_ui)))

    if os.path.exists(target_path):
        error = 'An item with that name already exists in the target location.'
        return jsonify(success=False, error=error) if is_ajax else (flash(error), redirect(url_for('mycloud', path=current_dir_ui)))

    try:
        shutil.move(source_path, target_path)
        success_msg = 'Item moved successfully.'
        if is_ajax: return jsonify(success=True, message=success_msg)
        flash(success_msg)
        return redirect(url_for('mycloud', path=current_dir_ui))
    except Exception as e:
        error = f'Error moving item: {str(e)}'
        if is_ajax: return jsonify(success=False, error=error)
        flash(error)
        return redirect(url_for('mycloud', path=current_dir_ui))

@app.route('/account')
@login_required
def account():
    user_id = session['user_id']
    username = session['username']
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        # FAST FIX: Select storage_used
        c.execute('SELECT email, tier, quota, storage_used FROM users WHERE id = %s', (user_id,))
        user = c.fetchone()

        if not user:
            flash("User not found.")
            return redirect(url_for('login'))
        
        # FAST FIX: Use DB value
        user_used = user['storage_used'] if user['storage_used'] is not None else 0

        tier_details = {
            'free': {'plan_name': 'Free', 'storage_capacity': '5 GB', 'upload_limit': '1 GB', 'speed': 'Standard', 'ads': True, 'file_sharing': False},
            'basic': {'plan_name': 'Basic', 'storage_capacity': '50 GB', 'upload_limit': '5 GB', 'speed': '2x Faster', 'ads': False, 'file_sharing': False},
            'plus': {'plan_name': 'Plus', 'storage_capacity': '200 GB', 'upload_limit': '20 GB', 'speed': '3x Faster', 'ads': False, 'file_sharing': False},
            'pro': {'plan_name': 'Pro', 'storage_capacity': '500 GB', 'upload_limit': '50 GB', 'speed': '5x Faster', 'ads': False, 'file_sharing': True},
            'admin': {'plan_name': 'Admin', 'storage_capacity': 'Unlimited', 'upload_limit': 'Unlimited', 'speed': 'Unlimited', 'ads': False, 'file_sharing': True}
        }
        details = tier_details.get(user['tier'], tier_details['free'])
        
        quota = user['quota']
        percent_used = min(round(float(user_used) / float(quota) * 100, 2), 100) if quota > 0 else 0
        
        if user['tier'] == 'admin':
            quota = 0
            percent_used = 0

        return render_template('account.html', username=username, email=user['email'],
                               tier=user['tier'],
                               details=details, used=user_used, quota=quota, percent_used=percent_used)
    except mysql.connector.Error as err:
        app.logger.error(f"Database error on account page: {err}")
        return redirect(url_for('mycloud'))
    finally:
        if conn: conn.close()

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    user_id = session['user_id']
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if new_password != confirm_password:
        flash('New passwords do not match.')
        return redirect(url_for('account'))
    if len(new_password) < 8:
        flash('New password must be at least 8 characters long.')
        return redirect(url_for('account'))

    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT password FROM users WHERE id = %s', (user_id,))
        user_record = c.fetchone()

        if user_record and check_password_hash(user_record[0], current_password):
            c.execute('UPDATE users SET password = %s WHERE id = %s', (generate_password_hash(new_password), user_id))
            conn.commit()
            flash('Password updated successfully.')
        else:
            flash('Incorrect current password.')
    except mysql.connector.Error as err:
        if conn: conn.rollback()
        flash('An error occurred while changing your password.')
    finally:
        if conn: conn.close()
    return redirect(url_for('account'))

@app.route('/share', methods=['POST'])
@login_required
def create_share_link():
    user_id = session['user_id']
    item_path = request.form.get('path')
    expiry_hours = int(request.form.get('expiry', 24))
    password = request.form.get('password')

    permissions = []
    if request.form.get('allow_preview') == 'true':
        permissions.append('preview')
    if request.form.get('allow_download') == 'true':
        permissions.append('download')

    if not permissions:
        return jsonify({'success': False, 'message': 'At least one permission (preview or download) must be selected.'})

    permissions_str = ",".join(permissions)

    expires_at = None
    if expiry_hours > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)

    password_to_store = password or None

    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()

        c.execute('SELECT token FROM shares WHERE user_id = %s AND item_path = %s', (user_id, item_path))
        existing_share = c.fetchone()

        reused = False
        if existing_share:
            token = existing_share[0]
            c.execute(
                'UPDATE shares SET expires_at = %s, permissions = %s, password_hash = %s, username = %s WHERE token = %s',
                (expires_at, permissions_str, password_to_store, session['username'], token)
            )
            reused = True
        else:
            token = secrets.token_urlsafe(16)
            c.execute(
                'INSERT INTO shares (token, user_id, username, item_path, expires_at, permissions, password_hash) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (token, user_id, session['username'], item_path, expires_at, permissions_str, password_to_store)
            )

        conn.commit()
        share_url = generate_public_share_url(token)
        return jsonify({'success': True, 'url': share_url, 'reused': reused})

    except mysql.connector.Error as err:
        app.logger.error(f"Error creating share link: {err}")
        if conn: conn.rollback()
        return jsonify({'success': False, 'message': 'Database error occurred.'})
    finally:
        if conn: conn.close()

@app.route('/delete_share_link', methods=['POST'])
@login_required
def delete_share_link():
    user_id = session['user_id']
    item_path = request.form.get('path')

    if not item_path:
        return jsonify({'success': False, 'message': 'Item path is missing.'})

    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('DELETE FROM shares WHERE user_id = %s AND item_path = %s', (user_id, item_path))
        conn.commit()

        if c.rowcount > 0:
            return jsonify({'success': True, 'message': 'Share link deleted successfully.'})
        else:
            return jsonify({'success': False, 'message': 'No matching share link found to delete.'})

    except mysql.connector.Error as err:
        app.logger.error(f"Error deleting share link: {err}")
        if conn: conn.rollback()
        return jsonify({'success': False, 'message': 'A database error occurred.'})
    finally:
        if conn: conn.close()

def _get_shared_item_details(token):
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute('SELECT * FROM shares WHERE token = %s', (token,))
        share = c.fetchone()
        if not share:
            return None

        if share['expires_at']:
            expires_at = share['expires_at']
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            share['expires_at'] = expires_at

            if expires_at < datetime.now(timezone.utc):
                return None

        user_dir = get_user_dir(share['user_id']) # <-- THIS NOW WORKS FOR PUBLIC USER
        full_path = os.path.join(user_dir, share['item_path'])

        if not os.path.exists(full_path) or not os.path.abspath(full_path).startswith(os.path.abspath(user_dir)):
             app.logger.warning(f"Share path mismatch or file not found for token {token}. Path: {full_path}")
             return None

        share['full_path'] = full_path
        return share
    except mysql.connector.Error as err:
        app.logger.error(f"DB error fetching share link {token}: {err}")
        return None
    finally:
        if conn: conn.close()

@app.route('/get_share_details', methods=['POST'])
@login_required
def get_share_details():
    user_id = session['user_id']
    item_path = request.form.get('path')

    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute('SELECT token, expires_at, permissions, password_hash FROM shares WHERE user_id = %s AND item_path = %s', (user_id, item_path))
        share = c.fetchone()
        if share:
            expiry_hours = "0"
            if share['expires_at']:
                expires_at = share['expires_at']
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)
                if expires_at > now:
                    delta = expires_at - now
                    hours_left = delta.total_seconds() / 3600
                    if hours_left > 0:
                        options = [1, 24, 168, 720]
                        closest_option = min(options, key=lambda x: abs(x - hours_left))
                        expiry_hours = str(closest_option)

            permissions = share['permissions'].split(',')
            access = 'both'
            if 'preview' in permissions and 'download' not in permissions:
                access = 'preview'
            elif 'download' in permissions and 'preview' not in permissions:
                access = 'download'

            return jsonify({
                'success': True,
                'exists': True,
                'url': generate_public_share_url(share['token']),
                'expiry': expiry_hours,
                'access': access,
                'has_password': bool(share['password_hash']),
                'password': share['password_hash']
            })
        else:
            return jsonify({'success': True, 'exists': False})
    except mysql.connector.Error as err:
        app.logger.error(f"DB error fetching share details: {err}")
        return jsonify({'success': False, 'message': 'Database error.'})
    finally:
        if conn: conn.close()

@app.route('/shared/<token>')
def show_shared_link(token):
    ip = get_client_ip(request)
    ua = request.headers.get('User-Agent', '')
    executor.submit(log_share_interaction, token, 'view', ip, ua)
    
    share = _get_shared_item_details(token)
    if not share:
        return render_template('sharedgone.html'), 404

    if share['password_hash']:
        unlocked_shares = session.get('unlocked_shares', [])
        if token not in unlocked_shares:
            return render_template('protected.html', token=token, file_name=os.path.basename(share['item_path']))

    is_dir = os.path.isdir(share['full_path'])
    file_size = get_folder_size(share['full_path']) if is_dir else get_file_size(share['full_path'])

    owner_email = None
    owner_username = 'Unknown'
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT email, username FROM users WHERE id = %s", (share['user_id'],))
        row = c.fetchone()
        if row:
            owner_email = row[0]
            owner_username = row[1]
    except Exception as e:
        app.logger.error(f"Error fetching owner email: {e}")
    finally:
        if conn:
            conn.close()

    return render_template('share.html',
        token=token,
        file_name=os.path.basename(share['item_path']),
        file_size=file_size,
        file_icon=get_file_icon(share['item_path']),
        upload_date=share['created_at'],
        owner_email=owner_email or owner_username,
        expires_at=share['expires_at'],
        permissions=share['permissions'].split(','),
        is_dir=is_dir
    )

@app.route('/shared_download/<token>')
def shared_download(token):
    ip = get_client_ip(request)
    ua = request.headers.get('User-Agent', '')
    executor.submit(log_share_interaction, token, 'download', ip, ua)

    share = _get_shared_item_details(token)

    if not share or 'download' not in share['permissions']:
        abort(403)

    if share['password_hash'] and token not in session.get('unlocked_shares', []):
        abort(403, "Password required for download.")

    if os.path.isfile(share['full_path']):
        owner_udek = get_user_udek(share['user_id'])
        decrypted_stream = generate_decrypted_stream(share['full_path'], owner_udek, speed_limit=2*1024*1024)

        filename = os.path.basename(share['item_path'])
        mime_type, _ = guess_type(share['full_path'])

        response = Response(decrypted_stream, mimetype=mime_type or 'application/octet-stream')
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Content-Length'] = get_file_size(share['full_path'])
        return response

    user_agent = request.headers.get('User-Agent', '')
    archive_format = get_best_archive_format(user_agent)
    owner_udek = get_user_udek(share['user_id'])
    speed_limit = 2 * 1024 * 1024
    temp_dir = tempfile.mkdtemp()

    try:
        decrypted_folder_path = os.path.join(temp_dir, os.path.basename(share['item_path']))
        os.makedirs(decrypted_folder_path)
        for root, _, files in os.walk(share['full_path']):
            for file in files:
                enc_file = os.path.join(root, file)
                rel_path = os.path.relpath(enc_file, share['full_path'])
                dec_file = os.path.join(decrypted_folder_path, rel_path)
                os.makedirs(os.path.dirname(dec_file), exist_ok=True)
                with open(dec_file, 'wb') as f_out:
                    for chunk in generate_decrypted_stream(enc_file, owner_udek):
                        f_out.write(chunk)

        basename = os.path.basename(share['item_path'].rstrip('/'))

        if archive_format == "zip":
            command = ['zip', '-r', '-0', '-q', '-', '.']
            mimetype, ext = "application/zip", ".zip"
            proc = subprocess.Popen(
                command,
                cwd=decrypted_folder_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        else:
            cmd = f"tar -cf - {shlex.quote(basename)} | zstd -6 -T1 -"
            mimetype, ext = "application/zstd", ".tar.zst"
            proc = subprocess.Popen(cmd, shell=True, cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        def stream_and_cleanup():
            try:
                while True:
                    chunk = proc.stdout.read(app.config['CHUNK_SIZE'])
                    if not chunk: break
                    yield chunk
                    if speed_limit: time.sleep(len(chunk) / speed_limit)
            finally:
                proc.kill()
                shutil.rmtree(temp_dir)

        response = Response(stream_and_cleanup(), mimetype=mimetype)
        response.headers['Content-Disposition'] = f"attachment; filename={basename}{ext}"
        return response
    except Exception as e:
        app.logger.error(f"Error during shared folder download: {e}")
        shutil.rmtree(temp_dir)
        abort(500)

@app.route('/shared_preview/<token>')
def shared_preview(token):
    ip = get_client_ip(request)
    ua = request.headers.get('User-Agent', '')
    executor.submit(log_share_interaction, token, 'preview', ip, ua)
    
    share = _get_shared_item_details(token)
    if not share:
        abort(404, "Link invalid or expired.")
    if 'preview' not in share['permissions']:
        abort(403, "Preview not permitted for this link.")

    if share['password_hash'] and token not in session.get('unlocked_shares', []):
        abort(403, "Password required for preview.")
    
    return _serve_preview(share['full_path'], share['user_id'], share['item_path'])

@app.route('/shared/<token>/verify', methods=['POST'])
def verify_share_password(token):
    password = request.form.get('password')
    share = _get_shared_item_details(token)

    if not share or not share['password_hash']:
        return redirect(url_for('show_shared_link', token=token))

    if share['password_hash'] == password:
        if 'unlocked_shares' not in session:
            session['unlocked_shares'] = []
        
        if token not in session['unlocked_shares']:
            session['unlocked_shares'].append(token)
            session.modified = True
            
        return redirect(url_for('show_shared_link', token=token))
    else:
        flash('Incorrect password. Please try again.', 'error')
        return render_template('protected.html', token=token, file_name=os.path.basename(share['item_path']))

def _delete_user_account(user_id_to_delete):
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)

        c.execute('SELECT paypal_subscription_id, email, tier FROM users WHERE id = %s', (user_id_to_delete,))
        user = c.fetchone()
        
        if not user:
            app.logger.error(f"Attempted to delete non-existent user ID: {user_id_to_delete}")
            return False
        
        # Prevent deletion of public user
        if user.get('tier') == 'public':
            app.logger.error(f"CRITICAL: Attempt to delete the 'public' user (ID: {user_id_to_delete}) was blocked.")
            return False

        subscription_id = user.get('paypal_subscription_id')

        if subscription_id and subscription_id.startswith('I-'):
            access_token = get_paypal_access_token()
            if not access_token:
                app.logger.error(f"Could not get PayPal token to cancel sub for user {user_id_to_delete}")
                return False

            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            }
            base_url = "https://api-m.sandbox.paypal.com" if app.config['PAYPAL_ENVIRONMENT'] == 'sandbox' else "https://api-m.paypal.com"
            url = f"{base_url}/v1/billing/subscriptions/{subscription_id}/cancel"
            body = {'reason': 'User account deleted from service.'}
            response = requests.post(url, headers=headers, json=body)

            if response.status_code != 204:
                app.logger.error(f"PayPal cancellation failed for user {user_id_to_delete} during account deletion: {response.text}")
                return False
            
            app.logger.info(f"Successfully cancelled PayPal subscription {subscription_id} for user {user_id_to_delete}.")

        c.execute('DELETE FROM users WHERE id = %s', (user_id_to_delete,))
        conn.commit()

        user_dir = get_user_dir(user_id_to_delete) # This will correctly get /user_files/<id>
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
            app.logger.info(f"Successfully deleted user data directory for former user {user_id_to_delete}: {user_dir}")

        app.logger.info(f"Account for user {user.get('email')} (ID: {user_id_to_delete}) has been permanently deleted.")
        return True

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Network error during PayPal cancellation for user {user_id_to_delete}: {e}")
        if conn: conn.rollback()
        return False
    except Exception as e:
        if conn: conn.rollback()
        app.logger.error(f"General error during account deletion for user {user_id_to_delete}: {str(e)}")
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    user_id = session['user_id']
    
    if _delete_user_account(user_id):
        session.clear()
        flash('Your account, subscription, and all associated data have been permanently deleted.', 'success')
        return redirect(url_for('login'))
    else:
        flash('An unexpected error occurred while deleting your account. Please contact support.', 'error')
        return redirect(url_for('account'))

# app.py

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)

        # --- STATS FOR REGISTERED USERS ---
        c.execute("SELECT COUNT(*) as c FROM users WHERE tier NOT IN ('admin', 'public')")
        total_users = c.fetchone()['c'] or 0
        c.execute("SELECT COUNT(*) as c FROM users WHERE tier = 'pro'")
        pro_users = c.fetchone()['c'] or 0
        c.execute("SELECT COUNT(*) as c FROM users WHERE tier = 'plus'")
        plus_users = c.fetchone()['c'] or 0
        c.execute("SELECT COUNT(*) as c FROM users WHERE tier = 'basic'")
        basic_users = c.fetchone()['c'] or 0
        c.execute("SELECT COUNT(*) as c FROM users WHERE tier = 'free'")
        free_users = c.fetchone()['c'] or 0
        
        c.execute("SELECT id FROM users WHERE tier NOT IN ('admin', 'public')")
        all_user_ids = [row['id'] for row in c.fetchall()]
        total_storage_used = sum(get_folder_size(get_user_dir(user_id)) for user_id in all_user_ids)
        
        # Add public storage
        public_user_id = os.environ.get('PUBLIC_UPLOADER_USER_ID')
        public_storage_used = 0
        if public_user_id:
            public_storage_used = get_folder_size(get_user_dir(public_user_id))

        stats = {
            'total_users': total_users,
            'total_storage': total_storage_used,
            'public_storage': public_storage_used, # <-- ADDED
            'pro_users': pro_users,
            'plus_users': plus_users,
            'basic_users': basic_users,
            'free_users': free_users
        }

        # Registered Users Geographic Distribution
        c.execute("""
            SELECT country, COUNT(*) as count
            FROM users
            WHERE country IS NOT NULL AND country != '' AND tier NOT IN ('admin', 'public')
            GROUP BY country
            ORDER BY count DESC
            LIMIT 5
        """)
        locations_raw = c.fetchall()
        locations = []
        if locations_raw:
            top_location_count = locations_raw[0]['count']
            for loc in locations_raw:
                db_country_identifier = loc['country']
                display_name = db_country_identifier
                flag_emoji = '🌍'
                try:
                    country_matches = pycountry.countries.search_fuzzy(db_country_identifier)
                    if country_matches:
                        matched_country = country_matches[0]
                        display_name = matched_country.name
                        flag_emoji = country_code_to_flag(matched_country.alpha_2)
                except Exception:
                    pass
                
                locations.append({
                    'name': display_name,
                    'count': loc['count'],
                    'bar_width': (loc['count'] / top_location_count * 100) if top_location_count > 0 else 0,
                    'flag': flag_emoji
                })

        # --- WEBSITE VISITOR ANALYTICS ---
        visitor_stats = {}
        period = request.args.get('period')
        period_title = "All Time" 
        
        try:
            # Get total counts regardless of period
            c.execute("SELECT COUNT(DISTINCT ip_address) as c FROM visitor_analytics WHERE visit_timestamp >= NOW() - INTERVAL 24 HOUR")
            visitor_stats['last_24h'] = c.fetchone()['c'] or 0
            c.execute("SELECT COUNT(DISTINCT ip_address) as c FROM visitor_analytics WHERE visit_timestamp >= NOW() - INTERVAL 7 DAY")
            visitor_stats['last_7d'] = c.fetchone()['c'] or 0
            c.execute("SELECT COUNT(DISTINCT ip_address) as c FROM visitor_analytics WHERE visit_timestamp >= NOW() - INTERVAL 14 DAY")
            visitor_stats['last_14d'] = c.fetchone()['c'] or 0
            c.execute("SELECT COUNT(DISTINCT ip_address) as c FROM visitor_analytics WHERE visit_timestamp >= NOW() - INTERVAL 30 DAY")
            visitor_stats['last_30d'] = c.fetchone()['c'] or 0
            c.execute("SELECT COUNT(DISTINCT ip_address) as c FROM visitor_analytics")
            visitor_stats['all_time'] = c.fetchone()['c'] or 0

            # Build WHERE clause for location query
            where_clause = "country IS NOT NULL AND country != ''"
            period_map = {
                '24h': ("visit_timestamp >= NOW() - INTERVAL 24 HOUR", "Last 24 Hours"),
                '7d': ("visit_timestamp >= NOW() - INTERVAL 7 DAY", "Last 7 Days"),
                '14d': ("visit_timestamp >= NOW() - INTERVAL 14 DAY", "Last 14 Days"),
                '30d': ("visit_timestamp >= NOW() - INTERVAL 30 DAY", "Last 30 Days")
            }

            if period and period in period_map:
                where_clause += f" AND {period_map[period][0]}"
                period_title = period_map[period][1]

            # Fetch locations based on the selected period - LIMIT 5 REMOVED
            location_query = f"""
                SELECT country, COUNT(DISTINCT ip_address) as count
                FROM visitor_analytics
                WHERE {where_clause}
                GROUP BY country ORDER BY count DESC
            """
            c.execute(location_query)
            visitor_locations_raw = c.fetchall()
            visitor_locations = []
            if visitor_locations_raw:
                top_visitor_count = visitor_locations_raw[0]['count']
                for loc in visitor_locations_raw:
                    db_country_identifier = loc['country']
                    display_name = db_country_identifier
                    flag_emoji = '🌍'
                    try:
                        matches = pycountry.countries.search_fuzzy(db_country_identifier)
                        if matches:
                            country = matches[0]
                            display_name = country.name
                            flag_emoji = country_code_to_flag(country.alpha_2)
                    except Exception:
                        pass
                    
                    visitor_locations.append({
                        'name': display_name, 'count': loc['count'],
                        'bar_width': (loc['count'] / top_visitor_count * 100) if top_visitor_count > 0 else 0,
                        'flag': flag_emoji
                    })
            visitor_stats['locations'] = visitor_locations

        except mysql.connector.Error as db_err:
            if "doesn't exist" in str(db_err):
                 app.logger.warning("Table 'visitor_analytics' not found. Skipping visitor stats.")
                 visitor_stats = {'locations': [], 'last_24h': 0, 'last_7d': 0, 'last_14d': 0, 'last_30d': 0, 'all_time': 0}
            else:
                 raise db_err

        # --- USER MANAGEMENT ---
        query = request.args.get('query', '')
        search_query = f"%{query}%"
        
        c.execute(
            "SELECT id, email, tier FROM users WHERE tier NOT IN ('admin', 'public') AND email LIKE %s ORDER BY created_at DESC",
            (search_query,)
        )
        users_raw = c.fetchall()
        users = []
        for user in users_raw:
            user['storage_used'] = get_folder_size(get_user_dir(user['id']))
            users.append(user)

        return render_template('admin.html', 
                               stats=stats, 
                               locations=locations, 
                               users=users, 
                               visitor_stats=visitor_stats, 
                               period_title=period_title)

    except mysql.connector.Error as err:
        app.logger.error(f"Error on admin page: {err}")
        flash('Could not load admin analytics data.', 'error')
        return redirect(url_for('mycloud'))
    finally:
        if conn: conn.close()

@app.route('/admin/delete_user', methods=['POST'])
@admin_required
def admin_delete_user():
    user_id_to_delete = request.form.get('user_id')
    
    if not user_id_to_delete:
        flash("No user ID provided.", "error")
        return redirect(url_for('admin_dashboard'))

    if str(user_id_to_delete) == str(session['user_id']):
        flash("You cannot delete your own account from the admin panel.", "error")
        return redirect(url_for('admin_dashboard'))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE id = %s", (user_id_to_delete,))
    user_email_tuple = c.fetchone()
    conn.close()

    if not user_email_tuple:
        flash(f"User with ID {user_id_to_delete} not found.", "error")
        return redirect(url_for('admin_dashboard', query=request.args.get('query', '')))
    
    user_email = user_email_tuple[0]

    if _delete_user_account(user_id_to_delete):
        flash(f"Successfully deleted user '{user_email}' (ID: {user_id_to_delete}) and all their data.", 'success')
    else:
        flash(f"An error occurred while trying to delete user '{user_email}'. Check logs for details.", 'error')
        
    return redirect(url_for('admin_dashboard', query=request.args.get('query', '')))

# Add this to app.py

@app.route('/admin/change_tier', methods=['POST'])
@admin_required
def admin_change_tier():
    user_id = request.form.get('user_id')
    new_tier = request.form.get('new_tier')
    current_query = request.form.get('current_query', '')

    if not user_id or not new_tier:
        flash("Missing user ID or tier selection.", "error")
        return redirect(url_for('admin_dashboard', query=current_query))

    # Determine new quota based on app config
    if new_tier == 'basic':
        new_quota = app.config['BASIC_USER_QUOTA']
    elif new_tier == 'plus':
        new_quota = app.config['PLUS_USER_QUOTA']
    elif new_tier == 'pro':
        new_quota = app.config['PRO_USER_QUOTA']
    elif new_tier == 'free':
        new_quota = app.config['FREE_USER_QUOTA']
    else:
        flash("Invalid tier selected.", "error")
        return redirect(url_for('admin_dashboard', query=current_query))

    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Check if user exists and isn't admin/public
        c.execute("SELECT email, tier FROM users WHERE id = %s", (user_id,))
        user = c.fetchone()
        
        if not user:
            flash("User not found.", "error")
            return redirect(url_for('admin_dashboard', query=current_query))
            
        if user[1] in ['admin', 'public']:
            flash("Cannot change tier for Admin or Public accounts.", "error")
            return redirect(url_for('admin_dashboard', query=current_query))

        # Update user tier and quota. 
        # Note: We set paypal_subscription_id to NULL because this is a manual admin override
        # and should not be linked to an active PayPal recurring billing profile managed by the app.
        c.execute(
            "UPDATE users SET tier = %s, quota = %s, paypal_subscription_id = NULL WHERE id = %s",
            (new_tier, new_quota, user_id)
        )
        conn.commit()
        
        # Optional: Send email notification to user about the manual upgrade
        # executor.submit(send_subscription_confirmation_email, app, user[0], "User", new_tier.capitalize())
        
        flash(f"User {user[0]} manually updated to {new_tier.capitalize()} plan.", "success")

    except mysql.connector.Error as err:
        app.logger.error(f"Database error during admin tier change: {err}")
        if conn: conn.rollback()
        flash("Database error occurred while updating plan.", "error")
    finally:
        if conn: conn.close()

    return redirect(url_for('admin_dashboard', query=current_query))

if __name__ == '__main__':
    app.run(debug=True, threaded=True)