"""
Trajectory Analyzer Service
Processes raw mouse trajectory data, extracts kinematic features,
and runs BiGRU + Random Forest inference for bot detection.
"""

import math
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class TrajectoryAnalyzer:
    """
    Dual-model trajectory analysis for bot detection.
    BiGRU: Sequential analysis of raw trajectories
    Random Forest: Session-level aggregated kinetic features
    """

    def __init__(self):
        self._bigru_model = None
        self._rf_model = None

    def extract_kinematic_features(
        self, points: List[Dict]
    ) -> List[Dict]:
        """
        Compute velocity, acceleration, jerk, and curvature from raw (x, y, t) coordinates.

        Args:
            points: List of {x, y, timestamp_ms, event_type}

        Returns:
            Points enriched with kinematic features
        """
        if len(points) < 2:
            return points

        enriched = []
        for i, point in enumerate(points):
            features = {
                "x": point["x"],
                "y": point["y"],
                "timestamp_ms": point["timestamp_ms"],
                "event_type": point.get("event_type", "move"),
                "velocity": 0.0,
                "acceleration": 0.0,
                "jerk": 0.0,
                "curvature": 0.0,
            }

            if i > 0:
                prev = points[i - 1]
                dx = point["x"] - prev["x"]
                dy = point["y"] - prev["y"]
                dt = max((point["timestamp_ms"] - prev["timestamp_ms"]) / 1000.0, 0.001)

                distance = math.sqrt(dx**2 + dy**2)
                features["velocity"] = distance / dt

                if i > 1:
                    prev_enriched = enriched[-1]
                    dv = features["velocity"] - prev_enriched["velocity"]
                    features["acceleration"] = dv / dt

                    if i > 2:
                        prev_prev = enriched[-2]
                        da = features["acceleration"] - prev_enriched["acceleration"]
                        features["jerk"] = da / dt

            # Curvature: angle change between consecutive segments
            if i >= 2:
                p0, p1, p2 = points[i-2], points[i-1], points[i]
                features["curvature"] = self._compute_curvature(p0, p1, p2)

            enriched.append(features)

        return enriched

    def aggregate_session_features(self, enriched_points: List[Dict]) -> Dict:
        """
        Aggregate trajectory points into session-level features for Random Forest.

        Returns:
            Dict of aggregated kinetic features
        """
        if not enriched_points:
            return self._empty_features()

        velocities = [p["velocity"] for p in enriched_points if p["velocity"] > 0]
        accelerations = [p["acceleration"] for p in enriched_points]
        jerks = [p["jerk"] for p in enriched_points]

        # Path straightness: direct distance / total path distance
        if len(enriched_points) >= 2:
            start = enriched_points[0]
            end = enriched_points[-1]
            direct_dist = math.sqrt(
                (end["x"] - start["x"])**2 + (end["y"] - start["y"])**2
            )
            total_dist = sum(
                math.sqrt(
                    (enriched_points[i]["x"] - enriched_points[i-1]["x"])**2 +
                    (enriched_points[i]["y"] - enriched_points[i-1]["y"])**2
                )
                for i in range(1, len(enriched_points))
            )
            path_straightness = direct_dist / max(total_dist, 0.001)
        else:
            path_straightness = 1.0
            total_dist = 0.0

        # Count pauses (velocity near 0)
        pause_count = sum(1 for v in velocities if v < 1.0) if velocities else 0

        # Click and scroll counts
        click_count = sum(1 for p in enriched_points if p.get("event_type") == "click")
        scroll_count = sum(1 for p in enriched_points if p.get("event_type") == "scroll")

        # Jitter: std deviation of velocity
        jitter = float(np.std(velocities)) if velocities else 0.0

        # Session duration
        if len(enriched_points) >= 2:
            duration = enriched_points[-1]["timestamp_ms"] - enriched_points[0]["timestamp_ms"]
        else:
            duration = 0

        return {
            "mean_velocity": float(np.mean(velocities)) if velocities else 0.0,
            "max_velocity": float(np.max(velocities)) if velocities else 0.0,
            "mean_acceleration": float(np.mean(accelerations)) if accelerations else 0.0,
            "max_acceleration": float(np.max(np.abs(accelerations))) if accelerations else 0.0,
            "jitter_score": jitter,
            "path_straightness": path_straightness,
            "pause_count": pause_count,
            "total_distance": total_dist,
            "click_count": click_count,
            "scroll_count": scroll_count,
            "total_points": len(enriched_points),
            "session_duration_ms": duration,
            "mean_jerk": float(np.mean(np.abs(jerks))) if jerks else 0.0,
        }

    async def analyze(self, points: List[Dict]) -> Dict:
        """
        Run full bot detection pipeline:
        1. Extract kinematic features
        2. BiGRU sequential analysis
        3. Random Forest session-level classification
        4. Ensemble the results

        Returns:
            Combined bot detection result
        """
        # Feature extraction
        enriched = self.extract_kinematic_features(points)
        session_features = self.aggregate_session_features(enriched)

        # BiGRU inference
        bigru_score = await self._run_bigru(enriched)

        # Random Forest inference
        rf_score = await self._run_random_forest(session_features)

        # Ensemble: weighted average (BiGRU gets more weight for sequential detection)
        combined = 0.6 * bigru_score + 0.4 * rf_score

        is_bot = combined > 0.5
        confidence = abs(combined - 0.5) * 2  # 0-1 confidence

        return {
            "bigru_bot_score": round(bigru_score, 4),
            "rf_fraud_score": round(rf_score, 4),
            "combined_bot_probability": round(combined, 4),
            "is_bot": is_bot,
            "confidence": round(confidence, 4),
            **session_features,
        }

    async def _run_bigru(self, enriched_points: List[Dict]) -> float:
        """Run BiGRU inference on trajectory sequence."""
        try:
            if self._bigru_model is None:
                self._bigru_model = self._load_bigru_model()

            if self._bigru_model is None:
                return self._heuristic_bot_score(enriched_points)

            import torch
            # Prepare sequence: [x, y, t, velocity, acceleration, jerk]
            sequence = []
            for p in enriched_points:
                sequence.append([
                    p["x"] / 1920.0,  # Normalize to screen dimensions
                    p["y"] / 1080.0,
                    p["timestamp_ms"] / 60000.0,
                    min(p["velocity"] / 5000.0, 1.0),
                    min(abs(p["acceleration"]) / 10000.0, 1.0),
                    min(abs(p["jerk"]) / 50000.0, 1.0),
                ])

            # Pad/truncate to fixed length
            max_len = 200
            if len(sequence) > max_len:
                sequence = sequence[:max_len]
            while len(sequence) < max_len:
                sequence.append([0.0] * 6)

            tensor = torch.FloatTensor([sequence])
            with torch.no_grad():
                output = self._bigru_model(tensor)
            return float(output.squeeze().item())

        except Exception as e:
            logger.warning(f"BiGRU inference failed: {e}. Using heuristic.")
            return self._heuristic_bot_score(enriched_points)

    async def _run_random_forest(self, session_features: Dict) -> float:
        """Run Random Forest inference on aggregated features."""
        try:
            if self._rf_model is None:
                self._rf_model = self._load_rf_model()

            if self._rf_model is None:
                return self._heuristic_rf_score(session_features)

            feature_vector = np.array([[
                session_features["mean_velocity"],
                session_features["max_velocity"],
                session_features["mean_acceleration"],
                session_features["jitter_score"],
                session_features["path_straightness"],
                session_features["pause_count"],
                session_features["click_count"],
            ]])

            proba = self._rf_model.predict_proba(feature_vector)
            return float(proba[0][1])  # Probability of bot class

        except Exception as e:
            logger.warning(f"RF inference failed: {e}. Using heuristic.")
            return self._heuristic_rf_score(session_features)

    def _load_bigru_model(self):
        """Load trained BiGRU model from disk."""
        try:
            import torch
            from backend.ml.bigru_model import BiGRUBotDetector
            model = BiGRUBotDetector()
            model.load_state_dict(torch.load(
                "backend/ml/saved_models/bigru_bot_detector.pt",
                map_location="cpu", weights_only=True
            ))
            model.eval()
            logger.info("BiGRU model loaded successfully")
            return model
        except FileNotFoundError:
            logger.warning("BiGRU model file not found. Using heuristic fallback.")
            return None
        except Exception as e:
            logger.warning(f"Failed to load BiGRU model: {e}")
            return None

    def _load_rf_model(self):
        """Load trained Random Forest model from disk."""
        try:
            import joblib
            model = joblib.load("backend/ml/saved_models/rf_kinetic_classifier.joblib")
            logger.info("Random Forest model loaded successfully")
            return model
        except FileNotFoundError:
            logger.warning("RF model file not found. Using heuristic fallback.")
            return None
        except Exception as e:
            logger.warning(f"Failed to load RF model: {e}")
            return None

    def _heuristic_bot_score(self, enriched_points: List[Dict]) -> float:
        """Heuristic bot detection when ML models aren't available."""
        if not enriched_points:
            return 0.5

        velocities = [p["velocity"] for p in enriched_points if p["velocity"] > 0]
        if not velocities:
            return 0.5

        # Bots tend to have: low jitter, high path straightness, constant velocity
        jitter = float(np.std(velocities))
        cv = jitter / max(float(np.mean(velocities)), 0.001)

        score = 0.5
        if cv < 0.1:   # Too consistent = likely bot
            score += 0.3
        if cv < 0.05:
            score += 0.15

        return min(score, 1.0)

    def _heuristic_rf_score(self, features: Dict) -> float:
        """Heuristic classification when RF model isn't available."""
        score = 0.3
        if features["jitter_score"] < 5.0:
            score += 0.2
        if features["path_straightness"] > 0.9:
            score += 0.15
        if features["pause_count"] < 2:
            score += 0.15
        return min(score, 1.0)

    def _compute_curvature(self, p0: Dict, p1: Dict, p2: Dict) -> float:
        """Compute curvature at p1 given three consecutive points."""
        ax, ay = p1["x"] - p0["x"], p1["y"] - p0["y"]
        bx, by = p2["x"] - p1["x"], p2["y"] - p1["y"]

        cross = ax * by - ay * bx
        dot = ax * bx + ay * by

        angle = math.atan2(abs(cross), dot)
        return angle

    def _empty_features(self) -> Dict:
        return {
            "mean_velocity": 0, "max_velocity": 0, "mean_acceleration": 0,
            "max_acceleration": 0, "jitter_score": 0, "path_straightness": 0,
            "pause_count": 0, "total_distance": 0, "click_count": 0,
            "scroll_count": 0, "total_points": 0, "session_duration_ms": 0,
            "mean_jerk": 0,
        }


# Singleton
trajectory_analyzer = TrajectoryAnalyzer()
