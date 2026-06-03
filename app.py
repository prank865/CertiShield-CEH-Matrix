from flask import Flask, render_template, jsonify, request, make_response
import json
import os
import sqlite3
import uuid
from datetime import datetime

app = Flask(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
QUESTIONS_FILE = os.path.join(BASE_DIR, 'questions.json')
DATABASE_FILE = os.path.join(BASE_DIR, 'certishield_analytics.db')

def init_tracking_database():
    """Initializes the SQLite schema to track user identities and live exam sessions."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Table to store student names and registration details
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            registered_at TEXT NOT NULL
        )
    ''')
    
    # Table to track live states, question progress, scores, and status metrics
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exam_attempts (
            attempt_id TEXT PRIMARY KEY,
            user_id TEXT,
            questions_completed INTEGER DEFAULT 0,
            total_correct INTEGER DEFAULT 0,
            status TEXT DEFAULT 'IN_PROGRESS',
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    conn.commit()
    conn.close()

def load_database_records():
    if not os.path.exists(QUESTIONS_FILE):
        return []
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as file:
            return json.load(file)
    except (json.JSONDecodeError, IOError):
        return []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/v1/questions', methods=['GET'])
def get_questions():
    records = load_database_records()
    return jsonify({"status": "success", "total_count": len(records), "data": records})

@app.route('/api/v1/register', methods=['POST'])
def register_student():
    """Registers a student's session identity before starting the evaluation matrix."""
    payload = request.json
    full_name = payload.get('name')
    email = payload.get('email')
    
    if not full_name or not email:
        return jsonify({"status": "error", "message": "Missing identity constraints."}), 400
        
    user_id = str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Insert new user track record
    cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (user_id, full_name, email, timestamp))
    # Initialize a live exam attempt state row set to IN_PROGRESS
    cursor.execute("INSERT INTO exam_attempts VALUES (?, ?, 0, 0, 'IN_PROGRESS', ?, ?)", 
                   (attempt_id, user_id, timestamp, timestamp))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "status": "success",
        "user_id": user_id,
        "attempt_id": attempt_id
    })

@app.route('/api/v1/telemetry/update', methods=['POST'])
def update_telemetry_stream():
    """Receives live heartbeats from front-end to log progress positions or mid-exam abandonment."""
    payload = request.json
    attempt_id = payload.get('attempt_id')
    completed_count = payload.get('questions_completed')
    correct_count = payload.get('total_correct')
    status = payload.get('status', 'IN_PROGRESS') # Can be 'IN_PROGRESS' or 'COMPLETED'
    timestamp = datetime.utcnow().isoformat()
    
    if not attempt_id:
        return jsonify({"status": "error", "message": "Missing validation tracking token."}), 400
        
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE exam_attempts 
        SET questions_completed = ?, total_correct = ?, status = ?, updated_at = ?
        WHERE attempt_id = ?
    ''', (completed_count, correct_count, status, timestamp, attempt_id))
    
    conn.commit()
    conn.close()
    return jsonify({"status": "telemetry_logged"})

@app.route('/admin/dashboard')
def admin_portal():
    """A secure diagnostic endpoint displaying candidate attempts, dropouts, and scores."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Query linking user data alongside attempt status tracking fields
    cursor.execute('''
        SELECT u.full_name, u.email, e.questions_completed, e.total_correct, e.status, e.started_at, e.updated_at
        FROM users u
        JOIN exam_attempts e ON u.user_id = e.user_id
        ORDER BY e.updated_at DESC
    ''')
    records = cursor.fetchall()
    conn.close()
    
    # Render dynamic monitoring board interface directly
    html_template = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>CertiShield Admin Core Console</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-950 text-gray-100 p-8">
        <div class="max-w-6xl mx-auto space-y-6">
            <h1 class="text-3xl font-extrabold text-indigo-400">Candidate Evaluation Surveillance Control Dashboard</h1>
            <p class="text-gray-400 text-sm">Real-time connection verification metrics detailing mid-exam dropouts and full certification completions.</p>
            <div class="overflow-x-auto bg-gray-900 border border-gray-800 rounded-xl">
                <table class="w-full text-left text-sm">
                    <thead class="bg-gray-800 text-gray-400 uppercase text-xs">
                        <tr>
                            <th class="p-4">Candidate Name</th>
                            <th class="p-4">Email Address</th>
                            <th class="p-4">Progress Vector</th>
                            <th class="p-4">Total Score</th>
                            <th class="p-4">Session Status</th>
                            <th class="p-4">Last Event Window</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-800">
                        {% for row in records %}
                        <tr class="hover:bg-gray-800/40">
                            <td class="p-4 font-semibold text-white">{{ row['full_name'] }}</td>
                            <td class="p-4 font-mono text-gray-300">{{ row['email'] }}</td>
                            <td class="p-4">{{ row['questions_completed'] }} / 100</td>
                            <td class="p-4 text-indigo-400 font-bold">{{ row['total_correct'] }} Correct</td>
                            <td class="p-4">
                                {% if row['status'] == 'COMPLETED' %}
                                <span class="bg-emerald-500/20 text-emerald-400 px-2.5 py-1 rounded text-xs font-bold border border-emerald-500/30">Concluded</span>
                                {% else %}
                                <span class="bg-amber-500/20 text-amber-400 px-2.5 py-1 rounded text-xs font-bold border border-amber-500/30 animate-pulse">Abandonded / Testing</span>
                                {% endif %}
                            </td>
                            <td class="p-4 text-xs font-mono text-gray-500">{{ row['updated_at'] }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html_template, records=records)

# Helper function to easily compile raw templates on single script deployment files
from flask import render_template_string

if __name__ == '__main__':
    import os
    # The cloud server will give us a dynamic port, or use 5000 as a backup
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)