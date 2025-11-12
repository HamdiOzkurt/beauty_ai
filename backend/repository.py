"""
Veritabanı İşlemleri Katmanı (Repository Pattern)

Bu modül, veritabanı CRUD (Create, Read, Update, Delete) işlemlerini soyutlar.
Her bir model (örn: Customer, Appointment) için bir Repository sınıfı bulunur.
Bu, iş mantığının (business logic) veritabanı sorgularından ayrılmasına yardımcı olur.
"""

from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import and_, or_

from database import SessionLocal
from models import Customer, Appointment, AppointmentStatus
from config import settings, SERVICE_DURATIONS, AVAILABLE_EXPERTS
import random
import string

class CustomerRepository:
    """Müşteri modeli için veritabanı işlemleri."""

    def get_by_phone(self, phone: str) -> Optional[Customer]:
        """Telefon numarasına göre bir müşteri bulur."""
        db = SessionLocal()
        try:
            customer = db.query(Customer).filter(Customer.phone == phone).first()
            return customer
        finally:
            db.close()

    def get_appointments(self, customer_id: int, limit: int = 5, include_cancelled: bool = False) -> list[Appointment]:
        """Bir müşterinin geçmiş randevularını getirir."""
        db = SessionLocal()
        try:
            query = db.query(Appointment).filter(Appointment.customer_id == customer_id)
            
            # İptal edilenleri dahil etme (varsayılan)
            if not include_cancelled:
                query = query.filter(Appointment.status != AppointmentStatus.CANCELLED)
            
            appointments = query.order_by(Appointment.appointment_date.desc())\
                .limit(limit)\
                .all()
            return appointments
        finally:
            db.close()

    def create(self, full_name: str, phone: str, email: str = None) -> Customer:
        """Yeni bir müşteri oluşturur."""
        db = SessionLocal()
        try:
            customer = Customer(
                full_name=full_name,  # Tek parametre
                phone=phone,
                email=email
            )
            db.add(customer)
            db.commit()
            db.refresh(customer)
            return customer
        finally:
            db.close()

class AppointmentRepository:
    """Randevu modeli için veritabanı işlemleri."""

    def check_availability(
        self,
        expert_name: str,
        start_time: datetime,
        duration_minutes: int
    ) -> bool:
        """Uzmanın belirtilen saatte müsait olup olmadığını kontrol eder."""
        db = SessionLocal()
        try:
            end_time = start_time + timedelta(minutes=duration_minutes)
            conflicts = db.query(Appointment).filter(
                and_(
                    Appointment.expert_name == expert_name,
                    Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                    or_(
                        and_(
                            Appointment.appointment_date <= start_time,
                            Appointment.end_time > start_time
                        ),
                        and_(
                            Appointment.appointment_date < end_time,
                            Appointment.end_time >= end_time
                        ),
                        and_(
                            Appointment.appointment_date >= start_time,
                            Appointment.end_time <= end_time
                        )
                    )
                )
            ).first()
            return conflicts is None
        finally:
            db.close()

    def get_by_code(self, appointment_code: str) -> Optional[Appointment]:
        """Randevu koduna göre bir randevu bulur."""
        db = SessionLocal()
        try:
            appointment = db.query(Appointment).filter(Appointment.appointment_code == appointment_code).first()
            return appointment
        finally:
            db.close()

    def create(
        self,
        customer_id: int,
        expert_name: str,
        service_type: str,
        appointment_date: datetime
    ) -> Appointment:
        """Yeni bir randevu oluşturur."""
        db = SessionLocal()
        try:
            # 6 haneli benzersiz randevu kodu oluştur
            appointment_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            
            # Hizmet süresini al
            duration = SERVICE_DURATIONS.get(service_type, 60)
            end_time = appointment_date + timedelta(minutes=duration)
            
            appointment = Appointment(
                customer_id=customer_id,
                expert_name=expert_name,
                service_type=service_type,
                service_duration=duration,
                appointment_date=appointment_date,
                end_time=end_time,
                appointment_code=appointment_code,
                status=AppointmentStatus.CONFIRMED
            )
            db.add(appointment)
            db.commit()
            db.refresh(appointment)
            return appointment
        finally:
            db.close()

    def cancel(self, appointment_code: str, reason: Optional[str] = None) -> Optional[Appointment]:
        """Bir randevuyu koduna göre bulur ve iptal eder."""
        db = SessionLocal()
        try:
            appointment = db.query(Appointment).filter(Appointment.appointment_code == appointment_code).first()
            if appointment and appointment.status != AppointmentStatus.CANCELLED:
                appointment.status = AppointmentStatus.CANCELLED
                appointment.cancelled_at = datetime.utcnow()
                appointment.cancellation_reason = reason
                db.commit()
                db.refresh(appointment)
                return appointment
            return None # Ya da zaten iptal edilmişse appointment'ı döndür
        finally:
            db.close()

    def find_available_expert(self, start_time: datetime, duration_minutes: int) -> Optional[str]:
        """Belirtilen zaman aralığı için müsait bir uzman bulur."""
        db = SessionLocal()
        try:
            all_experts = AVAILABLE_EXPERTS
            random.shuffle(all_experts)  # Uzmanları rastgele sırala

            for expert_name in all_experts:
                if self.check_availability(expert_name, start_time, duration_minutes):
                    return expert_name
            return None
        finally:
            db.close()

    def find_available_slots_for_day(self, service_type: str, day: datetime.date, duration_minutes: int, expert_name: Optional[str] = None) -> List[tuple[datetime, str]]:
        """Belirli bir gün, hizmet ve uzman için tüm uygun (saat, uzman) çiftlerini bulur."""
        db = SessionLocal()
        try:
            start_of_day = datetime.combine(day, datetime.min.time()).replace(hour=settings.BUSINESS_HOURS_START)
            end_of_day = datetime.combine(day, datetime.min.time()).replace(hour=settings.BUSINESS_HOURS_END)
            
            potential_slot = start_of_day
            available_slots = []

            experts_to_check = [expert_name] if expert_name else [e["full_name"] for e in settings.EXPERTS.values()]
            normalized_service_type = service_type.replace(' ', '_').lower()

            while potential_slot + timedelta(minutes=duration_minutes) <= end_of_day:
                for expert in experts_to_check:
                    expert_info = next((e for e_key, e in settings.EXPERTS.items() if e["full_name"] == expert), None)
                    
                    if not expert_info or normalized_service_type not in expert_info.get("specialties", []):
                        continue

                    # Check if this expert is available at this specific time slot
                    if self.check_availability(expert, potential_slot, duration_minutes):
                        available_slots.append((potential_slot, expert))
                
                potential_slot += timedelta(minutes=settings.APPOINTMENT_SLOT_MINUTES)
            
            return available_slots
        finally:
            db.close()
