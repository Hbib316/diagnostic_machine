import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import joblib
import os

class MLDiagnosticService:
    def __init__(self, model_path="diagnostic_model.pkl"):
        # Initialize model path and feature names
        self.model_path = model_path
        self.model = None
        self.feature_names = ["Vibration", "Temperature", "Pressure", "RMS", "Mean Temp"]
        self.is_trained = False
        # Load or create model
        self.load_or_train_model()

    def load_or_train_model(self):
        # Check if model exists
        if os.path.exists(self.model_path):
            # Load existing model
            self.model = joblib.load(self.model_path)
            self.is_trained = True
            print("Loaded model")
        else:
            # Create and train a simple model with dummy data
            X_dummy = np.random.rand(100, 5) * 100  # 100 samples, 5 features
            y_dummy = np.random.choice([0, 1], 100)  # Random 0 (normal) or 1 (fault)
            self.model = Pipeline([
                ("scaler", StandardScaler()),  # Standardize data
                ("classifier", RandomForestClassifier(n_estimators=10, random_state=42))
            ])
            self.model.fit(X_dummy, y_dummy)
            self.is_trained = True
            joblib.dump(self.model, self.model_path)  # Save model
            print("Trained and saved new model")

    def predict_fault(self, params):
        # Predict fault for given parameters
        if not self.is_trained:
            return {"fault_probability": 0.0, "is_fault": False, "model_status": "Not trained"}
        
        # Convert parameters to numpy array
        X = np.array(params).reshape(1, -1)
        # Predict fault (0 or 1)
        prediction = self.model.predict(X)[0]
        # Get probability of fault
        probability = self.model.predict_proba(X)[0][1]  # Probability of class 1 (fault)
        
        return {
            "fault_probability": float(probability),
            "is_fault": bool(prediction),
            "model_status": "Active"
        }

# Create global ML service instance
ml_service = MLDiagnosticService()

def predict_machine_fault(params):
    # Utility function to make predictions
    return ml_service.predict_fault(params)