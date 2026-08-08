"""
Device Fingerprint Service
Processes Canvas, WebGL, and WebRTC fingerprints for environment integrity.
"""

import hashlib
import logging
import json
from typing import Dict, Any, Optional
from backend.config import settings

logger = logging.getLogger(__name__)


class DeviceFingerprintService:
    """
    Generates composite device fingerprints and validates consistency.
    Detects spoofing by cross-referencing User-Agent with reported hardware.
    """

    def generate_composite_hash(self, fingerprint_data: Dict) -> str:
        """Generate a deterministic composite hash from all fingerprint signals."""
        components = [
            str(fingerprint_data.get("canvas_hash") or ""),
            str(fingerprint_data.get("webgl_hash") or ""),
            str(fingerprint_data.get("webgl_vendor") or ""),
            str(fingerprint_data.get("webgl_renderer") or ""),
            str(fingerprint_data.get("platform") or ""),
            str(fingerprint_data.get("screen_resolution") or ""),
            str(fingerprint_data.get("color_depth") or ""),
            str(fingerprint_data.get("hardware_concurrency") or ""),
            str(fingerprint_data.get("language") or ""),
        ]
        raw = "|".join(components)
        return hashlib.sha256(raw.encode()).hexdigest()

    def validate_consistency(self, fingerprint_data: Dict) -> Dict[str, Any]:
        """
        Check if the fingerprint signals are internally consistent.
        Inconsistencies suggest anti-detect browsers or spoofing.
        """
        issues = []
        is_consistent = True
        user_agent = (fingerprint_data.get("user_agent") or "").lower()
        platform = (fingerprint_data.get("platform") or "").lower()
        renderer = (fingerprint_data.get("webgl_renderer") or "").lower()

        # Check 1: User-Agent vs Platform
        if platform and user_agent:
            if "windows" in platform and "mac" in user_agent:
                issues.append("UA_PLATFORM_MISMATCH: UA says Mac but platform says Windows")
                is_consistent = False
            elif "mac" in platform and "windows" in user_agent:
                issues.append("UA_PLATFORM_MISMATCH: UA says Windows but platform says Mac")
                is_consistent = False
            elif "linux" in platform and ("windows" in user_agent or "mac" in user_agent):
                issues.append("UA_PLATFORM_MISMATCH: Platform Linux but UA says otherwise")
                is_consistent = False

        # Check 2: WebGL Renderer vs Platform (GPU sanity)
        if renderer and platform:
            if "apple" in renderer and "win" in platform:
                issues.append("GPU_PLATFORM_MISMATCH: Apple GPU reported on Windows")
                is_consistent = False
            if "swiftshader" in renderer:
                issues.append("SOFTWARE_RENDERER: SwiftShader detected (headless browser indicator)")
                is_consistent = False

        # Check 3: Suspiciously generic fingerprint
        if not fingerprint_data.get("canvas_hash"):
            issues.append("MISSING_CANVAS: Canvas fingerprint missing (may be blocked)")

        # Check 4: WebRTC IP leaks
        webrtc_ips = fingerprint_data.get("webrtc_local_ips", [])
        if webrtc_ips and any("0.0.0.0" in ip for ip in webrtc_ips):
            issues.append("WEBRTC_BLOCKED: WebRTC returning null IPs")

        # Check 5: Hardware concurrency
        hw = fingerprint_data.get("hardware_concurrency")
        if hw is not None and (hw < 1 or hw > 128):
            issues.append(f"UNUSUAL_HARDWARE: {hw} CPU cores reported")
            is_consistent = False

        return {
            "is_consistent": is_consistent,
            "issues": issues,
            "risk_level": "HIGH" if len(issues) > 2 else "MEDIUM" if issues else "LOW",
        }


# Singleton
device_fingerprint_service = DeviceFingerprintService()
