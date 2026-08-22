# How to Run

Unzip the project, open the folder in VS Code, then open **two terminals**
(Terminal → New Terminal, then click the `+` for a second one).

## Terminal 1 — Backend

**If the zip already includes `backend\venv`**, skip straight to activating it —
no need to create it or reinstall packages:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
```

If that fails (see note below), delete the `venv` folder and fall back to:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```


Then start the server:

```powershell
uvicorn app.main:app --reload --port 8000
```

Leave this running. Check it worked: http://localhost:8000/docs

## Terminal 2 — Frontend

```powershell
cd frontend
python -m http.server 3000
```

Leave this running too.

## Open the app

**http://localhost:3000** → Get Started → create an account.

---


```

### If something breaks
- `'python' not recognized` → Python isn't installed / not on PATH (install from python.org, check "Add to PATH").
- `Activate.ps1 disabled` → run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then retry.
- Port already in use → close whatever's using 8000/3000, or run on a different port.
- **Included `venv` doesn't work** (`ModuleNotFoundError`, wrong Python path, activate errors) →
  a venv is tied to the exact folder path and Python install it was created on, so it often
  breaks when copied to another PC. Delete `backend\venv` and create a fresh one with the
  `python -m venv venv` steps above — takes a couple of minutes.
