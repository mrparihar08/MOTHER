import os
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.app.app import app
from backend.presentation.services.ai_image_service import (
    AIImageService,
    GeminiImageProvider,
    PollinationsImageProvider,
    build_image_prompt,
    clean_prompt_for_image_gen,
    generate_ai_image,
)
from backend.presentation.schemas import AIImageGenerateRequest, AIImageGenerateResponse


class TestAIImageService(unittest.TestCase):
    def setUp(self):
        self.service = AIImageService()
        self.client = TestClient(app)

    def test_build_image_prompt_slide_awareness(self):
        prompt = build_image_prompt(
            topic="Artificial Intelligence in Healthcare",
            slide_title="Neural Diagnostics in Radiology",
            slide_content="Deep learning algorithms detecting subtle fractures and anomalies in X-Ray scans",
            visual_type="medical",
            style="Corporate Executive",
            aspect_ratio="16:9",
            text_position="left",
        )
        self.assertIn("Neural Diagnostics in Radiology", prompt)
        self.assertIn("Artificial Intelligence in Healthcare", prompt)
        self.assertIn("16:9 widescreen presentation aspect ratio", prompt)
        self.assertIn("negative space on the left side", prompt)
        self.assertIn("no watermarks", prompt)

    def test_build_image_prompt_presets(self):
        cyber_prompt = build_image_prompt(
            topic="Zero Trust Cybersecurity Architecture",
            slide_title="Firewall Threat Mitigation",
            slide_content="Real-time encryption and SOC anomaly detection",
            visual_type="technology",
            style="Technology",
        )
        self.assertTrue("cybersecurity" in cyber_prompt.lower() or "threat" in cyber_prompt.lower() or "shield" in cyber_prompt.lower())

    def test_gemini_provider_mock_success(self):
        provider = GeminiImageProvider()
        
        mock_image_bytes = b"\xff\xd8\xff\xe0" + b"X" * 2048  # Valid JPEG header dummy
        mock_generated_image = MagicMock()
        mock_generated_image.image.image_bytes = mock_image_bytes
        
        mock_result = MagicMock()
        mock_result.generated_images = [mock_generated_image]
        
        mock_genai_client = MagicMock()
        mock_genai_client.models.generate_images.return_value = mock_result
        
        with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_test_key"}), \
             patch("backend.chats.services.gemini_service.get_gemini_client", return_value=mock_genai_client):
            
            res = provider.generate(
                prompt="Medical diagnostic scan",
                width=1920,
                height=1080,
                aspect_ratio="16:9",
                style="Professional",
            )
            
            self.assertIsNotNone(res)
            self.assertEqual(res["provider"], "gemini")
            self.assertTrue(res["image_url"].startswith("/assets/"))
            self.assertEqual(res["aspect_ratio"], "16:9")
            self.assertTrue(res["generated"])

    def test_pollinations_provider_mock_success(self):
        provider = PollinationsImageProvider()
        
        mock_data = b"\xff\xd8\xff\xe0" + b"P" * 2048  # Valid JPEG dummy
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_resp.content = mock_data
        
        with patch("requests.get", return_value=mock_resp):
            res = provider.generate(
                prompt="Cloud architecture server room",
                width=1920,
                height=1080,
                aspect_ratio="16:9",
                style="Professional",
            )
            
            self.assertIsNotNone(res)
            self.assertEqual(res["provider"], "pollinations")
            self.assertTrue(res["image_url"].startswith("/assets/"))
            self.assertEqual(res["aspect_ratio"], "16:9")
            self.assertTrue(res["generated"])

    def test_ai_image_service_auto_fallback(self):
        """When Gemini fails in AUTO mode, it should automatically fallback to Pollinations."""
        service = AIImageService()
        
        mock_pollinations_data = b"\xff\xd8\xff\xe0" + b"FALLBACK" * 500
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_resp.content = mock_pollinations_data

        with patch.object(service.gemini_provider, "generate", return_value=None), \
             patch("requests.get", return_value=mock_resp):
            
            res = service.generate(
                prompt="Financial growth roadmap",
                provider="auto",
                aspect_ratio="16:9",
            )
            
            self.assertIsNotNone(res)
            self.assertEqual(res["provider"], "pollinations")

    def test_ai_image_service_explicit_provider_routing(self):
        service = AIImageService()
        
        with patch.object(service.gemini_provider, "generate", return_value={"provider": "gemini", "image_url": "/assets/g.jpg"}) as mock_gemini, \
             patch.object(service.pollinations_provider, "generate", return_value={"provider": "pollinations", "image_url": "/assets/p.jpg"}) as mock_poll:
            
            # Explicit Gemini call
            res_gem = service.generate(prompt="Test G", provider="gemini")
            self.assertEqual(res_gem["provider"], "gemini")
            mock_gemini.assert_called_once()
            mock_poll.assert_not_called()
            
            mock_gemini.reset_mock()
            mock_poll.reset_mock()
            
            # Explicit Pollinations call
            res_poll = service.generate(prompt="Test P", provider="pollinations")
            self.assertEqual(res_poll["provider"], "pollinations")
            mock_poll.assert_called_once()
            mock_gemini.assert_not_called()

    def test_api_endpoint_generate_post(self):
        mock_result = {
            "provider": "gemini",
            "model": "imagen-3.0-generate-002",
            "image_url": "/assets/mock_generated.jpg",
            "url": "/assets/mock_generated.jpg",
            "mime_type": "image/jpeg",
            "width": 1920,
            "height": 1080,
            "aspect_ratio": "16:9",
            "prompt": "Test Slide Visual",
            "source": "Google Gemini Imagen 3",
            "generated": True,
            "license": "AI Generated",
            "attribution": "Image generated via Google Gemini",
        }
        
        with patch("backend.presentation.presentation_api.ai_image_service.generate", return_value=mock_result):
            response = self.client.post(
                "/api/presentation/ai-image/generate",
                json={
                    "prompt": "Test Slide Visual",
                    "provider": "auto",
                    "style": "Professional",
                    "aspect_ratio": "16:9",
                    "topic": "Enterprise AI",
                    "slide_title": "AI in Healthcare",
                },
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["provider"], "gemini")
            self.assertEqual(data["image_url"], "/assets/mock_generated.jpg")
            self.assertTrue(data["generated"])


if __name__ == "__main__":
    unittest.main()
