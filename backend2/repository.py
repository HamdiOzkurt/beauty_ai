"""
Backend2 - Repository Layer (Directus-Only)
Data access layer for Directus CMS
NO local PostgreSQL - all data managed through Directus
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
import random
import string
import logging

from config import settings
from database import directus
from models import DirectusItem, Customer, Appointment, Service, Expert, Campaign

logger = logging.getLogger(__name__)


# ============================================================================
# Base Repository
# ============================================================================

class BaseRepository:
    """Base repository with common Directus operations"""

    def __init__(self, collection_name: str):
        self.collection = collection_name

    def get_all(self, params: Dict = None) -> List[DirectusItem]:
        """Get all items from collection"""
        data = directus.get(self.collection, params)
        return [DirectusItem(**item) for item in data]

    def get_by_id(self, item_id: int) -> Optional[DirectusItem]:
        """Get single item by ID"""
        params = {"filter[id][_eq]": item_id, "limit": 1}
        data = directus.get(self.collection, params)
        return DirectusItem(**data[0]) if data else None

    def create(self, data: Dict) -> Optional[DirectusItem]:
        """Create new item"""
        result = directus.post(self.collection, data)
        return DirectusItem(**result) if result else None

    def update(self, item_id: int, data: Dict) -> Optional[DirectusItem]:
        """Update existing item"""
        result = directus.patch(self.collection, item_id, data)
        return DirectusItem(**result) if result else None

    def delete(self, item_id: int) -> bool:
        """Delete item"""
        return directus.delete(self.collection, item_id)


# ============================================================================
# Service Repository
# ============================================================================

class ServiceRepository(BaseRepository):
    """voises_services collection operations"""

    def __init__(self):
        super().__init__("voises_services")

    def list_all(self) -> List[Service]:
        """List all active services for current tenant"""
        params = {
            "filter[_and][0][is_active][_eq]": True,
            "filter[_and][1][tenant_id][_eq]": settings.TENANT_ID,
            "fields": "*"
        }
        data = directus.get(self.collection, params)
        return [Service(**item) for item in data]

    def get_by_name(self, service_name: str) -> Optional[Service]:
        """Get service by name"""
        params = {
            "filter[_and][0][name][_icontains]": service_name,
            "filter[_and][1][tenant_id][_eq]": settings.TENANT_ID,
            "limit": 1
        }
        data = directus.get(self.collection, params)
        return Service(**data[0]) if data else None


# ============================================================================
# Expert Repository
# ============================================================================

class ExpertRepository(BaseRepository):
    """voises_experts collection operations"""

    def __init__(self):
        super().__init__("voises_experts")

    def list_all(self, service_name: Optional[str] = None) -> List[Expert]:
        """List all active experts, optionally filtered by service"""
        params = {
            "filter[_and][0][is_active][_eq]": True,
            "filter[_and][1][tenant_id][_eq]": settings.TENANT_ID,
            "fields": "*,services.voises_services_id.*"
        }

        data = directus.get(self.collection, params)
        experts = []

        for exp_data in data:
            # Parse specialties from many-to-many relation
            specialties = []
            if 'services' in exp_data and exp_data['services']:
                for s in exp_data['services']:
                    if isinstance(s, dict) and s.get('voises_services_id'):
                        service_data = s['voises_services_id']
                        if isinstance(service_data, dict) and 'name' in service_data:
                            specialties.append(service_data['name'])

            expert = Expert(**exp_data)
            expert.specialties = specialties

            # Filter by service if specified
            if service_name:
                if any(service_name.lower() in s.lower() for s in specialties):
                    experts.append(expert)
            else:
                experts.append(expert)

        return experts

    def get_by_name(self, first_name: str, last_name: str = "") -> Optional[Expert]:
        """Get expert by name"""
        params = {
            "filter[_and][0][first_name][_icontains]": first_name,
            "filter[_and][1][tenant_id][_eq]": settings.TENANT_ID,
            "limit": 1
        }
        if last_name:
            params["filter[_and][2][last_name][_icontains]"] = last_name

        data = directus.get(self.collection, params)
        return Expert(**data[0]) if data else None


# ============================================================================
# Campaign Repository
# ============================================================================

class CampaignRepository(BaseRepository):
    """voises_campaigns collection operations"""

    def __init__(self):
        super().__init__("voises_campaigns")

    def list_active(self) -> List[Campaign]:
        """List active campaigns (within date range)"""
        now = datetime.utcnow()
        params = {
            "filter[tenant_id][_eq]": settings.TENANT_ID
        }

        all_campaigns = directus.get(self.collection, params)
        active_campaigns = []

        for c_data in all_campaigns:
            try:
                start_date_str = c_data.get('start_date')
                end_date_str = c_data.get('end_date')

                if start_date_str and end_date_str:
                    start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00').replace('+00:00', ''))
                    end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00').replace('+00:00', ''))

                    if start_date <= now <= end_date:
                        active_campaigns.append(Campaign(**c_data))
            except Exception as e:
                logger.error(f"Campaign date parse error: {e}")
                continue

        return active_campaigns


# ============================================================================
# Customer Repository
# ============================================================================

class CustomerRepository(BaseRepository):
    """voises_customers collection operations"""

    def __init__(self):
        super().__init__("voises_customers")

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Normalize phone number to +90 format"""
        phone = phone.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')

        if phone.startswith('+90'):
            return phone
        if phone.startswith('0'):
            return '+90' + phone[1:]
        return '+90' + phone

    def get_by_phone(self, phone: str) -> Optional[Customer]:
        """Get customer by phone number"""
        normalized_phone = self.normalize_phone(phone)

        params = {
            "filter[_and][0][phone_number][_eq]": normalized_phone,
            "filter[_and][1][tenant_id][_eq]": settings.TENANT_ID,
            "limit": 1
        }
        data = directus.get(self.collection, params)
        return Customer(**data[0]) if data else None

    def create_customer(self, full_name: str, phone: str) -> Customer:
        """Create new customer"""
        normalized_phone = self.normalize_phone(phone)
        parts = full_name.strip().split(' ', 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        payload = {
            "tenant_id": settings.TENANT_ID,
            "first_name": first_name,
            "last_name": last_name,
            "phone_number": normalized_phone,
            "created_date": datetime.now().replace(tzinfo=None).isoformat(),
        }

        result = directus.post(self.collection, payload)
        if result:
            return Customer(**result)
        raise Exception("Failed to create customer")

    def get_appointments(self, customer_id: int, limit: int = 10) -> List[Appointment]:
        """Get customer appointments"""
        params = {
            "filter[_and][0][customer_id][_eq]": customer_id,
            "filter[_and][1][tenant_id][_eq]": settings.TENANT_ID,
            "filter[_and][2][status][_eq]": "confirmed",
            "sort": "-date_time",
            "limit": limit,
            "fields": "*.*"
        }

        data = directus.get("voises_appointments", params)
        return [Appointment(**item) for item in data]


# ============================================================================
# Appointment Repository
# ============================================================================

class AppointmentRepository(BaseRepository):
    """voises_appointments collection operations"""

    def __init__(self):
        super().__init__("voises_appointments")

    def check_availability(
        self,
        expert_id: int,
        start_time: datetime,
        duration_minutes: int
    ) -> bool:
        """Check if expert is available at specified time"""
        end_time = start_time + timedelta(minutes=duration_minutes)

        params = {
            "filter[expert_id][_eq]": expert_id,
            "filter[tenant_id][_eq]": settings.TENANT_ID,
            "fields": "id,date_time,end_date,status",
            "limit": -1
        }

        all_appointments = directus.get(self.collection, params)
        conflicts = []

        for appt in all_appointments:
            status = appt.get('status', '').lower()
            if status not in ['pending', 'confirmed']:
                continue

            try:
                appt_start_str = appt.get('date_time')
                appt_end_str = appt.get('end_date')

                if not appt_start_str or not appt_end_str:
                    continue

                appt_start = datetime.fromisoformat(appt_start_str.replace('Z', '+00:00').replace('+00:00', ''))
                appt_end = datetime.fromisoformat(appt_end_str.replace('Z', '+00:00').replace('+00:00', ''))

                # Conflict check
                if (start_time < appt_end) and (end_time > appt_start):
                    conflicts.append(appt)
            except Exception as e:
                logger.error(f"Date parse error: {e}")
                continue

        return len(conflicts) == 0

    def find_available_slots_for_day(
        self,
        service_type: str,
        day: datetime.date,
        duration_minutes: int,
        expert_name: Optional[str] = None
    ) -> List[Tuple[datetime, str]]:
        """Find available time slots for a specific day"""
        start_of_day = datetime.combine(day, datetime.min.time())
        end_of_day = datetime.combine(day, datetime.max.time())

        # Get all appointments for the day
        params = {
            "filter[date_time][_gte]": start_of_day.isoformat(),
            "filter[date_time][_lte]": end_of_day.isoformat(),
            "filter[tenant_id][_eq]": settings.TENANT_ID,
            "fields": "id,date_time,end_date,status,expert_id.id,expert_id.first_name,expert_id.last_name",
            "limit": -1
        }

        all_appointments = directus.get(self.collection, params)
        daily_appointments = [
            appt for appt in all_appointments
            if appt.get('status', '').lower() in ['confirmed', 'pending']
        ]

        # Get active experts for this service
        expert_repo = ExpertRepository()
        experts = expert_repo.list_all(service_name=service_type)

        # Filter by expert name if specified
        if expert_name:
            experts = [e for e in experts if expert_name.lower() in f"{e.first_name} {e.last_name}".lower()]

        # Convert to dict format for compatibility
        experts_data = [{"id": e.id, "first_name": e.first_name, "last_name": e.last_name} for e in experts]

        # Calculate available slots
        available_slots = []
        start_business = datetime.combine(day, datetime.min.time()).replace(hour=settings.BUSINESS_HOURS_START)
        end_business = datetime.combine(day, datetime.min.time()).replace(hour=settings.BUSINESS_HOURS_END)

        potential_slot = start_business

        while potential_slot + timedelta(minutes=duration_minutes) <= end_business:
            slot_end = potential_slot + timedelta(minutes=duration_minutes)

            for expert in experts_data:
                exp_id = expert['id']
                exp_full_name = f"{expert.get('first_name', '')} {expert.get('last_name', '')}".strip()

                is_taken = False
                for appt in daily_appointments:
                    appt_exp_id = appt.get('expert_id')
                    if isinstance(appt_exp_id, dict):
                        appt_exp_id = appt_exp_id.get('id')

                    if appt_exp_id != exp_id:
                        continue

                    appt_start = datetime.fromisoformat(appt['date_time'].replace('Z', '+00:00')).replace(tzinfo=None)
                    appt_end = datetime.fromisoformat(appt['end_date'].replace('Z', '+00:00')).replace(tzinfo=None)

                    if (potential_slot < appt_end) and (slot_end > appt_start):
                        is_taken = True
                        break

                if not is_taken:
                    available_slots.append((potential_slot, exp_full_name))

            potential_slot += timedelta(minutes=settings.APPOINTMENT_SLOT_MINUTES)

        return available_slots

    def create_appointment(
        self,
        customer_phone: str,
        customer_name: str,
        expert_name: str,
        service_type: str,
        appointment_date: datetime
    ) -> Appointment:
        """Create new appointment in Directus"""
        # Get customer
        customer_repo = CustomerRepository()
        customer = customer_repo.get_by_phone(customer_phone)

        if not customer:
            customer = customer_repo.create_customer(customer_name, customer_phone)

        # Get expert
        exp_parts = expert_name.split(' ', 1)
        expert_repo = ExpertRepository()
        expert = expert_repo.get_by_name(exp_parts[0], exp_parts[1] if len(exp_parts) > 1 else "")

        if not expert:
            raise Exception(f"Expert not found: {expert_name}")

        # Get service
        service_repo = ServiceRepository()
        service = service_repo.get_by_name(service_type)

        if not service:
            raise Exception(f"Service not found: {service_type}")

        # Calculate duration
        duration = getattr(service, 'duration_minute', 60)
        if isinstance(duration, str):
            try:
                time_parts = duration.split(':')
                duration = int(time_parts[0]) * 60 + int(time_parts[1])
            except:
                duration = 60

        end_time = appointment_date + timedelta(minutes=duration)
        appt_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        payload = {
            "tenant_id": settings.TENANT_ID,
            "customer_id": customer.id,
            "expert_id": expert.id,
            "service_id": service.id,
            "date_time": appointment_date.isoformat(),
            "end_date": end_time.isoformat(),
            "status": "confirmed",
            "created_at": datetime.now().replace(tzinfo=None).isoformat(),
            "notes": f"Auto-generated Code: {appt_code}"
        }

        result = directus.post(self.collection, payload)
        if result:
            appointment = Appointment(**result)
            appointment.appointment_code = appt_code
            return appointment

        raise Exception("Failed to create appointment")

    def cancel_appointment(self, appointment_id: int, reason: str = "Customer request") -> bool:
        """Cancel appointment"""
        payload = {
            "status": "cancelled",
            "notes": f"Cancellation Reason: {reason}"
        }

        result = directus.patch(self.collection, appointment_id, payload)
        return result is not None
