# CloudX — Privacy-First Cloud Storage

CloudX is a self-hosted file storage platform built with security and privacy at its core. No third-party dependencies, no AI training on your data, no telemetry.

> Built with Flask, MariaDB, and AES-256-GCM encryption.

---

## Features

### Security
- **Per-user encryption** — every user gets a unique Data Encryption Key (UDEK), encrypted by a master key. A compromised user never exposes others.
- **AES-256-GCM** encryption for all files at rest
- **ClamAV** virus scanning on every upload via Unix socket daemon
- **TLS/SSL** for all data in transit
- **reCAPTCHA** protection on authentication forms
- **Secure password hashing** via Werkzeug

### Storage & Files
- Upload files and folders
- Create, rename, move, and delete files
- Download as ZIP or TAR.ZSTD archive
- File previews (images, video, audio, PDF, text, code)
- Public and password-protected share links with expiration dates
- Share analytics per link (views, downloads, country, device)

### Subscription Tiers
| Plan | Storage | Max Upload | Speed |
|------|---------|------------|-------|
| Free | 5 GB | 1 GB | 2 MB/s |
| Basic | 50 GB | 5 GB | 4 MB/s |
| Plus | 200 GB | 20 GB | 6 MB/s |
| Pro | 500 GB | 50 GB | 10 MB/s |

- PayPal subscription integration (sandbox + production)
- Bandwidth throttling enforced at the streaming layer, not just the database

### Admin Dashboard
- User management (view, delete, manually change tier)
- Platform analytics (storage used, active users, new registrations)
- Visitor analytics with geolocation and device type
- Share analytics across all users

### Email System
- Email verification on registration (6-digit OTP, 10-minute expiry)
- Password reset via secure token
- Welcome emails, subscription confirmation, cancellation emails

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, Flask, Gevent |
| Database | MariaDB / MySQL with connection pooling |
| Encryption | AES-256-GCM (cryptography library) |
| Virus Scanning | ClamAV via pyclamd (Unix socket) |
| Payments | PayPal Subscriptions API |
| Email | SMTP via Flask-Mail |
| Compression | Flask-Compress, ZSTD, ZIP |
| Concurrency | ThreadPoolExecutor, Gevent monkey patching |
| Frontend | Vanilla HTML/CSS/JS, Jinja2 templates |

---

## Project Structure

```
cloudx/
├── app.py              # Main Flask application (routes, logic, encryption)
├── contact.py          # Email system (welcome, reset, verification, billing)
├── web.py              # Marketing website routes
├── templates/          # App templates (dashboard, share, admin, auth)
├── web-templates/      # Marketing pages (index, pricing, about, why-us)
├── static/
│   ├── style.css       # App styles
│   ├── website.css     # Marketing site styles
│   └── icons/          # File type icons (SVG)
├── .env.example        # Environment variable template
└── requirements.txt    # Python dependencies
```

---

## Setup

### Requirements
- Python 3.10+
- MariaDB or MySQL
- ClamAV daemon (`clamd`)
- A working SMTP server

### Installation

```bash
# Clone the repo
git clone https://github.com/ahmed-the-x/cloudX.git
cd cloudX

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Fill in your values in .env

# Run
python app.py
```

### Environment Variables

Copy `.env.example` to `.env` and fill in:

- `FLASK_SECRET_KEY` — random secret key for sessions
- `MYSQL_*` — your database credentials
- `MASTER_ENCRYPTION_KEY_HEX` — 32-byte hex key for UDEK encryption. Generate with:
  ```bash
  python3 -c "import os; print(os.urandom(32).hex())"
  ```
- `PAYPAL_*` — PayPal API credentials and plan IDs
- `MAIL_*` — SMTP configuration
- `RECAPTCHA_*` — Google reCAPTCHA v2 keys

---

## Architecture Highlights

**Key Hierarchy**
Each user has a unique 256-bit Data Encryption Key (UDEK). The UDEK is encrypted by a master key using AES-256-GCM and stored in the database. Files are encrypted with the user's UDEK. This means:
- The database alone is useless without the master key
- A leaked user record never exposes other users' files

**Bandwidth Throttling**
Speed limits are enforced at the streaming generator level using `time.sleep()` per chunk — not just stored as a database flag. Plan limits are real infrastructure constraints.

**Virus Scanning**
ClamAV runs as a daemon. Files are scanned via Unix socket before encryption. The database is kept in RAM for near-instant scans.

---

## License

MIT License — free to use, modify, and deploy.

---

*Built by [Ahmed Alaoui](https://linkedin.com/in/ahmed-alaoui1)*
