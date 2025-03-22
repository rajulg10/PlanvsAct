# Production Plan vs Actual Tracker

A Flask application to track and compare planned vs actual production, with support for managing production losses.

## Features

- Track planned vs actual production for multiple lines
- Record and manage production losses with reasons and remarks
- Generate daily and weekly PDF reports
- Visual dashboard with real-time updates
- Loss tracking with time ranges and detailed remarks

## Installation

1. Clone the repository:
```bash
git clone https://github.com/rajulg10/PlanvsAct.git
cd PlanvsAct
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
```
Edit `.env` with your configuration:
- Set `SECRET_KEY` for Flask
- Configure `DATABASE_URL` for PostgreSQL connection

## Database Setup

1. Create a PostgreSQL database
2. Update the `DATABASE_URL` in your `.env` file:
```
DATABASE_URL=postgresql://username:password@localhost:5432/planvsactual
```

3. Initialize the database:
```python
from app import db
db.create_all()
```

## Running the Application

```bash
flask run
```

The application will be available at `http://localhost:5000`

## Deployment on Railway

1. Install Railway CLI:
```bash
# macOS
brew install railway

# Windows
scoop install railway

# Linux
curl -fsSL https://railway.app/install.sh | sh
```

2. Login to Railway:
```bash
railway login
```

3. Initialize Railway project:
```bash
railway init
```

4. Create PostgreSQL database:
```bash
railway add
```
Select PostgreSQL from the list of plugins.

5. Deploy the application:
```bash
railway up
```

6. Set environment variables:
```bash
railway variables set SECRET_KEY=your-secret-key-here
```

The application will be automatically deployed and a URL will be provided.

### Monitoring and Logs

- View logs: `railway logs`
- Check status: `railway status`
- Open dashboard: `railway open`

## License

MIT License
