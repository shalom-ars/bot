import pytest
import numpy as np
from app.engine.model import ProbabilityModel

def test_model_initialization():
    model = ProbabilityModel()
    assert model.is_trained == False

def test_model_training_and_prediction():
    model = ProbabilityModel()
    
    # Create dummy classification dataset
    X = np.random.rand(100, 5)
    y = np.random.randint(0, 2, 100)
    
    model.train(X, y)
    assert model.is_trained == True
    
    # Predict
    prob, uncertainty, model_name = model.predict(np.random.rand(1, 5))
    assert 0.0 <= prob <= 1.0
