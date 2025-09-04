from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import paho.mqtt.client as mqtt
import json
from threading import Thread, Lock
from ml_service import predict_machine_fault
import sqlite3
import bcrypt
from datetime import datetime
import time
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey123")

# Store latest machine data with thread safety
latest_data = {
    "parametres_machine": [0, 0, 0, 0, 0],
    "timestamp": 0,
    "ml_prediction": {"fault_probability": 0.0, "is_fault": False, "model_status": "Initializing"}
}
data_lock = Lock()

# MQTT configuration - Utilisez des variables d'environnement
MQTT_BROKER = os.environ.get("MQTT_BROKER", "d736909d58a34fa6930bc5f9398c1c1b.s1.eu.hivemq.cloud")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 8883))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "diagnostic_machine")
MQTT_USER = os.environ.get("MQTT_USER", "habib")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "Password2")

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
            timestamp REAL,
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
    # Insert pre-created users (only if they don't exist)
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
    cursor.execute('''
        INSERT INTO machine_history (
            timestamp, vibration, temperature, pressure, rms, mean_temp,
            fault_probability, is_fault, model_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data["timestamp"],
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
    try:
        data = json.loads(msg.payload.decode())
        params = data.get("parametres_machine", [])
        if len(params) == 5:
            prediction = predict_machine_fault(params)
            with data_lock:
                latest_data = {
                    "parametres_machine": params,
                    "timestamp": data.get("timestamp", time.time()),
                    "ml_prediction": prediction
                }
            insert_history(latest_data, prediction)
            print(f"Received: {params}, Fault: {prediction['is_fault']}, Prob: {prediction['fault_probability']:.2%}")
    except Exception as e:
        print(f"Error processing MQTT message: {e}")

# Setup and manage MQTT client with reconnection
class MQTTManager:
    def __init__(self):
        self.client = None
        self.connected = False
        self.setup_mqtt()

    def setup_mqtt(self):
        try:
            self.client = mqtt.Client()
            self.client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
            self.client.on_connect = on_connect
            self.client.on_message = on_message
            self.client.tls_set()
            
            # Set up callback for connection loss
            self.client.on_disconnect = self.on_disconnect
            
            print(f"Connecting to MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
            self.connected = True
            print("MQTT client started successfully")
            
        except Exception as e:
            print(f"Failed to setup MQTT: {e}")
            self.connected = False

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        print(f"MQTT disconnected with code: {rc}")
        if rc != 0:
            print("Unexpected disconnection, attempting to reconnect...")
            time.sleep(5)
            self.setup_mqtt()

    def is_connected(self):
        return self.connected

# Global MQTT manager
mqtt_manager = None

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
        # Si c'est un timestamp numérique
        if isinstance(value, (int, float)):
            if value > 1e10:  # Si c'est en millisecondes
                value = value / 1000
            return datetime.fromtimestamp(value).strftime(format)
        # Si c'est déjà une chaîne de caractères, retournez-la telle quelle
        return value
    except (ValueError, TypeError):
        return "Format invalide"

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
    return render_template('index.html', data=latest_data, mqtt_connected=mqtt_manager.is_connected() if mqtt_manager else False)

# Route for latest data
@app.route('/data')
@login_required
def get_data():
    with data_lock:
        return jsonify(latest_data)

# Route for MQTT status
@app.route('/mqtt_status')
@login_required
def mqtt_status():
    return jsonify({"connected": mqtt_manager.is_connected() if mqtt_manager else False})

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

# Health check endpoint for Render
@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "mqtt_connected": mqtt_manager.is_connected() if mqtt_manager else False,
        "timestamp": time.time()
    })

if __name__ == '__main__':
    init_history_db()
    init_users_db()
    
    # Initialize MQTT manager
    mqtt_manager = MQTTManager()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)