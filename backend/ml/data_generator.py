"""
Synthetic Trajectory Data Generator
Generates labeled human vs bot mouse trajectories for model training.
"""

import numpy as np
import math
from typing import List, Tuple


class TrajectoryDataGenerator:
    """
    Generates synthetic mouse trajectories for training BiGRU and RF models.

    Three trajectory types:
    1. Human: Bezier curves with natural jitter, variable velocity, pauses, overshoots
    2. Bot: Linear interpolation, constant velocity, perfect efficiency
    3. Smart Bot: Bot with GAN-like noise to mimic human behavior
    """

    def __init__(self, screen_w: int = 1920, screen_h: int = 1080, seed: int = 42):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.rng = np.random.RandomState(seed)

    def generate_dataset(
        self,
        n_human: int = 2000,
        n_bot: int = 1500,
        n_smart_bot: int = 500,
        seq_length: int = 200,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate a labeled dataset of trajectories.

        Returns:
            sequences: (N, seq_length, 6) array
            labels: (N,) array (0=human, 1=bot)
        """
        all_sequences = []
        all_labels = []

        for _ in range(n_human):
            seq = self._generate_human_trajectory(seq_length)
            all_sequences.append(seq)
            all_labels.append(0)

        for _ in range(n_bot):
            seq = self._generate_bot_trajectory(seq_length)
            all_sequences.append(seq)
            all_labels.append(1)

        for _ in range(n_smart_bot):
            seq = self._generate_smart_bot_trajectory(seq_length)
            all_sequences.append(seq)
            all_labels.append(1)

        sequences = np.array(all_sequences, dtype=np.float32)
        labels = np.array(all_labels, dtype=np.float32)

        # Shuffle
        indices = self.rng.permutation(len(labels))
        return sequences[indices], labels[indices]

    def _generate_human_trajectory(self, seq_length: int) -> np.ndarray:
        """Generate realistic human mouse trajectory with Bezier curves and jitter."""
        # Random start and end points
        start = (self.rng.uniform(100, self.screen_w - 100),
                 self.rng.uniform(100, self.screen_h - 100))
        end = (self.rng.uniform(100, self.screen_w - 100),
               self.rng.uniform(100, self.screen_h - 100))

        # Generate control points for Bezier curve
        n_control = self.rng.randint(2, 5)
        controls = [start]
        for _ in range(n_control):
            cx = self.rng.uniform(min(start[0], end[0]) - 100,
                                  max(start[0], end[0]) + 100)
            cy = self.rng.uniform(min(start[1], end[1]) - 100,
                                  max(start[1], end[1]) + 100)
            controls.append((cx, cy))
        controls.append(end)

        # Sample points along the Bezier curve with variable speed
        t_values = np.sort(self.rng.beta(2, 2, size=seq_length))
        t_values = t_values / t_values.max()

        points = []
        for t in t_values:
            x, y = self._bezier_point(controls, t)

            # Add natural hand jitter (Gaussian noise)
            jitter_x = self.rng.normal(0, 2.5)
            jitter_y = self.rng.normal(0, 2.5)
            x += jitter_x
            y += jitter_y

            points.append((x, y))

        # Add random pauses (velocity → 0)
        n_pauses = self.rng.randint(1, 5)
        pause_indices = self.rng.choice(range(10, seq_length - 10), size=n_pauses, replace=False)
        for pi in pause_indices:
            pause_len = self.rng.randint(2, 8)
            for j in range(pi, min(pi + pause_len, seq_length)):
                points[j] = points[pi]

        # Convert to feature array with timestamps
        return self._points_to_features(points, seq_length, speed_variation=True)

    def _generate_bot_trajectory(self, seq_length: int) -> np.ndarray:
        """Generate perfectly linear bot trajectory with constant velocity."""
        start = (self.rng.uniform(0, self.screen_w), self.rng.uniform(0, self.screen_h))
        end = (self.rng.uniform(0, self.screen_w), self.rng.uniform(0, self.screen_h))

        points = []
        for i in range(seq_length):
            t = i / (seq_length - 1)
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            points.append((x, y))

        return self._points_to_features(points, seq_length, speed_variation=False)

    def _generate_smart_bot_trajectory(self, seq_length: int) -> np.ndarray:
        """Generate bot trajectory with injected noise to evade detection."""
        # Start with a bot trajectory
        start = (self.rng.uniform(0, self.screen_w), self.rng.uniform(0, self.screen_h))
        end = (self.rng.uniform(0, self.screen_w), self.rng.uniform(0, self.screen_h))

        points = []
        for i in range(seq_length):
            t = i / (seq_length - 1)
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t

            # Add synthetic jitter (less natural than human)
            noise_x = self.rng.normal(0, 1.0)
            noise_y = self.rng.normal(0, 1.0)
            x += noise_x
            y += noise_y

            points.append((x, y))

        # Add 1-2 fake pauses
        n_pauses = self.rng.randint(1, 3)
        pause_indices = self.rng.choice(range(20, seq_length - 20), size=n_pauses, replace=False)
        for pi in pause_indices:
            points[pi] = points[pi - 1]

        return self._points_to_features(points, seq_length, speed_variation=False)

    def _bezier_point(self, controls: list, t: float) -> Tuple[float, float]:
        """Compute point on a Bezier curve using De Casteljau's algorithm."""
        points = list(controls)
        while len(points) > 1:
            new_points = []
            for i in range(len(points) - 1):
                x = (1 - t) * points[i][0] + t * points[i + 1][0]
                y = (1 - t) * points[i][1] + t * points[i + 1][1]
                new_points.append((x, y))
            points = new_points
        return points[0]

    def _points_to_features(
        self, points: list, seq_length: int, speed_variation: bool
    ) -> np.ndarray:
        """Convert raw (x, y) points into 6-feature sequences."""
        features = np.zeros((seq_length, 6), dtype=np.float32)

        # Generate timestamps
        if speed_variation:
            # Variable time intervals (human-like)
            intervals = self.rng.exponential(150, size=seq_length)
            timestamps = np.cumsum(intervals)
        else:
            # Constant intervals (bot-like)
            timestamps = np.arange(seq_length) * 150.0

        for i in range(seq_length):
            x, y = points[i]
            t = timestamps[i]

            # Normalize
            x_norm = x / self.screen_w
            y_norm = y / self.screen_h
            t_norm = t / max(timestamps[-1], 1)

            # Kinematic features
            velocity = 0.0
            acceleration = 0.0
            jerk = 0.0

            if i > 0:
                dx = points[i][0] - points[i-1][0]
                dy = points[i][1] - points[i-1][1]
                dt = max((timestamps[i] - timestamps[i-1]) / 1000, 0.001)
                velocity = math.sqrt(dx**2 + dy**2) / dt

            if i > 1:
                prev_dx = points[i-1][0] - points[i-2][0]
                prev_dy = points[i-1][1] - points[i-2][1]
                prev_dt = max((timestamps[i-1] - timestamps[i-2]) / 1000, 0.001)
                prev_velocity = math.sqrt(prev_dx**2 + prev_dy**2) / prev_dt
                dt = max((timestamps[i] - timestamps[i-1]) / 1000, 0.001)
                acceleration = (velocity - prev_velocity) / dt

            features[i] = [
                x_norm,
                y_norm,
                t_norm,
                min(velocity / 5000, 1.0),
                min(abs(acceleration) / 10000, 1.0),
                min(abs(jerk) / 50000, 1.0),
            ]

        return features


def generate_training_data(
    n_human: int = 2000,
    n_bot: int = 1500,
    n_smart_bot: int = 500,
    seq_length: int = 200,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convenience function to generate training data."""
    generator = TrajectoryDataGenerator(seed=seed)
    return generator.generate_dataset(n_human, n_bot, n_smart_bot, seq_length)
