# Deploying Cynthia (CloudDrive) to PythonAnywhere

A step-by-step for putting the app on a free PythonAnywhere web app so a client
can reach it at `https://YOURUSER.pythonanywhere.com`.

Replace `YOURUSER` with your PythonAnywhere username throughout.

---

## 0. Before you start

1. Create a free account at https://www.pythonanywhere.com/registration/register/beginner/
2. Generate a session secret (run locally):
   ```
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
3. **Rotate the Gemini API key.** The old key was stored in plaintext in `.env`
   during development. Create a fresh one at
   https://aistudio.google.com/app/apikey and use the new value below.

---

## 1. Get the code onto PythonAnywhere

### Option A — GitHub (recommended for updates later)

Locally:
```
cd C:\Users\user\Documents\Cynthia
git init
git add .
git commit -m "Prepare for deployment"
```
Create a **private** repo on GitHub and push to it. `.gitignore` already excludes
`.env`, `env/`, `__pycache__/`, `instance/`, and `static/uploads/`, so no secrets
or local data are pushed.

Then in a PythonAnywhere **Bash console**:
```
git clone https://github.com/YOURNAME/YOURREPO.git ~/Cynthia
```

### Option B — Zip upload

Zip the project folder *without* `env/`, `__pycache__/`, `instance/`,
`static/uploads/`, and `.env`. Upload the zip via the **Files** tab, then in a
Bash console:
```
cd ~ && unzip Cynthia.zip -d Cynthia
```

---

## 2. Virtualenv and dependencies

In a PythonAnywhere Bash console:
```
cd ~/Cynthia
python3.10 -m venv ~/.virtualenvs/cynthia
source ~/.virtualenvs/cynthia/bin/activate
pip install -r requirements.txt
```

---

## 3. Create the server-side `.env`

In the **Files** tab, create `/home/YOURUSER/Cynthia/.env` with:
```
SECRET_KEY=<the token_hex(32) value from step 0>
GEMINI_API_KEY=<your rotated key, or leave blank to disable AI image generation>
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image
UPLOAD_FOLDER=/home/YOURUSER/Cynthia/static/uploads
SESSION_COOKIE_SECURE=true
```
The database defaults to SQLite at `~/Cynthia/instance/clouddrive.db` — no setup
needed. `USER_STORAGE_LIMIT` defaults to 3 GB; add a line to override it.

---

## 4. Configure the web app

**Web** tab → **Add a new web app** → **Manual configuration** → **Python 3.10**.

Then set:

| Field | Value |
|---|---|
| Source code | `/home/YOURUSER/Cynthia` |
| Working directory | `/home/YOURUSER/Cynthia` |
| Virtualenv | `/home/YOURUSER/.virtualenvs/cynthia` |

**WSGI configuration file** (click the link on the Web tab to edit it) — delete
everything and replace with:
```python
import sys

path = '/home/YOURUSER/Cynthia'
if path not in sys.path:
    sys.path.insert(0, path)

from wsgi import application  # noqa: E402
```

**Static files** section — add:

| URL | Directory |
|---|---|
| `/static/` | `/home/YOURUSER/Cynthia/static` |

**Security** section — turn **Force HTTPS** on.

---

## 5. Launch

Click the green **Reload** button on the Web tab.

The app creates its database tables and applies the 3 GB storage limit
automatically on first load. Then visit:
```
https://YOURUSER.pythonanywhere.com/auth/register
```

Create an account, upload a file, confirm the storage bar shows a **3 GB** limit.

---

## 6. Share with the client

Send them `https://YOURUSER.pythonanywhere.com`. Either pre-register an account
for them or let them sign up themselves. The site stays up with no cold starts,
and their uploads and account persist.

---

## Free-tier limits to know

- **Outbound internet is whitelisted.** AI image generation calls
  `generativelanguage.googleapis.com`. If that host isn't on PythonAnywhere's
  free whitelist, image generation returns a clean error and every other feature
  still works. You can request the host be added on the PythonAnywhere forum, or
  upgrade to the $5/month "Hacker" plan, which removes the whitelist.
- **Disk: 512 MB.** The per-account quota reads 3 GB, but the real ceiling on
  free is 512 MB of disk. Fine for a demo — don't upload gigabytes.
- **Daily CPU allowance.** Thumbnailing and image generation use some; light
  demo traffic is well within it.
- **Free web apps expire every 3 months** — you get an email with a one-click
  "run it for another 3 months" link.

---

## Updating the deployed app later

```
cd ~/Cynthia
git pull            # or re-upload changed files via the Files tab
```
Then click **Reload** on the Web tab.

---

## What changed in the codebase to prepare for this

| File | Change |
|---|---|
| `config.py` | `.env` resolved relative to the project (not the working dir); `SQLALCHEMY_DATABASE_URI` now reads `DATABASE_URL`; `UPLOAD_FOLDER` is absolute and overridable; added `SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE` |
| `database.py` | `storage_used` and `storage_limit` changed from `Integer` to `BigInteger` (3 GB overflows a 32-bit int on Postgres/MySQL); default limit is 3 GB |
| `app.py` | debug server is off unless `FLASK_DEBUG` is set; port reads `PORT` |
| `wsgi.py` | **new** — WSGI entrypoint imported by the PythonAnywhere config |
| `.env.example` | **new** — template for the environment variables |
