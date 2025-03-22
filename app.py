from flask import Flask, render_template, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import os
import logging
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from io import BytesIO

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///production.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/entry', methods=['POST'])
def add_entry():
    data = request.json
    logger.debug(f"Received data: {data}")
    
    try:
        entry = ProductionEntry(
            timestamp=datetime.now(),
            line_number=data['line_number'],
            from_time=datetime.strptime(data['from_time'], '%H:%M').time(),
            to_time=datetime.strptime(data['to_time'], '%H:%M').time(),
            planned=data['planned'],
            actual=data['actual'],
            total_loss_time=data.get('total_loss_time', 0)  # Make total_loss_time optional with default 0
        )
        
        for loss_data in data.get('losses', []):  # Make losses optional with default empty list
            loss = LossEntry(
                reason=loss_data['reason'],
                loss_time=loss_data['loss_time'],
                remarks=loss_data.get('remarks', '')
            )
            entry.losses.append(loss)
        
        db.session.add(entry)
        db.session.commit()
        logger.debug("Entry added successfully")
        return jsonify({'message': 'Entry added successfully'})
    
    except Exception as e:
        logger.error(f"Error adding entry: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

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
            for loss_data in data.get('losses', []):  # Make losses optional with default empty list
                loss = LossEntry(
                    reason=loss_data['reason'],
                    loss_time=loss_data['loss_time'],
                    remarks=loss_data.get('remarks', '')
                )
                entry.losses.append(loss)
            
            db.session.commit()
            logger.debug("Entry updated successfully")
            return jsonify({'message': 'Entry updated successfully'})
        
        except Exception as e:
            logger.error(f"Error updating entry: {str(e)}")
            db.session.rollback()
            return jsonify({'error': str(e)}), 400

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
    
    normal_style = styles['Normal']
    small_style = ParagraphStyle(
        'Small',
        parent=styles['Normal'],
        fontSize=8,
        leading=10
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
            
            # Loss details
            if daily_data['losses']:
                elements.append(Paragraph("Loss Details:", heading2_style))
                
                for reason, loss_data in daily_data['losses'].items():
                    # Loss reason and total time
                    elements.append(Paragraph(
                        f"<b>{reason}</b>: Total {loss_data['total_time']} minutes",
                        normal_style
                    ))
                    
                    # Loss occurrences with time ranges and remarks
                    for occurrence in loss_data['occurrences']:
                        occurrence_text = (
                            f"• Time: {occurrence['time_range']}, "
                            f"Duration: {occurrence['loss_time']} min"
                        )
                        if occurrence['remarks']:
                            occurrence_text += f"<br/>  Remarks: {occurrence['remarks']}"
                        
                        elements.append(Paragraph(occurrence_text, small_style))
                    
                    elements.append(Spacer(1, 10))
            
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

if __name__ == '__main__':
    app.run(debug=True)
