import network
import time
from machine import Pin, RTC
import ujson
from umqtt.simple import MQTTClient
import random
import ssl

# MQTT Server Parameters from HiveMQ Cloud
MQTT_CLIENT_ID = "micropython-random-demo"
MQTT_BROKER = "d736909d58a34fa6930bc5f9398c1c1b.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "habib"
MQTT_PASSWORD = "Password2"  # Remplacez par votre mot de passe réel
MQTT_TOPIC = "diagnostic_machine"

# Initialisation du RTC
rtc = RTC()

# Connexion WiFi
print("Connecting to WiFi", end="")
sta_if = network.WLAN(network.STA_IF)
sta_if.active(True)
sta_if.connect('Wokwi-GUEST', '')  # Pour Wokwi simulation
# Pour un usage réel, remplacez par vos credentials WiFi:
# sta_if.connect('your_ssid', 'your_password')
while not sta_if.isconnected():
    print(".", end="")
    time.sleep(0.1)
print(" Connected!")

# Synchroniser l'heure via NTP (optionnel mais recommandé)
try:
    import ntptime
    print("Synchronizing time with NTP server...")
    ntptime.settime()
    print("Time synchronized!")
except Exception as e:
    print("NTP synchronization failed:", e)

# Configuration SSL pour une connexion sécurisée
ssl_params = {
    "server_hostname": MQTT_BROKER,
    "cert_reqs": ssl.CERT_NONE  # Désactive la vérification du certificat (pour la simplicité)
}

print("Connecting to MQTT server... ", end="")
# Connexion au broker MQTT avec SSL
client = MQTTClient(
    MQTT_CLIENT_ID, 
    MQTT_BROKER, 
    port=MQTT_PORT, 
    user=MQTT_USER, 
    password=MQTT_PASSWORD,
    ssl=True,
    ssl_params=ssl_params
)

try:
    client.connect()
    print("Connected!")
    
    while True:
        # Obtenir l'heure actuelle du RTC
        current_time = rtc.datetime()
        # Formater l'horodatage: (année, mois, jour, heure, minute, seconde, microsecondes)
        timestamp = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            current_time[0], current_time[1], current_time[2],
            current_time[4], current_time[5], current_time[6]
        )
        
        parametres_machine = []
        for i in range(5):
            parametres_machine.append(random.randint(1, 100))
        
        message = ujson.dumps({
            "parametres_machine": parametres_machine,
            "timestamp": timestamp,
            "timestamp_epoch": time.mktime((current_time[0], current_time[1], current_time[2],
                                          current_time[4], current_time[5], current_time[6],
                                          0, 0))
        })
        
        print("Publishing to MQTT topic {}: {}".format(MQTT_TOPIC, message))
        client.publish(MQTT_TOPIC, message)
        
        # Attente de 5 secondes avant l'envoi suivant
        time.sleep(5)
        
except Exception as e:
    print("Error: ", e)
    # Reconnexion en cas d'erreur
    time.sleep(5)
    machine.reset()