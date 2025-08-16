1) Backend (Django)

cd your-repo
python -m venv .venv
# mac/linux:
source .venv/bin/activate
# windows (powershell):
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 8000






2) Frontend (Next.js)

cd login_register/my-next-app

# install deps from the lockfile
npm ci 

# create your env file (create it in /my-next-app/.env.locale)
touch /my-next-app/.env.local
# open .env.local and paste this inside:
 DJANGO_BASE_URL=http://127.0.0.1:8000
 SIMPLEJWT_TOKEN_PATH=/api/auth/token/
 SIMPLEJWT_REFRESH_PATH=/api/auth/token/refresh/
 DJANGO_REGISTER_PATH=/api/auth/users/
 DJANGO_ME_PATH=/api/auth/users/me/
 AUTH_MODE=jwt

npm run dev
