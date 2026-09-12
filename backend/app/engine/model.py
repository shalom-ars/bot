from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
import numpy as np
import logging

logger = logging.getLogger(__name__)

class ProbabilityModel:
    def __init__(self):
        base_model = LogisticRegression(class_weight='balanced', max_iter=1000)
        self.model = CalibratedClassifierCV(base_model, method='sigmoid', cv=5)
        self.is_trained = False
        
    def train(self, X_train, y_train):
        if len(X_train) < 5:  # Minimum needed for cv=5
            logger.error(f"Cannot train model on {len(X_train)} samples. Need >= 5 for calibration.")
            return
            
        self.model.fit(X_train, y_train)
        self.is_trained = True
        logger.info("CalibratedClassifierCV model trained successfully.")
        
    def predict(self, features: np.ndarray) -> tuple[float, float, str]:
        """
        Takes a 2D numpy array of features.
        Returns (probability, uncertainty, model_name).
        """
        if not self.is_trained:
            return (0.50, 0.50, "untrained_baseline")
            
        probs = self.model.predict_proba(features)
        
        # Uncertainty is heuristically derived from probability proximity to 0.5
        # and standard error if we had an ensemble, but we use a simpler proxy for now.
        prob = float(probs[0][1])
        uncertainty = 4.0 * prob * (1 - prob) * 0.1 # Max uncertainty 0.1 at prob=0.5
        
        return (prob, uncertainty, "calibrated_logistic_regression")
