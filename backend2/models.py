"""
Models - Simple Data Classes
Directus'tan gelen verileri Python objelerine çevirmek için helper classes.
SQLAlchemy kullanılmıyor, tüm veri Directus'ta saklanıyor.
"""
from datetime import datetime
from typing import Optional, List


class DirectusItem:
    """
    Directus'tan gelen JSON verisini Python objesine çevirir.
    Generic class - tüm collection'lar için kullanılabilir.
    """

    def __init__(self, **entries):
        self.__dict__.update(entries)

        # Tarih alanlarını otomatik dönüştür
        date_fields = [
            'created_date', 'last_visited_date', 'date_time',
            'end_date', 'created_at', 'start_date', 'updated_at'
        ]

        for field in date_fields:
            if hasattr(self, field) and getattr(self, field):
                val = getattr(self, field)
                if isinstance(val, str):
                    try:
                        # ISO formatındaki 'Z' harfini temizle
                        setattr(self, field, datetime.fromisoformat(val.replace('Z', '+00:00')))
                    except ValueError:
                        pass  # Format uymazsa string olarak kalsın

    def to_dict(self) -> dict:
        """Convert object to dictionary"""
        return self.__dict__

    def __repr__(self):
        class_name = self.__class__.__name__
        return f"<{class_name} {self.__dict__}>"


# ============================================================================
# Helper Functions for Data Conversion
# ============================================================================

def to_directus_item(data: dict) -> DirectusItem:
    """Convert dictionary to DirectusItem"""
    return DirectusItem(**data)


def to_directus_items(data_list: List[dict]) -> List[DirectusItem]:
    """Convert list of dictionaries to list of DirectusItems"""
    return [DirectusItem(**item) for item in data_list]


# ============================================================================
# Optional: Type Hints for Directus Collections
# ============================================================================

class Customer(DirectusItem):
    """
    voises_customers collection type hint.
    Directus'ta saklanır, sadece type checking için.
    """
    id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    tenant_id: Optional[int] = None
    created_date: Optional[datetime] = None


class Appointment(DirectusItem):
    """
    voises_appointments collection type hint.
    Directus'ta saklanır, sadece type checking için.
    """
    id: Optional[int] = None
    customer_id: Optional[int] = None
    expert_id: Optional[int] = None
    service_id: Optional[int] = None
    date_time: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    tenant_id: Optional[int] = None
    created_at: Optional[datetime] = None


class Service(DirectusItem):
    """
    voises_services collection type hint.
    Directus'ta saklanır, sadece type checking için.
    """
    id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minute: Optional[int] = None
    price: Optional[float] = None
    is_active: Optional[bool] = None
    tenant_id: Optional[int] = None


class Expert(DirectusItem):
    """
    voises_experts collection type hint.
    Directus'ta saklanır, sadece type checking için.
    """
    id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: Optional[bool] = None
    tenant_id: Optional[int] = None
    services: Optional[List] = None  # Many-to-many relation


class Campaign(DirectusItem):
    """
    voises_campaigns collection type hint.
    Directus'ta saklanır, sadece type checking için.
    """
    id: Optional[int] = None
    name: Optional[str] = None
    code: Optional[str] = None
    discount_rate: Optional[float] = None
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    tenant_id: Optional[int] = None
