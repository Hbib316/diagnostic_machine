from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import paho.mqtt.client as mqtt
import json
from threading import Thread, Lock
from ml_service import predict_machine_fault
import sqlite3
import bcrypt
from datetime import datetime
import time
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "supersecretkey123"  # Changez en production

# Lock pour la synchronisation des threads
data_lock = Lock()

# Store latest machine data avec des valeurs par défaut
latest_data = {
    "parametres_machine": [0, 0, 0, 0, 0],
    "timestamp": time.time(),
    "ml_prediction": {
        "fault_probability": 0.0, 
        "is_fault": False, 
        "model_status": "En attente des données"
    },
    "connection_status": "Déconnecté",
    "last_update": None
}

# Stockage des dernières données reçues (buffer circulaire)
data_buffer = []
MAX_BUFFER_SIZE = 100

# MQTT configuration
MQTT_BROKER = "d736909d58a34fa6930bc5f9398c1c1b.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_TOPIC = "diagnostic_machine"
MQTT_USER = "habib"
MQTT_PASSWORD = "Password2"

# SQLite database files
HISTORY_DB = "history.db"
USERS_DB = "users.db"

# Variable pour suivre l'état de connexion MQTT
mqtt_connected = False

def init_history_db():
    """Initialise la base de données d'historique"""
    try:
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
                model_status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        logger.info("Base de données d'historique initialisée")
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la base de données: {e}")
    finally:
        conn.close()

def init_users_db():
    """Initialise la base de données des utilisateurs"""
    try:
        conn = sqlite3.connect(USERS_DB)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Utilisateurs pré-créés
        pre_created_users = [
            ("admin", "password123"),
            ("user", "test123"),
            ("operateur", "op123")
        ]
        
        for username, plain_password in pre_created_users:
            cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
            if not cursor.fetchone():
                hashed_password = bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt())
                cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                             (username, hashed_password))
                logger.info(f"Utilisateur {username} créé")
        
        conn.commit()
        logger.info("Base de données des utilisateurs initialisée")
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation des utilisateurs: {e}")
    finally:
        conn.close()

def insert_history(data, prediction):
    """Insère les données dans l'historique"""
    try:
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
        logger.debug("Données insérées dans l'historique")
    except Exception as e:
        logger.error(f"Erreur lors de l'insertion en base: {e}")
    finally:
        conn.close()

def update_data_buffer(data):
    """Met à jour le buffer circulaire des données"""
    global data_buffer
    data_buffer.append({
        "timestamp": data["timestamp"],
        "parametres_machine": data["parametres_machine"].copy(),
        "ml_prediction": data["ml_prediction"].copy()
    })
    
    # Maintenir la taille du buffer
    if len(data_buffer) > MAX_BUFFER_SIZE:
        data_buffer.pop(0)

# MQTT callback when connected
def on_connect(client, userdata, flags, rc):
    global mqtt_connected, latest_data
    
    if rc == 0:
        mqtt_connected = True
        with data_lock:
            latest_data["connection_status"] = "Connecté"
        logger.info("Connexion MQTT réussie")
        client.subscribe(MQTT_TOPIC)
        logger.info(f"Abonnement au topic: {MQTT_TOPIC}")
    else:
        mqtt_connected = False
        with data_lock:
            latest_data["connection_status"] = f"Échec de connexion (Code: {rc})"
        logger.error(f"Échec de connexion MQTT: {rc}")

def on_disconnect(client, userdata, rc):
    global mqtt_connected, latest_data
    mqtt_connected = False
    with data_lock:
        latest_data["connection_status"] = "Déconnecté"
    logger.warning("Connexion MQTT perdue")

