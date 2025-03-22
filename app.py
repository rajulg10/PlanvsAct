import os
from datetime import datetime, date, timedelta
from io import BytesIO
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, jsonify, send_file, g
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure logging
if os.getenv('FLASK_ENV') == 'production':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s - [in %(pathname)s:%(lineno)d]'
    )
else:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/planvsactual.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s - [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('PlanVsActual startup')

# Database Configuration
database_url = os.getenv('DATABASE_URL')
if not database_url:
    database_url = os.getenv('RAILWAY_DATABASE_URL')  # Try Railway's specific variable
if not database_url:
    database_url = 'sqlite:///production.db'  # Fallback to SQLite

# Convert postgres:// to postgresql:// if necessary
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key')
app.config['SQLALCHEMY_POOL_SIZE'] = 10
app.config['SQLALCHEMY_MAX_OVERFLOW'] = 10
app.config['SQLALCHEMY_POOL_RECYCLE'] = 300
app.config['SQLALCHEMY_POOL_TIMEOUT'] = 30

# Log database configuration (without credentials)
db_url_parts = database_url.split('@')
if len(db_url_parts) > 1:
    safe_db_url = f"...@{db_url_parts[-1]}"
else:
    safe_db_url = database_url
app.logger.info(f"Database URL configured as: {safe_db_url}")

db = SQLAlchemy(app)

class ProductionEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False)
    line_number = db.Column(db.Integer, nullable=False)  # Line 1 or Line 2
    from_time = db.Column(db.Time, nullable=False)
    to_time = db.Column(db.Time, nullable=False)
    planned = db.Column(db.Integer, nullable=False)
    actual = db.Column(db.Integer, nullable=False)
    total_loss_time = db.Column(db.Integer, nullable=False, default=0)  # Total loss time in minutes
    losses = db.relationship('LossEntry', backref='production_entry', lazy=True, cascade='all, delete-orphan')

class LossEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    production_entry_id = db.Column(db.Integer, db.ForeignKey('production_entry.id'), nullable=False)
    reason = db.Column(db.String(50), nullable=False)
    loss_time = db.Column(db.Integer, nullable=False)  # Loss time in minutes
    remarks = db.Column(db.Text)

# Initialize database tables
def init_db():
    try:
        with app.app_context():
            # Test database connection first
            if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
                db.session.execute(text('SELECT sqlite_version()'))
            else:
                db.session.execute(text('SELECT 1'))
            db.session.commit()
            
            # Create tables
            db.create_all()
            app.logger.info("Database tables created successfully")
            return True
    except Exception as e:
        app.logger.error(f"Database initialization failed: {str(e)}")
        return False

# Database connection handling
def get_db():
    if not hasattr(g, 'db_session'):
        g.db_session = db.session
    try:
        # Test connection with database-agnostic query
        g.db_session.execute(text('SELECT 1'))
        g.db_session.commit()
    except Exception as e:
        app.logger.error(f"Database connection error: {str(e)}")
        g.db_session.rollback()
        # Close and remove the session
        g.db_session.close()
        delattr(g, 'db_session')
        raise

@app.before_request
def before_request():
    try:
        get_db()
    except Exception:
        return jsonify({
            'status': 'error',
            'message': 'Database connection error',
            'timestamp': datetime.now().isoformat()
        }), 503

@app.teardown_appcontext
def teardown_db(exception=None):
    db_session = getattr(g, 'db_session', None)
    if db_session is not None:
        db_session.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/entry', methods=['POST'])
