# AI-Driven BI Dashboard Generator - Backend

FastAPI backend for the Business Intelligence Dashboard Generator.

## Tech Stack

- **FastAPI 0.104+** - Modern Python web framework
- **SQLAlchemy 2.0+** - ORM for database operations
- **SQLite** - Development database (file-based)
- **Pandas 2.0+** - Data processing and analysis
- **Plotly 5.17+** - Chart generation
- **Passlib + Bcrypt** - Password hashing
- **Python-Jose** - JWT token handling

## Setup Instructions

### 1. Create Virtual Environment

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows)
venv\Scripts\activate

# Activate virtual environment (Linux/Mac)
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Edit `.env` file and set a secure `SECRET_KEY`:

```bash
# Generate a secure secret key (run this in terminal)
openssl rand -hex 32

# Or use Python
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the generated key and paste it in `.env` file.

### 4. Run Database Migrations

The database tables are automatically created on first run. The SQLite database file `app.db` will be created in the backend directory.

### 5. Start Development Server

```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at:
- **API Root**: http://localhost:8000
- **Interactive Docs (Swagger)**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── api/                 # API endpoints
│   │   ├── v1/
│   │   │   ├── auth.py      # Authentication routes
│   │   │   ├── datasets.py  # Dataset management
│   │   │   ├── queries.py   # Query execution
│   │   │   └── dashboards.py
│   │   └── deps.py          # Dependencies (auth, db)
│   ├── core/
│   │   ├── config.py        # Settings from .env
│   │   ├── database.py      # SQLAlchemy setup
│   │   └── security.py      # Password & JWT utilities
│   ├── models/              # SQLAlchemy models
│   │   ├── user.py
│   │   ├── dataset.py
│   │   └── dashboard.py
│   ├── schemas/             # Pydantic schemas
│   ├── crud/                # Database operations
│   ├── services/            # Business logic
│   └── utils/               # Helper functions
├── data/
│   ├── uploads/             # User uploaded files
│   ├── processed/           # Cleaned datasets
│   └── samples/             # Sample datasets
├── requirements.txt
├── .env
└── README.md
```

## API Endpoints (After Full Implementation)

### Authentication
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login and get JWT token
- `GET /api/v1/users/me` - Get current user info

### Datasets
- `POST /api/v1/datasets` - Upload dataset
- `GET /api/v1/datasets` - List user's datasets
- `GET /api/v1/datasets/{id}/preview` - Preview dataset
- `DELETE /api/v1/datasets/{id}` - Delete dataset

### Queries
- `POST /api/v1/queries/template` - Execute template query

### Dashboards
- `POST /api/v1/dashboards` - Save dashboard
- `GET /api/v1/dashboards` - List dashboards
- `GET /api/v1/dashboards/{id}` - Get dashboard
- `PUT /api/v1/dashboards/{id}` - Update dashboard
- `DELETE /api/v1/dashboards/{id}` - Delete dashboard

## Development Status

### ✅ Completed (Task 1)
- [x] Project structure created
- [x] FastAPI app skeleton
- [x] Database models (User, Dataset, Dashboard)
- [x] Configuration management
- [x] CORS setup

### 🔄 In Progress
- [ ] Authentication endpoints (Task 2)
- [ ] Password hashing & JWT (Task 2)
- [ ] Frontend integration (Task 3)

### ⏳ Upcoming
- [ ] Dataset upload (Day 2)
- [ ] Data processing (Day 3)
- [ ] Query system (Day 4)
- [ ] Dashboard persistence (Day 6)

## Testing

### Manual Testing
Use the interactive docs at http://localhost:8000/docs to test endpoints.

### Test with curl

```bash
# Health check
curl http://localhost:8000/health

# Root endpoint
curl http://localhost:8000/
```

## Troubleshooting

### Import Errors
Make sure virtual environment is activated and dependencies are installed.

### Database Errors
Delete `app.db` file and restart the server to recreate tables.

### Port Already in Use
Change port: `uvicorn app.main:app --reload --port 8001`

## Next Steps

1. Complete Task 2: Implement authentication endpoints
2. Test authentication flow with Postman
3. Move to Task 3: Build frontend for login/register

---

**Project**: FYP - AI-Driven BI Dashboard Generator  
**Phase**: 40% Milestone (Day 1)  
**Last Updated**: February 27, 2026
