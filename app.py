from flask import Flask, render_template, request, redirect, session, url_for, flash
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import google.generativeai as genai
import img2pdf
import fitz  # PyMuPDF
from PIL import Image

# ---------- CONFIGURATION ----------
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Important for session

# ✅ Setup folders
DB_FOLDER = 'db'
DATABASE = os.path.join(DB_FOLDER, 'database.db')
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

# ✅ Ensure folders exist
os.makedirs(DB_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ✅ Gemini API key
genai.configure(api_key="AIzaSyCdIAKn4sl9OBeVSkKvcZoRNVhONQUTwk0")

# ---------- DATABASE SETUP ----------
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            content TEXT,
            file_path TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS qa_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            question TEXT,
            answer TEXT
        )''')
        conn.commit()

# ✅ Initialize database only if it doesn't exist
if not os.path.exists(DATABASE):
    init_db()

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------- ROUTES ----------
@app.route('/')
def index():
    return redirect('/login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        with get_db_connection() as conn:
            try:
                conn.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, password))
                conn.commit()
                flash('Registration successful. Please log in.', 'success')
                return redirect('/login')
            except sqlite3.IntegrityError:
                flash('Email already exists.', 'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        with get_db_connection() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ? AND password = ?", (email, password)).fetchone()
        if user:
            session['user_id'] = user['id']
            session['name'] = user['name']
            return redirect('/dashboard')
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('dashboard.html')

# ---------- Gemini Doubt Solver ----------
chat_sessions = {}

@app.route('/doubt_solver', methods=['GET', 'POST'])
def doubt_solver():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    question = None
    answer = None
    image_url = None
    chat_id = request.args.get('chat_id')

    if user_id not in chat_sessions:
        model = genai.GenerativeModel("gemini-1.5-flash")
        chat_sessions[user_id] = model.start_chat()

    chat = chat_sessions[user_id]

    if chat_id:
        with get_db_connection() as conn:
            chat_data = conn.execute(
                'SELECT question, answer FROM qa_history WHERE id = ? AND user_id = ?',
                (chat_id, user_id)
            ).fetchone()
            if chat_data:
                question = chat_data['question']
                answer = chat_data['answer']
    elif request.method == 'POST':
        question = request.form['question']
        image = request.files.get('image')

        if image and allowed_file(image.filename):
            filename = secure_filename(image.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(filepath)
            image_url = url_for('static', filename='uploads/' + filename)

        try:
            prompt = f"""
Please explain the following question in a beginner-friendly, clear format.

✅ Format Requirements:
- Answer in a clean **step-by-step format**
- Use clear numbering (e.g., 1., 2., 3.)
- Start each step on a **new line**
- No long paragraphs

🧠 Question:
{question}
"""
            response = chat.send_message(prompt)
            answer = response.text
            with get_db_connection() as conn:
                conn.execute(
                    'INSERT INTO qa_history (user_id, question, answer) VALUES (?, ?, ?)',
                    (user_id, question, answer)
                )
                conn.commit()
        except Exception as e:
            answer = f"❌ Error: {str(e)}"

    with get_db_connection() as conn:
        history = conn.execute(
            'SELECT * FROM qa_history WHERE user_id = ? ORDER BY id DESC',
            (user_id,)
        ).fetchall()

    return render_template('doubt_solver.html', question=question, answer=answer, image_url=image_url, history=history)

@app.route('/delete_chat/<int:qa_id>', methods=['POST'])
def delete_chat(qa_id):
    if 'user_id' not in session:
        return redirect('/login')
    with get_db_connection() as conn:
        conn.execute('DELETE FROM qa_history WHERE id = ? AND user_id = ?', (qa_id, session['user_id']))
        conn.commit()
    return redirect(url_for('doubt_solver'))

@app.route('/calculator', methods=['GET', 'POST'])
def calculator():
    result = ''
    expression = ''
    if request.method == 'POST':
        button = request.form['button']
        expression = request.form.get('expression', '')
        if button == 'AC':
            expression = ''
        elif button == 'DEL':
            expression = expression[:-1]
        elif button == '=':
            try:
                from math import sin, cos, tan, sqrt, log, pi, e
                result = str(eval(expression.replace('pi', str(pi)).replace('e', str(e))))
                expression = result
            except:
                result = "Error"
                expression = ''
        else:
            expression += button
    return render_template('calculator.html', result=expression)

@app.route('/exam_planner', methods=['GET', 'POST'])
def exam_planner():
    if 'exams' not in session:
        session['exams'] = []
    if request.method == 'POST':
        subject = request.form['subject']
        date = request.form['date']
        session['exams'].append({'subject': subject, 'date': date})
        session.modified = True
    return render_template('exam_planner.html', exams=session['exams'])

@app.route('/delete_exam', methods=['POST'])
def delete_exam():
    subject = request.form['subject']
    date = request.form['date']
    if 'exams' in session:
        session['exams'] = [exam for exam in session['exams'] if not (exam['subject'] == subject and exam['date'] == date)]
        session.modified = True
    return redirect(url_for('exam_planner'))

@app.route('/study_plan', methods=['GET', 'POST'])
def study_plan():
    plan = []
    if request.method == 'POST':
        try:
            days = int(request.form['days'])
            time_from = request.form['time_from']
            time_to = request.form['time_to']
            subjects_raw = request.form['subjects']
            subjects = [s.strip() for s in subjects_raw.split(',') if s.strip()]
            total_subjects = len(subjects)
            current_day = datetime.today()
            subject_index = 0
            for day in range(days):
                subject = subjects[subject_index]
                plan.append({
                    'date': (current_day + timedelta(days=day)).strftime('%Y-%m-%d'),
                    'subject': subject,
                    'time': f"{time_from} - {time_to}"
                })
                subject_index = (subject_index + 1) % total_subjects
        except Exception as e:
            plan = [{'date': 'Error', 'subject': 'Invalid Input', 'time': str(e)}]
    return render_template('study_plan.html', plan=plan)

@app.route('/study_reminder', methods=['GET', 'POST'])
def study_reminder():
    if 'reminders' not in session:
        session['reminders'] = []

    if request.method == 'POST':
        subject = request.form['subject']
        date = request.form['date']
        time = request.form['time']
        session['reminders'].append({'subject': subject, 'date': date, 'time': time})
        session.modified = True
        return redirect(url_for('study_reminder'))

    return render_template('study_reminder.html', reminders=session['reminders'])

@app.route('/delete_reminder', methods=['POST'])
def delete_reminder():
    subject = request.form['subject']
    date = request.form['date']
    time = request.form['time']
    if 'reminders' in session:
        session['reminders'] = [
            r for r in session['reminders']
            if not (r['subject'] == subject and r['date'] == date and r['time'] == time)
        ]
        session.modified = True
    return redirect(url_for('study_reminder'))

@app.route('/notes', methods=['GET', 'POST'])
def notes():
    if 'user_id' not in session:
        return redirect('/login')
    user_id = session['user_id']
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        file = request.files.get('file')
        file_path = None
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
        with get_db_connection() as conn:
            conn.execute('INSERT INTO notes (user_id, title, content, file_path) VALUES (?, ?, ?, ?)',
                         (user_id, title, content, file_path))
            conn.commit()
        return redirect(url_for('notes'))

    with get_db_connection() as conn:
        notes = conn.execute('SELECT * FROM notes WHERE user_id = ?', (user_id,)).fetchall()
    return render_template('notes.html', notes=notes)

@app.route('/delete_note/<int:note_id>')
def delete_note(note_id):
    with get_db_connection() as conn:
        conn.execute('DELETE FROM notes WHERE id = ?', (note_id,))
        conn.commit()
    return redirect(url_for('notes'))

@app.route('/pdf_editor', methods=['GET', 'POST'])
def pdf_editor():
    message = None
    pdf_generated_path = None
    if request.method == 'POST':
        title = request.form.get('title') or "my_pdf"
        uploaded_images = request.files.getlist('images')
        image_paths = []
        for image in uploaded_images:
            if image and image.filename:
                filename = secure_filename(image.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image.save(filepath)
                image_paths.append(filepath)
        if image_paths:
            pdf_name = f"{title.replace(' ', '_')}_{len(os.listdir(app.config['UPLOAD_FOLDER']))}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_name)
            with open(output_path, "wb") as f:
                f.write(img2pdf.convert(image_paths))
            pdf_generated_path = url_for('static', filename=f'uploads/{pdf_name}')
            message = "✅ PDF created successfully!"
    pdfs = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if f.endswith('.pdf')]
    return render_template("pdf_editor.html", message=message, pdf_generated_path=pdf_generated_path, pdfs=pdfs)

@app.route('/delete_pdf/<filename>')
def delete_pdf(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    return redirect(url_for('pdf_editor'))

# ---------- MAIN ----------
if __name__ == '__main__':
    app.run(debug=True)
