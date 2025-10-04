# AR Portal (Authored Reference Data System) — with Map Catalog

## Quickstart
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python manage.py makemigrations maps
python manage.py migrate
python manage.py createsuperuser
python manage.py load_demo
python manage.py runserver
```

Open http://127.0.0.1:8000

Login: /accounts/login/ (demo users: encoder/encoder, approver/approver)

## Catalog
- `/maps/` — search by **map_name** or **description** (from `MapInfo`).
- Results list: map_name, version, last_modified, tracking_id, provider_sid, approver_sid.
- Click a map to open `/maps/view/<map_name>/<version>/` showing **all rows and string_01..string_65**.

## Docker
```bash
docker-compose up --build
```