def add_entry():
    try:
        data = request.json
        app.logger.info(f"Received production entry for Line {data.get('line_number')}")
        
        # Validate required fields
        required_fields = ['line_number', 'from_time', 'to_time', 'planned', 'actual']
        for field in required_fields:
            if field not in data:
                app.logger.error(f"Missing required field: {field}")
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Create production entry
        entry = ProductionEntry(
            timestamp=datetime.now(),
            line_number=data['line_number'],
            from_time=datetime.strptime(data['from_time'], '%H:%M').time(),
            to_time=datetime.strptime(data['to_time'], '%H:%M').time(),
            planned=data['planned'],
            actual=data['actual'],
            total_loss_time=data.get('total_loss_time', 0)
        )
        
        # Add losses if present
        if 'losses' in data:
            app.logger.info(f"Processing {len(data['losses'])} loss entries")
            for loss_data in data['losses']:
                loss = LossEntry(
                    reason=loss_data['reason'],
                    loss_time=loss_data['loss_time'],
                    remarks=loss_data.get('remarks', '')
                )
                entry.losses.append(loss)
        
        db.session.add(entry)
        db.session.commit()
        app.logger.info(f"Successfully added entry ID: {entry.id}")
        
        return jsonify({'success': True, 'id': entry.id})
    except Exception as e:
        app.logger.error(f"Error adding entry: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/entry/<int:entry_id>', methods=['GET', 'PUT'])
def manage_entry(entry_id):
    entry = ProductionEntry.query.get_or_404(entry_id)
    
    if request.method == 'GET':
        return jsonify({
            'id': entry.id,
            'line_number': entry.line_number,
            'from_time': entry.from_time.strftime('%H:%M'),
            'to_time': entry.to_time.strftime('%H:%M'),
            'planned': entry.planned,
            'actual': entry.actual,
            'total_loss_time': entry.total_loss_time,
            'losses': [{
                'reason': loss.reason,
                'loss_time': loss.loss_time,
                'remarks': loss.remarks
            } for loss in entry.losses]
        })
    
    else:  # PUT
        data = request.json
        try:
            entry.line_number = data['line_number']
            entry.from_time = datetime.strptime(data['from_time'], '%H:%M').time()
            entry.to_time = datetime.strptime(data['to_time'], '%H:%M').time()
            entry.planned = data['planned']
            entry.actual = data['actual']
            entry.total_loss_time = data.get('total_loss_time', 0)  # Make total_loss_time optional with default 0
            
            # Remove existing losses
            for loss in entry.losses:
                db.session.delete(loss)
            
            # Add new losses
            if 'losses' in data:
                app.logger.info(f"Processing {len(data['losses'])} loss entries")
                for loss_data in data['losses']:
                    loss = LossEntry(
                        reason=loss_data['reason'],
                        loss_time=loss_data['loss_time'],
                        remarks=loss_data.get('remarks', '')
                    )
                    entry.losses.append(loss)
            
            db.session.commit()
            app.logger.info(f"Successfully updated entry ID: {entry.id}")
            return jsonify({'success': True, 'id': entry.id})
        
        except Exception as e:
            app.logger.error(f"Error updating entry: {str(e)}")
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

@app.route('/api/daily-report')
def get_daily_report():
    today = date.today()
    entries = ProductionEntry.query.filter(
        db.func.date(ProductionEntry.timestamp) == today
    ).order_by(ProductionEntry.from_time).all()
    
    return jsonify([{
        'id': entry.id,
        'line_number': entry.line_number,
        'from_time': entry.from_time.strftime('%H:%M'),
        'to_time': entry.to_time.strftime('%H:%M'),
        'planned': entry.planned,
        'actual': entry.actual,
        'total_loss_time': entry.total_loss_time,
        'losses': [{
            'reason': loss.reason,
            'loss_time': loss.loss_time,
            'remarks': loss.remarks
        } for loss in entry.losses]
    } for entry in entries])

def generate_report_data(start_date, end_date):
    entries = ProductionEntry.query.filter(
        db.func.date(ProductionEntry.timestamp).between(start_date, end_date)
    ).order_by(ProductionEntry.line_number, ProductionEntry.timestamp).all()
    
    # Group entries by line and date
    report_data = {1: {}, 2: {}}
    for entry in entries:
        entry_date = entry.timestamp.date()
        line_data = report_data[entry.line_number]
        
        if entry_date not in line_data:
            line_data[entry_date] = {
                'planned': 0,
                'actual': 0,
                'total_loss_time': 0,
                'losses': {}
            }
        
        daily_data = line_data[entry_date]
        daily_data['planned'] += entry.planned
        daily_data['actual'] += entry.actual
        daily_data['total_loss_time'] += entry.total_loss_time
        
        # Group losses by reason with time ranges and remarks
        for loss in entry.losses:
            if loss.reason not in daily_data['losses']:
                daily_data['losses'][loss.reason] = {
                    'total_time': 0,
                    'occurrences': []
                }
            
            loss_data = daily_data['losses'][loss.reason]
            loss_data['total_time'] += loss.loss_time
            loss_data['occurrences'].append({
                'time_range': f"{entry.from_time.strftime('%H:%M')}-{entry.to_time.strftime('%H:%M')}",
                'loss_time': loss.loss_time,
                'remarks': loss.remarks
            })
    
    return report_data

@app.route('/api/report/<report_type>')
def generate_report(report_type):
    today = date.today()
    
    if report_type == 'daily':
        start_date = end_date = today
    else:  # weekly
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    
    report_data = generate_report_data(start_date, end_date)
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30
    )
    title = f"Production Report ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})"
    elements.append(Paragraph(title, title_style))
    
    # Styles for the report
    heading2_style = ParagraphStyle(
        'Heading2',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=12
    )
    
    # Process each line
    for line_number in [1, 2]:
        elements.append(Paragraph(f"Line {line_number}", heading2_style))
        line_data = report_data[line_number]
        
        for entry_date in sorted(line_data.keys()):
            daily_data = line_data[entry_date]
            
            # Daily summary table
            data = [
                ['Date', 'Planned', 'Actual', 'Total Loss Time'],
                [
                    entry_date.strftime('%Y-%m-%d'),
                    str(daily_data['planned']),
                    str(daily_data['actual']),
                    f"{daily_data['total_loss_time']} min"
                ]
            ]
            
            t = Table(data, colWidths=[100, 100, 100, 100])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(t)
            elements.append(Spacer(1, 20))
            
            # Loss details table
            if daily_data['losses']:
                elements.append(Paragraph("Loss Details:", heading2_style))
                
                # Create loss details table
                loss_table_data = [['Loss Reason', 'Time Range', 'Duration', 'Remarks']]
                
                for reason, loss_data in daily_data['losses'].items():
                    for occurrence in loss_data['occurrences']:
                        loss_table_data.append([
                            reason,
                            occurrence['time_range'],
                            f"{occurrence['loss_time']} min",
                            occurrence['remarks'] or ''
                        ])
                    
                    # Add a summary row for this reason
                    loss_table_data.append([
                        f"Total for {reason}",
                        '',
                        f"{loss_data['total_time']} min",
                        ''
                    ])
                
                # Create the table with specific column widths
                loss_table = Table(loss_table_data, colWidths=[150, 100, 80, 170])
                
                # Style the table
                table_style = [
                    # Header row styling
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    
                    # Content styling
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                    ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    
                    # Align durations to center
                    ('ALIGN', (2, 0), (2, -1), 'CENTER'),
                ]
                
                # Add alternating row colors and total row styling
                for i in range(len(loss_table_data)):
                    if i > 0:  # Skip header row
                        if 'Total for' in loss_table_data[i][0]:
                            # Style for total rows
                            table_style.extend([
                                ('BACKGROUND', (0, i), (-1, i), colors.lightgrey),
                                ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
                                ('LINEABOVE', (0, i), (-1, i), 1, colors.grey),
                                ('LINEBELOW', (0, i), (-1, i), 1, colors.grey),
                            ])
                        elif i % 2 == 1:  # Alternating row colors
                            table_style.append(('BACKGROUND', (0, i), (-1, i), colors.whitesmoke))
                
                loss_table.setStyle(TableStyle(table_style))
                elements.append(loss_table)
                elements.append(Spacer(1, 20))
            
            elements.append(Spacer(1, 20))
        
        elements.append(Spacer(1, 30))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    return send_file(
        buffer,
        download_name=f'production_report_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}.pdf',
        mimetype='application/pdf'
    )

