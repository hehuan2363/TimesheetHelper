## Timesheet Helper

A lightweight Flask web application to draft weekly Oracle-style timesheets. The tool stores everything in a local SQLite database and keeps dependencies minimal so it is easy to run on an internal server or developer workstation.

### Features

- Password-based authentication with per-user charge codes.
- Thursday–Wednesday weekly view with quick entry form and edit/delete actions.
- Oracle-style overview table for fast copy/paste into the official system.
- REST API endpoints for time entry CRUD (useful for future integrations).

### Setup

1. **Create and activate a virtual environment (optional but recommended).**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies.**

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the development server.**

   ```bash
   export FLASK_APP=app:create_app
   export FLASK_ENV=development  # optional for auto-reload
   flask run
   ```

   Alternatively, you can start the app directly:

   ```bash
   python3 app.py
   ```

4. **Open the app** at [http://localhost:5000](http://localhost:5000).

The first user to register is created as a normal account; there is no admin concept yet. Each user manages their own charge codes and entries.

### Configuration Notes

- The SQLite database file (`timesheet.db`) is created in the project root when the app starts. Back it up regularly if you deploy for multiple users.
- Update the `SECRET_KEY` in `app.py` before running in any shared environment.
- `FLASK_ENV=development` enables the debug server; unset in production.

### Next Ideas

- Add CSV export that matches Oracle import requirements exactly.
- Support favorite charge codes and “copy last week” helpers.
- Integrate with company SSO or directory service for authentication.
