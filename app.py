from flask import Flask, render_template, jsonify, request, render_template_string
import json
import os
import psycopg2
from psycopg2.extras import DictCursor
import uuid
from datetime import datetime

app = Flask(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
QUESTIONS_FILE = os.path.join(BASE_DIR, 'questions.json')

# Grab the secure database URL provided by Render's backend parameters
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    """Establishes a connection to the permanent cloud PostgreSQL node."""
    if not DATABASE_URL:
        raise ValueError("CRITICAL CONFIG ERROR: DATABASE_URL environment variable is missing!")
    return psycopg2.connect(DATABASE_URL)

def init_tracking_database():
    """Initializes permanent relational tables inside the cloud PostgreSQL instance."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # User identity matrix tracking table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            registered_at TEXT NOT NULL
        )
    ''')
    
    # Permanent exam progress and telemetry score repository
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exam_attempts (
            attempt_id TEXT PRIMARY KEY,
            user_id TEXT REFERENCES users(user_id),
            exam_set TEXT DEFAULT 'Set A',
            questions_completed INTEGER DEFAULT 0,
            total_correct INTEGER DEFAULT 0,
            status TEXT DEFAULT 'IN_PROGRESS',
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    
    # Check if 'exam_set' column exists, if not add it (Migration protection)
    try:
        cursor.execute("ALTER TABLE exam_attempts ADD COLUMN exam_set TEXT DEFAULT 'Set A';")
    except psycopg2.errors.DuplicateColumn:
        pass
        
    conn.commit()
    cursor.close()
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
    target_set = request.args.get('set', 'Set A')
    
    # Filter the json items based on matching set criteria
    filtered_records = [q for q in records if q.get('set', 'Set A') == target_set]
    return jsonify({
        "status": "success", 
        "set": target_set,
        "total_count": len(filtered_records), 
        "data": filtered_records
    })

@app.route('/api/v1/register', methods=['POST'])
def register_student():
    payload = request.json
    if not payload:
        return jsonify({"status": "error", "message": "Missing request payload."}), 400
        
    full_name = payload.get('name')
    email = payload.get('email')
    chosen_set = payload.get('set', 'Set A')
    
    if not full_name or not email:
        return jsonify({"status": "error", "message": "Missing identity constraints."}), 400
        
    user_id = str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("INSERT INTO users (user_id, full_name, email, registered_at) VALUES (%s, %s, %s, %s)", 
                   (user_id, full_name, email, timestamp))
    
    cursor.execute("INSERT INTO exam_attempts (attempt_id, user_id, exam_set, questions_completed, total_correct, status, started_at, updated_at) VALUES (%s, %s, %s, 0, 0, 'IN_PROGRESS', %s, %s)", 
                   (attempt_id, user_id, chosen_set, timestamp, timestamp))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({
        "status": "success",
        "user_id": user_id,
        "attempt_id": attempt_id
    })

@app.route('/api/v1/telemetry/update', methods=['POST'])
def update_telemetry_stream():
    payload = request.json
    if not payload:
        return jsonify({"status": "error", "message": "Missing telemetry payload."}), 400

    attempt_id = payload.get('attempt_id')
    completed_count = payload.get('questions_completed', 0)
    correct_count = payload.get('total_correct', 0)
    status = payload.get('status', 'IN_PROGRESS')
    timestamp = datetime.utcnow().isoformat()
    
    if not attempt_id:
        return jsonify({"status": "error", "message": "Missing validation tracking token."}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE exam_attempts 
        SET questions_completed = %s, total_correct = %s, status = %s, updated_at = %s
        WHERE attempt_id = %s
    ''', (completed_count, correct_count, status, timestamp, attempt_id))
    
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "telemetry_logged"})

@app.route('/admin/dashboard')
def admin_portal():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute('''
        SELECT u.full_name, u.email, e.exam_set, e.questions_completed, e.total_correct, e.status, e.started_at, e.updated_at
        FROM users u
        JOIN exam_attempts e ON u.user_id = e.user_id
        ORDER BY e.updated_at DESC
    ''')
    records = cursor.fetchall()
    cursor.close()
    conn.close()
    
    html_template = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>CertiShield Admin Core Console</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-950 text-gray-100 p-8">
        <div class="max-w-6xl mx-auto space-y-6">
            <h1 class="text-3xl font-extrabold text-indigo-400">🛡️ CertiShield Production Surveillance Terminal</h1>
            <p class="text-gray-400 text-sm">Permanent Database Connectivity Status: Active. Monitoring live progress vectors filtered by custom exam subsets.</p>
            <div class="overflow-x-auto bg-gray-900 border border-gray-800 rounded-xl">
                <table class="w-full text-left text-sm">
                    <thead class="bg-gray-800 text-gray-400 uppercase text-xs">
                        <tr>
                            <th class="p-4">Candidate Name</th>
                            <th class="p-4">Email Address</th>
                            <th class="p-4">Exam Module</th>
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
                            <td class="p-4"><span class="bg-indigo-500/10 text-indigo-400 px-2 py-0.5 rounded text-xs border border-indigo-500/20 font-medium">{{ row['exam_set'] }}</span></td>
                            <td class="p-4">{{ row['questions_completed'] }} / 100</td>
                            <td class="p-4 text-indigo-400 font-bold">{{ row['total_correct'] }} Correct</td>
                            <td class="p-4">
                                {% if row['status'] == 'COMPLETED' %}
                                <span class="bg-emerald-500/20 text-emerald-400 px-2.5 py-1 rounded text-xs font-bold border border-emerald-500/30">Concluded</span>
                                {% else %}
                                <span class="bg-amber-500/20 text-amber-400 px-2.5 py-1 rounded text-xs font-bold border border-amber-500/30 animate-pulse">In Progress</span>
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

# Trigger initialization setup check automatically
if DATABASE_URL:
    try:
        init_tracking_database()
        print("PostgreSQL Schemas Checked and Synced Successfully.")
    except Exception as e:
        print(f"Database Initialization Error: {e}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)