# Health check endpoint
@app.route('/health')
def health_check():
    health_info = {
        'status': 'unhealthy',
        'timestamp': datetime.now().isoformat(),
        'components': {
            'database': {
                'status': 'unhealthy',
                'details': None
            }
        }
    }
    
    try:
        # Check database connection using a database-agnostic query
        if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
            # SQLite-specific version query
            result = db.session.execute(text('SELECT sqlite_version()')).scalar()
            db_type = 'sqlite'
        else:
            # PostgreSQL version query
            result = db.session.execute(text('SELECT version()')).scalar()
            db_type = 'postgresql'
        
        db.session.commit()
        
        health_info['components']['database'] = {
            'status': 'healthy',
            'details': {
                'version': result,
                'type': db_type,
                'uri': safe_db_url  # Using the safe URL we logged earlier
            }
        }
        health_info['status'] = 'healthy'
        return jsonify(health_info)
    except Exception as e:
        app.logger.error(f"Health check failed: {str(e)}")
        health_info['components']['database']['details'] = str(e)
        return jsonify(health_info), 500

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    app.logger.error(f"Page not found: {request.url}")
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Server Error: {error}")
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500

# Request logging middleware
@app.before_request
def log_request_info():
    if not request.path == '/health':  # Skip logging health checks
        app.logger.info(f"Request: {request.method} {request.path} from {request.remote_addr}")

@app.after_request
def log_response_info(response):
    if not request.path == '/health':  # Skip logging health checks
        app.logger.info(f"Response: {response.status} to {request.method} {request.path}")
    return response

# Initialize database on startup
if init_db():
    app.logger.info("Application started successfully with database connection")
else:
    app.logger.error("Application started but database initialization failed")

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5010))
    app.run(host='0.0.0.0', port=port)
