# AcxiomCRM — Python + PyTorch

A full-stack CRM MVP based on the supplied AcxiomCRM functional specification. It includes authentication, roles, dashboard analytics, customers, leads, opportunities, follow-ups, audit logs, REST APIs, validation, and a small PyTorch lead-scoring service.

## Stack
- Backend: Python / Flask / SQLAlchemy
- Database: SQLite
- Authentication: Flask-Login + Werkzeug password hashing
- Frontend: Jinja2 / Bootstrap 5 / vanilla JavaScript / Chart.js
- ML: PyTorch lead-scoring model

## Run on Windows
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## Demo accounts
- admin@acxiom.local / Admin@123
- manager@acxiom.local / Manager@123
- sales@acxiom.local / Sales@123

The app creates these accounts and sample CRM records automatically on first run.

## Main routes
- `/login`
- `/dashboard`
- `/customers`
- `/leads`
- `/opportunities`
- `/followups`
- `/audit`
- `/users`
- `/api/customers`
- `/api/leads`
- `/api/opportunities`
- `/api/reports/pipeline`
- `/api/lead-score`

## Notes
This implementation follows the business requirements in the supplied PDF while using Python/Flask instead of ASP.NET Core because that was requested. The architecture is intentionally simple enough to run quickly as a project demo.
