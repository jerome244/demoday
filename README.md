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









install venv first

then pip install -r requirements.txt



launch django server: 

python manage.py runserver







launch next.js:

cd /demoday/next-graph-app


npm install


npm i -D @types/cytoscape


npm run dev



