"""Tests for health endpoints."""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rest.routes import setup_routes


app = FastAPI()
setup_routes(app)
client = TestClient(app)


class HealthEndpointTests(unittest.TestCase):
    """Verify the health endpoint stays available."""

    def test_health_endpoint(self):
        response = client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertEqual(data["status"], "ok")
        self.assertIn("service", data)
        self.assertIn("llm_implementation", data)
