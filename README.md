# Production Plan vs Actual Tracker

A Flask web application to track and compare planned vs actual production across multiple production lines. The application helps monitor production efficiency by tracking losses and generating detailed reports.

## Features

- Track production data for multiple production lines
- Compare planned vs actual production
- Automatic loss tracking when actual production is less than planned
- Multiple loss entries with reasons and remarks
- Daily and weekly production reports
- Interactive dashboard with real-time updates
- PDF report generation

## Installation

1. Clone the repository:
```bash
git clone https://github.com/rajulg10/PlanvsAct.git
cd PlanvsAct
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
python app.py
```

The application will be available at `http://localhost:5000`

## Usage

1. Select a production line (Line 1 or Line 2)
2. Enter the time range, planned production, and actual production
3. If actual production is less than planned, the loss section will appear automatically
4. Add loss details with reasons and remarks
5. Save the entry to update the daily summary
6. Generate daily or weekly reports in PDF format

## Technologies Used

- Python
- Flask
- SQLAlchemy
- SQLite
- Bootstrap
- JavaScript
- ReportLab (for PDF generation)

## License

This project is licensed under the MIT License - see the LICENSE file for details.
