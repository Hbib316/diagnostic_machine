from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import paho.mqtt.client as mqtt
import json
from threading import Thread
from ml_service import predict_machine_fault
import sqlite3
import bcrypt
from datetime import datetime

app = Flask(__name__)
app.secret_key = "supersecretkey123"

# Store latest machine data
latest_data = {
    "parametres_machine": [0, 0, 0, 0, 0],
    "timestamp": 0,
    "ml_prediction": {"fault_probability": 0.0, "is_fault": False, "model_status": "Initializing"}
}

# MQTT configuration
MQTT_BROKER = "d736909d58a34fa6930bc5f9398c1c1b.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_TOPIC = "diagnostic_machine"
MQTT_USER = "habib"
MQTT_PASSWORD = "Password2"

# SQLite database files
HISTORY_DB = "history.db"
USERS_DB = "users.db"

# Initialize databases
def init_history_db():
    conn = sqlite3.connect(HISTORY_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS machine_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            vibration INTEGER,
            temperature INTEGER,
            pressure INTEGER,
            rms INTEGER,
            mean_temp INTEGER,
            fault_probability REAL,
            is_fault BOOLEAN,
            model_status TEXT
        )
    ''')
    conn.commit()
    conn.close()

def init_users_db():
    conn = sqlite3.connect(USERS_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    pre_created_users = [
        ("admin", "password123"),
        ("user", "test123")
    ]
    for username, plain_password in pre_created_users:
        cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
        if not cursor.fetchone():
            hashed_password = bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt())
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
    conn.commit()
    conn.close()

# Insert data into history database
def insert_history(data, prediction):
    conn = sqlite3.connect(HISTORY_DB)
    cursor = conn.cursor()
    
    # Convert timestamp to formatted string
    if isinstance(data["timestamp"], (int, float)):
        timestamp_str = datetime.fromtimestamp(data["timestamp"]).strftime('%Y-%m-%d %H:%M:%S')
    else:
        timestamp_str = data["timestamp"]
    
    cursor.execute('''
        INSERT INTO machine_history (
            timestamp, vibration, temperature, pressure, rms, mean_temp,
            fault_probability, is_fault, model_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        timestamp_str,
        data["parametres_machine"][0],
        data["parametres_machine"][1],
        data["parametres_machine"][2],
        data["parametres_machine"][3],
        data["parametres_machine"][4],
        prediction["fault_probability"],
        prediction["is_fault"],
        prediction["model_status"]
    ))
    conn.commit()
    conn.close()

# MQTT callback when connected
def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT!" if rc == 0 else f"MQTT connection failed: {rc}")
    client.subscribe(MQTT_TOPIC)

# MQTT callback when message received
def on_message(client, userdata, msg):
    global latest_data
    data = json.loads(msg.payload.decode())
    params = data.get("parametres_machine", [])
    if len(params) == 5:
        prediction = predict_machine_fault(params)
        latest_data = {
            "parametres_machine": params,
            "timestamp": data.get("timestamp", 0),
            "ml_prediction": prediction
        }
        insert_history(latest_data, prediction)
        print(f"Received: {params}, Fault: {prediction['is_fault']}, Prob: {prediction['fault_probability']:.2%}")

# Setup MQTT client
def setup_mqtt():
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.tls_set()
    client.connect(MQTT_BROKER, MQTT_PORT)
    client.loop_forever()

# Login check decorator
def login_required(f):
    def wrap(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# Filtre de template pour formater les timestamps
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M:%S'):
    try:
        if isinstance(value, (int, float)):
            if value > 1e10:
                value = value / 1000
            return datetime.fromtimestamp(value).strftime(format)
        elif isinstance(value, str):
            # Si c'est déjà une chaîne formatée, la retourner telle quelle
            return value
        return str(value)
    except (ValueError, TypeError):
        return "Format invalide"

# Route pour supprimer l'historique
@app.route('/clear_history', methods=['POST'])
@login_required
def clear_history():
    try:
        conn = sqlite3.connect(HISTORY_DB)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM machine_history")
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Historique supprimé avec succès"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur: {str(e)}"})

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = sqlite3.connect(USERS_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()
        if user and bcrypt.checkpw(password.encode('utf-8'), user[0]):
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Nom d'utilisateur ou mot de passe incorrect")
    return render_template('login.html', error=None)

# Logout route
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# Route for main page
@app.route('/')
@login_required
def index():
    return render_template('index.html', data=latest_data)

# Route for latest data
@app.route('/data')
@login_required
def get_data():
    return jsonify(latest_data)

# Route for history page
@app.route('/history')
@login_required
def history():
    conn = sqlite3.connect(HISTORY_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM machine_history ORDER BY timestamp DESC")
    history_data = cursor.fetchall()
    conn.close()
    history_list = [
        {
            "timestamp": row[1],
            "parametres_machine": [row[2], row[3], row[4], row[5], row[6]],
            "ml_prediction": {
                "fault_probability": row[7],
                "is_fault": row[8],
                "model_status": row[9]
            }
        } for row in history_data
    ]
    return render_template('history.html', history=history_list)

# API route for history data
@app.route('/history_data')
@login_required
def get_history_data():
    conn = sqlite3.connect(HISTORY_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM machine_history ORDER BY timestamp DESC")
    history_data = cursor.fetchall()
    conn.close()
    return jsonify([{
        "id": row[0],
        "timestamp": row[1],
        "parametres_machine": [row[2], row[3], row[4], row[5], row[6]],
        "ml_prediction": {
            "fault_probability": row[7],
            "is_fault": row[8],
            "model_status": row[9]
        }
    } for row in history_data])

if __name__ == '__main__':
    init_history_db()
    init_users_db()
    mqtt_thread = Thread(target=setup_mqtt)
    mqtt_thread.daemon = True
    mqtt_thread.start()
    app.run(host='0.0.0.0', port=5000, debug=True)