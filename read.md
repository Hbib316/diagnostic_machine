# 🏭 Système de Diagnostic Industriel

Un système de surveillance et de diagnostic en temps réel pour machines industrielles utilisant l'IoT, MQTT et l'intelligence artificielle.

## 🌟 Aperçu

Ce projet implémente un système complet de diagnostic prédictif pour équipements industriels. Il collecte des données de capteurs via MQTT, utilise des algorithmes de machine learning pour prédire les pannes, et fournit une interface web intuitive pour la surveillance en temps réel.

### 🚀 [Démo en ligne](https://diagnostic-machine.onrender.com)

**Identifiants de test :**
- **Admin :** `admin` / `password123`
- **Utilisateur :** `user` / `test123`
- **Opérateur :** `operateur` / `op123`

## 📋 Fonctionnalités

### ✨ Surveillance en Temps Réel
- **Dashboard interactif** avec mise à jour automatique (3 secondes)
- **Visualisation des paramètres machine** : Vibration, Température, Pression, RMS, Température moyenne
- **Indicateurs de statut** en temps réel avec codes couleur

### 🤖 Intelligence Artificielle
- **Prédiction de pannes** utilisant Random Forest
- **Probabilité de défaillance** calculée en temps réel
- **Modèle auto-adaptatif** avec sauvegarde automatique

### 📊 Historique et Analyse
- **Base de données SQLite** pour stockage persistant
- **Historique complet** des mesures et prédictions
- **Interface de consultation** avec recherche et filtrage

### 🔐 Sécurité
- **Authentification utilisateur** avec mots de passe chiffrés (bcrypt)
- **Gestion de sessions** sécurisée
- **Contrôle d'accès** par rôles

### 🌐 Connectivité IoT
- **Protocole MQTT** avec TLS/SSL
- **Reconnexion automatique** en cas de perte de connexion
- **Support multi-capteurs** avec validation des données

## 🛠️ Technologies Utilisées

### Backend
- **Python 3.8+**
- **Flask** - Framework web
- **SQLite** - Base de données
- **scikit-learn** - Machine Learning
- **paho-mqtt** - Client MQTT

### Frontend
- **HTML5/CSS3** - Interface utilisateur
- **JavaScript vanilla** - Interactivité
- **Design responsive** - Compatible mobile

### IoT & Communication
- **MQTT** - Protocole de communication
- **HiveMQ Cloud** - Broker MQTT
- **SSL/TLS** - Chiffrement des communications
