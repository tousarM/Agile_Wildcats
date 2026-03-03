# Product Development Management System (PDMS) Guide (Readme.md)

Authors: Simon G.Dak ,Osvaldo Estrell, Tousar Mohammed, Wesley Nguyen

Date: 2026-25-02  

This guide (Readme.md) provide developer onboarding explains about the project ,  setup, usage, and testing so contributors can get started quickly. Inline comments highlight customizable sections.

## About PDMS

The Product Development Management System is an Agile project management tool that allows users to manage Product Backlog.

This system allows team members to add new tasks to the Product Backlog, set and change priority for a task, move a task from the Product Backlog to the current Sprint Backlog, and then move a task from the Sprint Backlog to the Ready for Test status.


Once tested, the task is either failed and sent back for re-work in a Sprint or passed and marked as complete and ready for release.

---

## Project Setup

## 1. Clone the repository

```bash
git clone https://github.com/tousarM/Agile_Wildcats.git
cd pdms
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate it:

- Windows:

  ```bash
  venv\Scripts\activate
  ```

- macOS/Linux:

  ```bash
  source venv/bin/activate
  ```

### 3. Install dependencies

```bash
pip install -r requirements.txt
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

## Routes (with `/pdms/` prefix)

- Home → `http://127.0.0.1:8000/pdms/`  
- About → `http://127.0.0.1:8000/pdms/about/`  
