"""
Random Forest Training Script
Trains on aggregated kinetic features for session-level bot classification.
"""

import os
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from backend.ml.data_generator import TrajectoryDataGenerator
import math


def extract_session_features(sequence: np.ndarray) -> np.ndarray:
    """Extract aggregated kinetic features from a trajectory sequence."""
    # Denormalize velocity and acceleration
    velocities = sequence[:, 3] * 5000  # velocity_norm * max_velocity
    accelerations = sequence[:, 4] * 10000

    # Non-zero velocities
    nonzero_v = velocities[velocities > 0]

    mean_velocity = np.mean(nonzero_v) if len(nonzero_v) > 0 else 0
    max_velocity = np.max(nonzero_v) if len(nonzero_v) > 0 else 0
    mean_acceleration = np.mean(accelerations)
    jitter = np.std(nonzero_v) if len(nonzero_v) > 0 else 0

    # Path straightness
    start = sequence[0, :2]
    end = sequence[-1, :2]
    direct_dist = np.sqrt(np.sum((end - start) ** 2))
    total_dist = np.sum(np.sqrt(np.sum(np.diff(sequence[:, :2], axis=0) ** 2, axis=1)))
    path_straightness = direct_dist / max(total_dist, 0.001)

    # Pause count (velocity near 0)
    pause_count = np.sum(velocities < 1.0)

    # Click count (not directly available, approximate from position changes)
    position_changes = np.sum(np.abs(np.diff(sequence[:, :2], axis=0)) > 0.001, axis=0)
    click_estimate = max(0, len(velocities) - int(np.sum(position_changes > 0)))

    return np.array([
        mean_velocity,
        max_velocity,
        mean_acceleration,
        jitter,
        path_straightness,
        pause_count,
        click_estimate,
    ])


def train_random_forest(
    n_human: int = 2000,
    n_bot: int = 1500,
    n_smart_bot: int = 500,
    n_estimators: int = 200,
    save_path: str = "backend/ml/saved_models/rf_kinetic_classifier.joblib",
):
    """Train Random Forest classifier on session-level kinetic features."""

    print("=" * 60)
    print("Random Forest Kinetic Classifier - Training Pipeline")
    print("=" * 60)

    # Step 1: Generate data
    print(f"\n[1/4] Generating data and extracting features")
    generator = TrajectoryDataGenerator(seed=42)
    sequences, labels = generator.generate_dataset(n_human, n_bot, n_smart_bot)

    # Extract session-level features
    features = np.array([extract_session_features(seq) for seq in sequences])
    print(f"  Feature matrix shape: {features.shape}")
    print(f"  Features: mean_vel, max_vel, mean_acc, jitter, path_straight, pauses, clicks")

    # Step 2: Train/Test split
    print("\n[2/4] Splitting train/test (80/20)")
    X_train, X_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, random_state=42, stratify=labels
    )
    print(f"  Train: {len(X_train)}, Test: {len(X_test)}")

    # Step 3: Train
    print(f"\n[3/4] Training Random Forest ({n_estimators} trees)")
    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=15,
        min_samples_split=5,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    # Evaluate
    y_pred = clf.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"\n  Accuracy: {accuracy:.4f}")
    print("\n  Classification Report:")
    print(classification_report(y_test, y_pred, target_names=["Human", "Bot"]))

    # Feature importance
    feature_names = ["mean_vel", "max_vel", "mean_acc", "jitter", "path_straight", "pauses", "clicks"]
    importances = clf.feature_importances_
    print("  Feature Importances:")
    for name, imp in sorted(zip(feature_names, importances), key=lambda x: -x[1]):
        print(f"    {name:15s}: {imp:.4f}")

    # Step 4: Save
    print(f"\n[4/4] Saving model to {save_path}")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    joblib.dump(clf, save_path)
    print("=" * 60)

    return accuracy


if __name__ == "__main__":
    train_random_forest()
