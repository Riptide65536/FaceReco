from __future__ import annotations

import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend_api.openapi import build_openapi


class OpenApiSpecTests(unittest.TestCase):
    def test_openapi_contains_required_paths(self) -> None:
        spec = build_openapi()
        self.assertIn("/api/health", spec["paths"])
        self.assertIn("/api/auth/login", spec["paths"])
        self.assertIn("/api/models/train", spec["paths"])
        self.assertIn("/ws/events", spec["paths"])
        self.assertIn("BearerAuth", spec["components"]["securitySchemes"])
        self.assertIn("SystemStatus", spec["components"]["schemas"])
        self.assertIn("EventEnvelope", spec["components"]["schemas"])
        self.assertIn("VisionObservation", str(spec["components"]["schemas"]["EventEnvelope"]))


if __name__ == "__main__":
    unittest.main()
