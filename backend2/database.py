"""
Database Configuration - Directus CMS Connection
All data is managed through Directus CMS (no local PostgreSQL)
"""
import logging
import requests
from typing import Dict, List, Optional

from config import settings

# Configure logging
logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


class DirectusConnection:
    """
    Directus CMS bağlantısı ve yardımcı metodlar.
    Tüm veri Directus'ta saklanır, yerel veritabanı kullanılmaz.
    """

    def __init__(self):
        self.base_url = settings.DIRECTUS_URL.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {settings.DIRECTUS_TOKEN}",
            "Content-Type": "application/json"
        }

    def test_connection(self) -> bool:
        """Test Directus connection"""
        try:
            response = requests.get(
                f"{self.base_url}/server/info",
                headers=self.headers,
                timeout=5
            )
            if response.status_code == 200:
                logger.info("✅ Directus connection successful")
                return True
            else:
                logger.error(f"❌ Directus connection failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ Directus connection error: {e}")
            return False

    def get(self, collection: str, params: Dict = None) -> List[Dict]:
        """GET request to Directus"""
        try:
            response = requests.get(
                f"{self.base_url}/items/{collection}",
                headers=self.headers,
                params=params,
                timeout=10
            )
            if response.status_code == 200:
                return response.json().get('data', [])
            logger.error(f"Directus GET Error ({collection}): {response.text}")
            return []
        except Exception as e:
            logger.error(f"Directus GET Exception: {e}")
            return []

    def post(self, collection: str, data: Dict) -> Optional[Dict]:
        """POST request to Directus"""
        try:
            response = requests.post(
                f"{self.base_url}/items/{collection}",
                headers=self.headers,
                json=data,
                timeout=10
            )
            if response.status_code in [200, 201]:
                return response.json().get('data')
            logger.error(f"Directus POST Error ({collection}): {response.text}")
            return None
        except Exception as e:
            logger.error(f"Directus POST Exception: {e}")
            return None

    def patch(self, collection: str, item_id: int, data: Dict) -> Optional[Dict]:
        """PATCH request to Directus"""
        try:
            response = requests.patch(
                f"{self.base_url}/items/{collection}/{item_id}",
                headers=self.headers,
                json=data,
                timeout=10
            )
            if response.status_code == 200:
                return response.json().get('data')
            logger.error(f"Directus PATCH Error ({collection}): {response.text}")
            return None
        except Exception as e:
            logger.error(f"Directus PATCH Exception: {e}")
            return None

    def delete(self, collection: str, item_id: int) -> bool:
        """DELETE request to Directus"""
        try:
            response = requests.delete(
                f"{self.base_url}/items/{collection}/{item_id}",
                headers=self.headers,
                timeout=10
            )
            if response.status_code == 204:
                return True
            logger.error(f"Directus DELETE Error ({collection}): {response.text}")
            return False
        except Exception as e:
            logger.error(f"Directus DELETE Exception: {e}")
            return False


# Global Directus connection instance
directus = DirectusConnection()


def init_db():
    """
    Test Directus connection and verify collections exist.
    No local database initialization needed.
    """
    logger.info("🔍 Testing Directus connection...")

    if not directus.test_connection():
        raise ConnectionError("Failed to connect to Directus CMS")

    # Test critical collections
    required_collections = [
        "voises_customers",
        "voises_appointments",
        "voises_services",
        "voises_experts",
        "voises_campaigns"
    ]

    for collection in required_collections:
        try:
            result = directus.get(collection, params={"limit": 1})
            logger.info(f"✅ Collection '{collection}' is accessible")
        except Exception as e:
            logger.error(f"❌ Collection '{collection}' is NOT accessible: {e}")
            raise

    logger.info("✅ All Directus collections verified successfully")


if __name__ == "__main__":
    # Test database connection
    try:
        init_db()
        logger.info("✅ Directus setup complete!")
    except Exception as e:
        logger.error(f"❌ Directus setup failed: {e}")
