# Agile Wildcats — Product Development Management System (PDMS)

Authors: Simon G. Dak, Osvaldo Estrell, Tousar Mohammed, Wesley Nguyen  
Date : 2026-03-13
update Date: 2026-04-22

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
  - Roles determine permissions (e.g., Admin, Scrum Master, CI/CD Manager, Tester Manager)  
  - Admins manage users and tasks, Scrum Master updates backlog/sprints, Testers Manager record outcomes  

### Navigation Features
- Home     Landing page showing project overview, sprint summary, and quick links.  
- Backlog- Repository of all tasks and user stories not yet assigned to sprints.  
- Sprints- Time‑boxed iterations where backlog items are committed for development and tracked.  
- Tasks -  Detailed view of individual tasks, including description, priority, assignee, and status.  
- Board -  Visual Kanban board for moving tasks across workflow stages (Backlog → Sprint → Test → Done).  
- Team -   Displays registered users, their roles, and permissions. Admins manage accounts here.  
- Logout   Ends the current user session securely, enforcing role‑based access control.  

---

## Local Setup

1. Clone the repository
   ```bash
   git clone https://github.com/tousarM/Agile_Wildcats.git
   cd Agile_Wildcats-main
   ```

2. Create a virtual environment
   ```bash
   python -m venv venv
   ```
   Activate it:
   - Windows: `venv\Scripts\activate`  
   - macOS/Linux: `source venv/bin/activate`

3. Install dependencies
   ```bash
   python -m pip install -r requirements.txt
   ```

4. Run migrations
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

5. Create a superuser 
   ```bash
   python manage.py createsuperuser
   ```

6. Start the server
   ```bash
   python manage.py runserver
   ```

## Docker Setup

For containerized development or deployment:
```bash
docker-compose up --build
```

- The app runs on `http://127.0.0.1:8000/`  
- SQLite database (`db.sqlite3`) is persisted via volume mapping  
- Static files are collected automatically in the image  

---

## CI/CD Configuration

The PDMS project uses GitHub Actions for continuous integration and deployment. The workflow file is located at:

```
.github/workflows/pdms-ci.yml
```

### Workflow Triggers
- Pushes to `main`
- Pull requests targeting `main`
- Release tags :v1.0`)
- Weekly scheduled CodeQL scan

### Pipeline Steps
-  Checkout Code
-  Set Up Python
- CodeQL Security Analysis
- Database Migrations & Tests
- Collect Static Files
- Docker Build & Push
- Deploy to Kubernetes (on release/tag)

### Secrets Required
- `DOCKER_USERNAME` → Docker Hub account  
- `DOCKER_PASSWORD` → Docker Hub password or token  
- `SECRET_KEY` → Django secret key  
- `DB_USER` / `DB_PASSWORD` → Database credentials (if using PostgreSQL/MySQL later)  

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

- Home-   `http://127.0.0.1:8000/`  
- Backlog-`http://127.0.0.1:8000/backlog/`  
- Sprints-`http://127.0.0.1:8000/sprints/`  
- Tasks-  `http://127.0.0.1:8000/tasks/`  
- Board-  `http://127.0.0.1:8000/board/`  
- Team    `http://127.0.0.1:8000/team/`  
- Logout- `http://127.0.0.1:8000/logout/`  

---

## Workflow Diagram

```text
Backlog  →  Sprint  →  Test  →  Done
   |          |         |        |
   |          |         |        └── Release
   |          |         └── Failed → Back to Sprint
   └── New tasks added continuously
```

This diagram shows how tasks flow through the PDMS system:  
- Tasks start in Backlog.  
- Selected items move into Sprint.  
- Completed items go to Test.  
- If tests fail, tasks return to Sprint for rework.  
- If tests pass, tasks are marked Done and released.  

---

## Project Structure

```
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
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── forms.py
│   │   ├── models.py
│   │   ├── signals.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── tests.py
│   │   ├── migrations/
│   │   └── templates/
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
```
