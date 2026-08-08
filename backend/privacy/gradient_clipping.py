"""
Gradient Clipping
Bounds the influence of any single data point by clipping gradient norms.
Required before applying LDP noise to ensure sensitivity bounds hold.
"""

import numpy as np
import logging
from typing import Union, List

logger = logging.getLogger(__name__)


class GradientClipper:
    """
    Implements L2 norm gradient clipping as specified in DPFedBank.
    Ensures per-sample sensitivity stays within Δ bounds.
    """

    def __init__(self, max_norm: float = 1.0):
        self.max_norm = max_norm

    def clip(
        self,
        gradients: Union[np.ndarray, List[float]],
        max_norm: float = None,
    ) -> np.ndarray:
        """
        Clip gradients/updates to have L2 norm ≤ max_norm.

        Args:
            gradients: Gradient vector or model update
            max_norm: Override default max norm

        Returns:
            Clipped gradient vector
        """
        max_norm = max_norm or self.max_norm
        grad = np.array(gradients, dtype=np.float64)

        current_norm = np.linalg.norm(grad)

        if current_norm > max_norm:
            scale = max_norm / current_norm
            clipped = grad * scale
            logger.debug(
                f"Gradient clipped: {current_norm:.4f} → {max_norm:.4f} "
                f"(scale={scale:.4f})"
            )
            return clipped

        return grad

    def clip_per_sample(
        self,
        batch_gradients: List[np.ndarray],
        max_norm: float = None,
    ) -> List[np.ndarray]:
        """
        Clip each sample's gradient independently.
        Used in per-sample gradient clipping for DP-SGD.
        """
        return [self.clip(g, max_norm) for g in batch_gradients]

    def clip_and_aggregate(
        self,
        batch_gradients: List[np.ndarray],
        max_norm: float = None,
    ) -> np.ndarray:
        """
        Clip each gradient, then compute the mean.
        Standard DP-SGD aggregation step.
        """
        clipped = self.clip_per_sample(batch_gradients, max_norm)
        return np.mean(clipped, axis=0)


# Singleton with default from config
from backend.config import settings
gradient_clipper = GradientClipper(max_norm=settings.gradient_clip_norm)
