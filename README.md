# Agile Wildcats — Product Development Management System (PDMS)

Authors: Simon G. Dak, Osvaldo Estrell, Tousar Mohammed, Wesley Nguyen  
Date : 2026-03-13  

This README provides onboarding instructions for the PDMS project. It reflects the exact structure: root → `PDMS/` project folder → `accounts/` app and nested `PDMS/` settings package. It explains the purpose of the system, setup steps, usage, and directory layout so team members and contributors can quickly get started.

---

## About PDMS

The Product Development Management System (PDMS) is an Agile project management tool designed to help teams manage product backlogs and sprint workflows.

### Key Features

- Add new tasks to the Product Backlog  
- Set and update task priority  
- Move tasks between Backlog → Sprint → Ready for Test  
- Track testing outcomes:
  - Failed → returned to Sprint for rework  
  - Passed → marked complete and ready for release  
- Role‑based access control:
  - Users must register and log in with assigned roles  
  - Roles determine permissions (e.g., Admin, Scrum Master, CI/CD Manaager, Tester Manager etc )  
  - Admins manage users and tasks, Scrum Master update backlog/sprints, Testers Manager record outcomes  

---

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/tousarM/Agile_Wildcats.git
cd Agile_Wildcats-main
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate it:

- Windows

  ```bash
  venv\Scripts\activate

  ```

- macOS/Linux

  ```bash
  source venv/bin/activate
  ```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Run migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Create a superuser

```bash
python manage.py createsuperuser
```

### 6. Start the server

```bash
python manage.py runserver
```

---

## Docker Setup

For containerized development or deployment:

```bash
docker-compose up --build
```

- The app runs on `http://127.0.0.1:8000/`  
- SQLite database (`db.sqlite3`) is persisted via volume mapping  
- Static files are collected automatically in the image  

---

## Environment Variables

The project uses a `.env` file for configuration. Create a `.env` file in the project root with the following keys:

```env
# Django settings
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

# Database (SQLite by default, can switch to PostgreSQL later)
DATABASE_URL=sqlite:///db.sqlite3

# Static & media
STATIC_URL=/static/
MEDIA_URL=/media/
```

> Do not commit `.env` to GitHub — it’s already ignored in `.gitignore`.

---

## Routes

- Home → `http://127.0.0.1:8000/`  
- Login → `http://127.0.0.1:8000/login/`  
- Register → `http://127.0.0.1:8000/register/`  
- Tasks → `http://127.0.0.1:8000/tasks/`  
- Admin panel → `http://127.0.0.1:8000/admin/`  

---

## Project Structure

AGILE_WILDCATS-MAIN/
│   manage.py
│   requirements.txt
│   README.md
│   .gitignore
│   .dockerignore
│   dockerfile
│   docker-compose.yml
│   db.sqlite3
│   .env
│
├── .github/               # GitHub workflows, CI/CD configs
│   └── workflows/
│       └── codeql.yml
│
├── PDMS/                  # Django project folder
│   ├── accounts/          # Main app
│   │   ├── admin.py        # Admin customizations
│   │   ├── apps.py         # AppConfig (loads signals)
│   │   ├── forms.py        # User forms (login, register)
│   │   ├── models.py       # Profile, Task models
│   │   ├── signals.py      # Auto-create Profile on User creation
│   │   ├── urls.py         # App routes
│   │   ├── views.py        # Business logic
│   │   ├── tests.py        # Unit tests
│   │   ├── migrations/     # Database migrations
│   │   └── templates/      # App templates
│   │       ├── base.html
│   │       ├── forgot_password.html
│   │       ├── login.html
│   │       ├── register.html
│   │       ├── tasks.html
│   │       └── welcome.html
│   │
│   └── PDMS/              # Project settings/config package
│       ├── __init__.py
│       ├── asgi.py
│       ├── settings.py
│       ├── urls.py
│       └── wsgi.py

---

## Next Steps for the Team

- Add unit tests for models, forms, and views  
- Extend task management with sprint and backlog boards  
- Improve UI/UX with responsive design  
- Add API endpoints for integration with external tools  
- Configure CI/CD pipeline with GitHub Actions  
- Implement advanced role management (e.g., permissions per role)  
