"""Tests for health endpoints."""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.deps import get_consumers, get_llm_client
from app.rest.routes import setup_routes


app = FastAPI()
setup_routes(app)
app.dependency_overrides[get_llm_client] = lambda: None
app.dependency_overrides[get_consumers] = lambda: []
client = TestClient(app)


class HealthEndpointTests(unittest.TestCase):
    """Verify the health endpoint stays available."""

    def test_health_endpoint(self):
        response = client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertEqual(data["status"], "live")
        self.assertIn("service", data)
        self.assertIn("llm_implementation", data)

    def test_uninitialized_is_not_ready_but_live(self):
        response = client.get("/api/v1/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(client.get("/api/v1/live").status_code, 200)
