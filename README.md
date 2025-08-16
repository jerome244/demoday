myproject/
├─ manage.py
├─ requirements.txt
├─ .env.example
├─ .gitignore
├─ db.sqlite3                # (created after migrate)
├─ media/                    # uploads (profile photos, etc.)
├─ static/                   # collected static (optional)
├─ myproject/                # project settings package
│  ├─ __init__.py
│  ├─ settings.py
│  ├─ urls.py
│  ├─ asgi.py
│  └─ wsgi.py
├─ community/                # your forum/users/projects app
│  ├─ __init__.py
│  ├─ apps.py
│  ├─ admin.py
│  ├─ models.py              # <- paste the Community models from my last message
│  ├─ views.py               # <- optional endpoints (zip upload/download)
│  ├─ urls.py
│  ├─ migrations/
│  │  └─ __init__.py
│  └─ tests.py
└─ codeparsers/              # optional: parsing API app I shared earlier
   ├─ __init__.py
   ├─ apps.py
   ├─ admin.py
   ├─ models.py              # simple ParseResult JSON store
   ├─ parsers.py             # Python/C/CSS/HTML/JS parsers + facade
   ├─ views.py               # ParseAPI view
   ├─ urls.py
   ├─ migrations/
   │  └─ __init__.py
   └─ tests.py



1) Backend (Django)

cd your-repo
python -m venv .venv
# mac/linux:
source .venv/bin/activate
# windows (powershell):
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver






2) reinstall mongodb modules from root

npm ci 