import os
import sys 
import secrets 
import shutil 
import tempfile 
import pyclamd as clamd 
import shlex 
import subprocess 
import time
from dotenv import load_dotenv
from gevent import monkey
from flask import Flask, render_template, request, jsonify, g, abort
from concurrent.futures import ThreadPoolExecutor
from contact import send_contact_form_email, send_public_share_link_email
import logging
import mysql.connector.pooling 
import requests 
from datetime import datetime, timedelta, timezone

from werkzeug.utils import secure_filename 
from cryptography.hazmat.primitives.ciphers.aead import AESGCM 
from cryptography.exceptions import InvalidTag 

monkey.patch_all()
load_dotenv()


app = Flask(__name__, template_folder='web-templates')

# --- Add All Required Config from app.py ---
REQUIRED_SECRETS = [
    'MAIL_USERNAME',
    'MAIL_PASSWORD',
    'MYSQL_USER',
    'MYSQL_PASSWORD',
    'MASTER_ENCRYPTION_KEY_HEX',
    'PUBLIC_UPLOADER_USER_ID',
    'PUBLIC_UPLOAD_FOLDER',
    'PUBLIC_USER_EMAIL'
]
missing_secrets = [key for key in REQUIRED_SECRETS if not os.environ.get(key)]
if missing_secrets:
    app.logger.error(f"FATAL ERROR: Missing required environment variables: {', '.join(missing_secrets)}")
    sys.exit(f"Error: Missing required environment variables: {', '.join(missing_secrets)}")

app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.hostinger.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'contact@cloudxhq.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = (
    os.environ.get('MAIL_SENDER_NAME', 'CloudX Contact Form'),
    os.environ.get('MAIL_SENDER_EMAIL', 'contact@cloudxhq.com')
)

# --- Add Config for Uploads, Encryption, and Scanning ---
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', '/srv/sharex_data/user_files')
app.config['PUBLIC_UPLOAD_FOLDER'] = os.environ.get('PUBLIC_UPLOAD_FOLDER')
app.config['MASTER_ENCRYPTION_KEY'] = bytes.fromhex(os.environ.get('MASTER_ENCRYPTION_KEY_HEX'))
app.config['CLAMD_SOCKET'] = os.environ.get('CLAMD_SOCKET', '/run/clamav/clamd.ctl')
app.config['CLAMAV_MAX_FILE_SIZE_BYTES'] = 500 * 1024 * 1024 # 500MB
app.config['CLAMAV_MAX_FOLDER_ITEMS'] = 300
app.config['PUBLIC_UPLOAD_LIMIT'] = 500 * 1024 * 1024 # 500MB
app.config['PUBLIC_SPEED_LIMIT'] = 5 * 1024 * 1024 # 5 MB/s
app.config['PUBLIC_UPLOADER_USER_ID'] = os.environ.get('PUBLIC_UPLOADER_USER_ID')
app.config['UPLOAD_CHUNK'] = 8 * 1024 * 1024 # 8MB Chunk
app.config['ENCRYPTION_CHUNK_SIZE'] = 8 * 1024 * 1024

try:
    db_pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="web_visitor_pool",
        pool_size=5, 
        host=os.environ.get('MYSQL_HOST', 'localhost'),
        user=os.environ.get('MYSQL_USER'),
        password=os.environ.get('MYSQL_PASSWORD'),
        database=os.environ.get('MYSQL_DB', 'cloudx_db')
    )
except mysql.connector.Error as err:
    app.logger.error(f"FATAL: Could not connect to the database in web.py: {err}")
    db_pool = None

executor = ThreadPoolExecutor(max_workers=5)

logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

recent_visitors = {}

# --- ADD HELPER FUNCTIONS (COPIED FROM APP.PY) ---

def get_db_connection():
    return db_pool.get_connection()

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

def get_unique_filename(path):
    """
    Checks if a file exists. If it does, returns a unique name,
    e.g., 'file.txt' -> 'file_copy.txt' -> 'file_copy(2).txt'
    """
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

def count_files_in_folder(folder_path):
    """Recursively counts files in a folder."""
    count = 0
    try:
        for _, _, files in os.walk(folder_path):
            count += len(files)
    except FileNotFoundError:
        return 0
    return count

def safe_path_component(name):
    """Sanitizes a single path component."""
    if not name:
        return 'unnamed'
    dangerous_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in dangerous_chars:
        name = name.replace(char, '_')
    name = name.strip('. ')
    if not name:
        name = 'unnamed'
    return name

def scan_file_with_clamav(file_path: str):
    """Scans a file with ClamAV daemon."""
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

def get_user_udek(user_id):
    """Fetches and decrypts the User Data Encryption Key (UDEK)."""
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
    """Encrypts a file chunk by chunk."""
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

def generate_public_share_url(token):
    """Creates the full public URL for a share token."""
    public_domain = os.environ.get('PUBLIC_DOMAIN', 'cloudxhq.com')
    path = f"/shared/{token}"
    return f"https://{public_domain}{path}"

