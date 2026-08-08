"""
Local Differential Privacy (LDP) Implementation
Satisfies (ε, δ)-LDP by adding calibrated Gaussian noise.
Based on the DPFedBank framework specification.
"""

import numpy as np
import math
import logging
from typing import Union, List

logger = logging.getLogger(__name__)


class LocalDifferentialPrivacy:
    """
    Implements Local Differential Privacy with Gaussian noise mechanism.
    Noise scale: σ ≥ Δ/ε as specified in the AIDUS technical spec.
    """

    def compute_noise_scale(
        self,
        sensitivity: float,
        epsilon: float,
        delta: float = 1e-5,
    ) -> float:
        """
        Compute the Gaussian noise standard deviation (σ).
        For (ε, δ)-DP, σ ≥ Δ · √(2 · ln(1.25/δ)) / ε

        This is the analytic Gaussian mechanism formula.
        """
        if epsilon <= 0:
            raise ValueError("Epsilon must be positive")
        if delta <= 0 or delta >= 1:
            raise ValueError("Delta must be in (0, 1)")
        if sensitivity < 0:
            raise ValueError("Sensitivity must be non-negative")

        # Analytic Gaussian mechanism
        sigma = sensitivity * math.sqrt(2 * math.log(1.25 / delta)) / epsilon
        return sigma

    def add_noise(
        self,
        data: Union[float, np.ndarray, List[float]],
        epsilon: float,
        delta: float = 1e-5,
        sensitivity: float = 1.0,
    ) -> Union[float, np.ndarray]:
        """
        Add calibrated Gaussian noise to data for LDP.

        Args:
            data: Scalar or array of values to perturb
            epsilon: Privacy budget for this operation
            delta: Failure probability
            sensitivity: Sensitivity of the query (Δ)

        Returns:
            Perturbed data with same shape as input
        """
        sigma = self.compute_noise_scale(sensitivity, epsilon, delta)

        if isinstance(data, (int, float)):
            noise = np.random.normal(0, sigma)
            result = data + noise
            logger.debug(f"LDP noise added: σ={sigma:.4f}, ε={epsilon}, Δ={sensitivity}")
            return float(result)

        data_array = np.array(data, dtype=np.float64)
        noise = np.random.normal(0, sigma, size=data_array.shape)
        result = data_array + noise

        logger.debug(
            f"LDP noise added to array of shape {data_array.shape}: σ={sigma:.4f}, ε={epsilon}"
        )
        return result

    def add_laplace_noise(
        self,
        data: Union[float, np.ndarray],
        epsilon: float,
        sensitivity: float = 1.0,
    ) -> Union[float, np.ndarray]:
        """
        Add Laplace noise for pure ε-differential privacy.
        Scale parameter b = Δ/ε
        """
        if epsilon <= 0:
            raise ValueError("Epsilon must be positive")

        scale = sensitivity / epsilon

        if isinstance(data, (int, float)):
            noise = np.random.laplace(0, scale)
            return float(data + noise)

        data_array = np.array(data, dtype=np.float64)
        noise = np.random.laplace(0, scale, size=data_array.shape)
        return data_array + noise

    def randomized_response(
        self, value: bool, epsilon: float
    ) -> bool:
        """
        Randomized response mechanism for binary data.
        Used for survey-style LDP on boolean attributes.
        """
        p = math.exp(epsilon) / (1 + math.exp(epsilon))
        if np.random.random() < p:
            return value
        else:
            return not value


# Singleton
ldp = LocalDifferentialPrivacy()