# MQTT callback when message received
def on_message(client, userdata, msg):
    global latest_data
    
    try:
        # Décoder le message JSON
        data = json.loads(msg.payload.decode())
        logger.debug(f"Message MQTT reçu: {data}")
        
        # Vérifier la structure des données
        params = data.get("parametres_machine", [])
        if len(params) != 5:
            logger.warning(f"Données incomplètes reçues: {params}")
            return
        
        # Valider que tous les paramètres sont des nombres
        try:
            params = [float(p) for p in params]
        except (ValueError, TypeError):
            logger.error(f"Paramètres non numériques: {params}")
            return
        
        # Faire la prédiction ML
        prediction = predict_machine_fault(params)
        
        # Traiter le timestamp
        timestamp = data.get("timestamp_epoch", data.get("timestamp", time.time()))
        if isinstance(timestamp, str):
            # Si c'est une chaîne, utiliser l'heure actuelle
            timestamp = time.time()
        
        # Mise à jour thread-safe des données
        with data_lock:
            latest_data.update({
                "parametres_machine": params,
                "timestamp": timestamp,
                "ml_prediction": prediction,
                "connection_status": "Connecté - Données reçues",
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        
        # Mettre à jour le buffer
        update_data_buffer(latest_data)
        
        # Sauvegarder en base de données
        insert_history(latest_data, prediction)
        
        # Log des informations importantes
        fault_status = "PANNE DÉTECTÉE" if prediction['is_fault'] else "FONCTIONNEMENT NORMAL"
        logger.info(f"Données mises à jour - {fault_status} - Probabilité: {prediction['fault_probability']:.2%}")
        
    except json.JSONDecodeError as e:
        logger.error(f"Erreur de décodage JSON: {e}")
    except Exception as e:
        logger.error(f"Erreur lors du traitement du message MQTT: {e}")

# Setup MQTT client avec reconnexion automatique
def setup_mqtt():
    global mqtt_connected
    
    while True:
        try:
            client = mqtt.Client()
            client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
            client.on_connect = on_connect
            client.on_message = on_message
            client.on_disconnect = on_disconnect
            
            # Configuration SSL
            client.tls_set()
            
            logger.info(f"Tentative de connexion à {MQTT_BROKER}:{MQTT_PORT}")
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            
            # Boucle MQTT bloquante
            client.loop_forever()
            
        except Exception as e:
            mqtt_connected = False
            with data_lock:
                latest_data["connection_status"] = f"Erreur: {str(e)}"
            logger.error(f"Erreur MQTT: {e}")
            logger.info("Reconnexion dans 10 secondes...")
            time.sleep(10)

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
            if value > 1e10:  # Si c'est en millisecondes
                value = value / 1000
            return datetime.fromtimestamp(value).strftime(format)
        return str(value)
    except (ValueError, TypeError, OSError):
        return "Format invalide"

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            return render_template('login.html', error="Veuillez remplir tous les champs")
        
        try:
            conn = sqlite3.connect(USERS_DB)
            cursor = conn.cursor()
            cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            
            if user and bcrypt.checkpw(password.encode('utf-8'), user[0]):
                session['username'] = username
                logger.info(f"Connexion réussie pour l'utilisateur: {username}")
                return redirect(url_for('index'))
            else:
                logger.warning(f"Tentative de connexion échouée pour: {username}")
                return render_template('login.html', error="Nom d'utilisateur ou mot de passe incorrect")
                
        except Exception as e:
            logger.error(f"Erreur lors de la connexion: {e}")
            return render_template('login.html', error="Erreur du serveur")
        finally:
            conn.close()
            
    return render_template('login.html', error=None)

# Logout route
@app.route('/logout')
def logout():
    username = session.get('username', 'Inconnu')
    session.pop('username', None)
    logger.info(f"Déconnexion de l'utilisateur: {username}")
    return redirect(url_for('login'))

# Route for main page
@app.route('/')
@login_required
def index():
    with data_lock:
        data_copy = latest_data.copy()
    return render_template('index.html', data=data_copy)

# Route for latest data (API)
@app.route('/data')
@login_required
def get_data():
    with data_lock:
        data_copy = latest_data.copy()
    return jsonify(data_copy)

# Route pour les statistiques du buffer
@app.route('/buffer_stats')
@login_required
def get_buffer_stats():
    with data_lock:
        buffer_copy = data_buffer.copy()
    
    if not buffer_copy:
        return jsonify({"error": "Aucune donnée disponible"})
    
    # Calculer des statistiques simples
    recent_faults = sum(1 for d in buffer_copy[-10:] if d["ml_prediction"]["is_fault"])
    avg_fault_prob = sum(d["ml_prediction"]["fault_probability"] for d in buffer_copy[-10:]) / min(10, len(buffer_copy))
    
    return jsonify({
        "total_records": len(buffer_copy),
        "recent_faults": recent_faults,
        "avg_fault_probability": avg_fault_prob,
        "mqtt_connected": mqtt_connected
    })

# Route for history page
@app.route('/history')
@login_required
def history():
    try:
        conn = sqlite3.connect(HISTORY_DB)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM machine_history 
            ORDER BY timestamp DESC 
            LIMIT 1000
        """)
        history_data = cursor.fetchall()
        
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
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'historique: {e}")
        return render_template('history.html', history=[], error="Erreur de base de données")
    finally:
        conn.close()

# API route for history data
@app.route('/history_data')
@login_required
def get_history_data():
    limit = request.args.get('limit', 100, type=int)
    limit = min(limit, 1000)  # Limite maximale de sécurité
    
    try:
        conn = sqlite3.connect(HISTORY_DB)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM machine_history 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        history_data = cursor.fetchall()
        
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
        
    except Exception as e:
        logger.error(f"Erreur API historique: {e}")
        return jsonify({"error": "Erreur de base de données"}), 500
    finally:
        conn.close()

# Route de status pour le monitoring
@app.route('/status')
@login_required
def system_status():
    with data_lock:
        status = {
            "mqtt_connected": mqtt_connected,
            "last_data_time": latest_data.get("last_update"),
            "connection_status": latest_data.get("connection_status"),
            "buffer_size": len(data_buffer),
            "ml_model_status": latest_data["ml_prediction"]["model_status"]
        }
    return jsonify(status)

if __name__ == '__main__':
    # Initialisation des bases de données
    logger.info("Initialisation des bases de données...")
    init_history_db()
    init_users_db()
    
    # Démarrage du thread MQTT
    logger.info("Démarrage du service MQTT...")
    mqtt_thread = Thread(target=setup_mqtt)
    mqtt_thread.daemon = True
    mqtt_thread.start()
    
    # Démarrage de l'application Flask
    logger.info("Démarrage de l'application Flask...")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)