# --- END OF HELPER FUNCTIONS ---


def init_db_web():
    """Initializes the visitor_analytics table if it doesn't exist."""
    if not db_pool:
        return
    conn = None
    try:
        conn = db_pool.get_connection()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS visitor_analytics (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    ip_address VARCHAR(45) NOT NULL,
                    country VARCHAR(100),
                    visit_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    visit_date DATE AS (DATE(visit_timestamp)) STORED,
                    UNIQUE KEY unique_visitor_per_day (ip_address, visit_date)
                    )''')
        conn.commit()
        app.logger.info("Visitor analytics table checked/created successfully.")
    except mysql.connector.Error as err:
        app.logger.error(f"Error initializing visitor DB table: {err}")
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_client_ip(req):
    """Gets the real client IP, considering proxies."""
    if req.headers.get('X-Forwarded-For'):
        return req.headers.get('X-Forwarded-For').split(',')[0].strip()
    return req.remote_addr

def log_visitor_task(ip_address):
    """Logs a unique visitor by IP and day."""
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
        conn = db_pool.get_connection()
        c = conn.cursor()
        c.execute(
            "INSERT IGNORE INTO visitor_analytics (ip_address, country, visit_timestamp) VALUES (%s, %s, %s)",
            (ip_address, country, datetime.now())
        )
        conn.commit()
    except mysql.connector.Error as err:
        app.logger.error(f"Visitor logging DB error: {err}")
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.before_request
def before_request_callback():
    """Logs new visitors in a background thread."""
    if not db_pool or request.path.startswith('/static/'):
        return

    ip = get_client_ip(request)
    now = datetime.now()

    # Clean up old visitors from the recent_visitors cache
    for visitor_ip, last_seen in list(recent_visitors.items()):
        if now - last_seen > timedelta(hours=6):
            del recent_visitors[visitor_ip]

    if ip not in recent_visitors:
        recent_visitors[ip] = now
        executor.submit(log_visitor_task, ip)

init_db_web()

@app.route("/")
def homepage():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/pricing")
def pricing():
    return render_template("pricing.html")

@app.route("/why-us")
def why_us():
    return render_template("why-us.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/contact", methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        try:
            data = request.get_json()
            name = data.get('name')
            email = data.get('email')
            subject = data.get('subject')
            message = data.get('message')

            if not all([name, email, subject, message]):
                return jsonify({'success': False, 'message': 'Missing form data.'}), 400

            executor.submit(send_contact_form_email, app, name, email, subject, message)
            
            return jsonify({'success': True, 'message': 'Message sent successfully!'})

        except Exception as e:
            app.logger.error(f"Error processing contact form: {e}")
            return jsonify({'success': False, 'message': 'An internal error occurred.'}), 500
            
    return render_template("contact.html")


# --- PUBLIC UPLOAD ENDPOINTS ---

@app.route('/public-upload', methods=['POST'])
def public_upload():
    try:
        public_user_id = app.config['PUBLIC_UPLOADER_USER_ID']
        if not public_user_id:
            app.logger.error("PUBLIC_UPLOADER_USER_ID is not configured in web.py")
            return jsonify({'success': False, 'message': 'Public uploader is not configured.'}), 500
        
        public_user_dir = get_user_dir(public_user_id)
        speed_limit = app.config['PUBLIC_SPEED_LIMIT']
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'no_file_selected'})

        file = request.files['file']
        filename = request.form.get('filename', file.filename)
        secure_name = secure_filename(filename)
        if not secure_name:
            return jsonify({'success': False, 'message': 'invalid_filename'})

        total_size = int(request.form.get('totalSize', 0))
        if total_size > app.config['PUBLIC_UPLOAD_LIMIT']:
            return jsonify({'success': False, 'message': 'file_too_large'})

        chunk_number = int(request.form.get('chunkNumber', 0))
        total_chunks = int(request.form.get('totalChunks', 1))
        relative_path = request.form.get('relative_path', '') 

        if relative_path:
            path_parts = [safe_path_component(p) for p in relative_path.split('/') if p]
            if not path_parts:
                return jsonify({'success': False, 'message': 'invalid_relative_path'})

            target_dir = os.path.join(public_user_dir, *path_parts[:-1])
            final_path_uniquified = get_unique_filename(os.path.join(target_dir, secure_name))
            
            os.makedirs(target_dir, exist_ok=True)
        else:
            final_path_uniquified = get_unique_filename(os.path.join(public_user_dir, secure_name))
        
        temp_path = f"{final_path_uniquified}.part"

        try:
            buffer_size = 4 * 1024 * 1024
            with open(temp_path, 'ab') as f:
                f.seek(chunk_number * app.config['UPLOAD_CHUNK'])
                
                while True:
                    data_chunk = file.stream.read(buffer_size)
                    if not data_chunk:
                        break
                    f.write(data_chunk)
                    time.sleep(len(data_chunk) / speed_limit)

            if chunk_number == total_chunks - 1:
                should_scan = True
                scan_status = 'not_scanned'
                
                if relative_path:
                    top_folder_name = safe_path_component(relative_path.split('/')[0])
                    folder_full_path = os.path.join(public_user_dir, top_folder_name)
                    
                    if count_files_in_folder(folder_full_path) >= app.config['CLAMAV_MAX_FOLDER_ITEMS']:
                        should_scan = False
                        scan_status = 'skipped_folder_limit'
                        app.logger.info(f"Public Upload: Skipping scan for {filename}, folder '{top_folder_name}' exceeds item limit.")
                
                if should_scan:
                    scan_result = scan_file_with_clamav(temp_path)
                else:
                    scan_result = {'status': scan_status}
                
                if scan_result['status'] == 'malicious':
                    os.remove(temp_path)
                    app.logger.warning(f"Malicious public file upload blocked: {filename}")
                    return jsonify({'success': False, 'message': 'virus_detected', 'filename': filename})
                elif scan_result['status'] == 'error':
                    os.remove(temp_path)
                    app.logger.error(f"ClamAV scan error for public upload: {filename}")
                    return jsonify({'success': False, 'message': 'virus_scan_error'})

                try:
                    public_udek = get_user_udek(public_user_id)
                    encrypt_file_stream(temp_path, final_path_uniquified, public_udek)
                except Exception as e:
                    app.logger.error(f"Public encryption failed for {final_path_uniquified}: {e}")
                    if os.path.exists(temp_path): os.remove(temp_path)
                    return jsonify({'success': False, 'message': 'Encryption failed on server.'})
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                
                return jsonify({
                    'success': True, 
                    'filename': os.path.basename(final_path_uniquified), # The *unique* name
                    'relative_path': relative_path,
                    'original_filename': filename
                })

            return jsonify({'success': True}) # Chunk received OK

        except IOError as e:
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass
            return jsonify({'success': False, 'message': f'io_error: {str(e)}'})

    except Exception as e:
        app.logger.error(f"Public Upload error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/public-share', methods=['POST'])
def public_share():
    """
    Creates or Updates a public share link.
    This now checks for an existing link first.
    """
    conn = None
    try:
        data = request.json
        item_path = data.get('path') # This is the unique, secure top-level item (file or folder)
        expiry_hours = int(data.get('expiry', 0)) # Default to 0 (no expiry) if not provided
        password = data.get('password') or None
        permissions_str = data.get('permissions', 'preview,download')
        
        public_user_id = app.config['PUBLIC_UPLOADER_USER_ID']
        if not public_user_id:
            return jsonify({'success': False, 'message': 'Public uploader not configured.'}), 500
        
        expires_at = None
        if expiry_hours > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)

        conn = get_db_connection()
        c = conn.cursor()
        
        # --- *** THIS IS THE NEW LOGIC *** ---
        c.execute('SELECT token FROM shares WHERE user_id = %s AND item_path = %s', 
                  (public_user_id, item_path))
        existing_share = c.fetchone()

        reused = False
        if existing_share:
            # 1. A link EXISTS. Update it.
            token = existing_share[0]
            c.execute(
                'UPDATE shares SET expires_at = %s, permissions = %s, password_hash = %s WHERE token = %s',
                (expires_at, permissions_str, password, token)
            )
            reused = True
            app.logger.info(f"Public share link UPDATED for item: {item_path}")
        else:
            # 2. No link exists. Create one.
            token = secrets.token_urlsafe(16)
            c.execute(
                'INSERT INTO shares (token, user_id, username, item_path, expires_at, permissions, password_hash) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (token, public_user_id, 'Public Upload', item_path, expires_at, permissions_str, password)
            )
            app.logger.info(f"Public share link CREATED for item: {item_path}")
        # --- *** END NEW LOGIC *** ---
        
        conn.commit()
        
        share_url = generate_public_share_url(token)
        return jsonify({'success': True, 'url': share_url, 'reused': reused}) # Send 'reused' status

    except Exception as e:
        app.logger.error(f"Error creating/updating public share link: {e}")
        if conn: conn.rollback()
        return jsonify({'success': False, 'message': 'Database error occurred.'})
    finally:
        if conn: conn.close()

@app.route('/public-email-link', methods=['POST'])
def public_email_link():
    try:
        data = request.json
        email = data.get('email')
        url = data.get('url')
        filename = data.get('filename') # This should be the *original* filename

        if not all([email, url, filename]):
            return jsonify({'success': False, 'message': 'Missing data.'}), 400
        
        # Use the new email function
        executor.submit(send_public_share_link_email, app, email, url, filename)
        
        return jsonify({'success': True, 'message': 'Email sent.'})
    except Exception as e:
        app.logger.error(f"Error sending public link email: {e}")
        return jsonify({'success': False, 'message': 'Server error.'}), 500