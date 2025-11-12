"""
Güzellik Merkezi Sesli Asistan - Veritabanı Modelleri
SQLAlchemy ORM modelleri
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship, declarative_base
import enum
import secrets

Base = declarative_base()


class AppointmentStatus(enum.Enum):
    """Randevu durumları"""
    PENDING = "pending"           # Beklemede
    CONFIRMED = "confirmed"       # Onaylandı
    CANCELLED = "cancelled"       # İptal edildi
    COMPLETED = "completed"       # Tamamlandı
    NO_SHOW = "no_show"          # Gelmedi


class Customer(Base):
    """Müşteri modeli"""
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)  # Sadece bu kalacak
    phone = Column(String(20), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=True)
    
    # İstatistikler
    total_appointments = Column(Integer, default=0)
    completed_appointments = Column(Integer, default=0)
    cancelled_appointments = Column(Integer, default=0)
    no_show_count = Column(Integer, default=0)
    
    # Kampanya bilgileri
    is_first_appointment = Column(Boolean, default=True)
    loyalty_points = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # İlişkiler
    appointments = relationship("Appointment", back_populates="customer", cascade="all, delete-orphan")
    feedbacks = relationship("Feedback", back_populates="customer", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Customer {self.full_name} ({self.phone})>"
    
    # @property full_name metodunu SİL - Artık gerek yok çünkü direkt kolon var


class Appointment(Base):
    """Randevu modeli"""
    __tablename__ = "appointments"
    
    id = Column(Integer, primary_key=True, index=True)
    appointment_code = Column(String(10), unique=True, nullable=False, index=True)
    
    # Müşteri bilgisi
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    
    # Randevu detayları
    expert_name = Column(String(100), nullable=False)  # Uzman adı
    service_type = Column(String(100), nullable=False)  # Hizmet türü
    service_duration = Column(Integer, nullable=False)  # Dakika cinsinden
    
    # Tarih ve saat
    appointment_date = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    
    # Durum
    status = Column(SQLEnum(AppointmentStatus), default=AppointmentStatus.PENDING)
    
    # Fiyat ve ödeme
    price = Column(Float, nullable=True)
    deposit_amount = Column(Float, default=0.0)
    deposit_paid = Column(Boolean, default=False)
    
    # Kampanya
    campaign_applied = Column(String(100), nullable=True)
    discount_percentage = Column(Float, default=0.0)
    
    # Hatırlatma
    reminder_sent = Column(Boolean, default=False)
    reminder_sent_at = Column(DateTime, nullable=True)
    
    # Notlar
    notes = Column(Text, nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cancelled_at = Column(DateTime, nullable=True)
    
    # İlişkiler
    customer = relationship("Customer", back_populates="appointments")
    
    def __repr__(self):
        return f"<Appointment {self.appointment_code} - {self.service_type} on {self.appointment_date}>"
    
    @staticmethod
    def generate_code():
        """Benzersiz randevu kodu üret (6 haneli alfanumerik)"""
        return secrets.token_urlsafe(6)[:6].upper()


class Feedback(Base):
    """Müşteri geri bildirimi modeli"""
    __tablename__ = "feedbacks"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    
    # Geri bildirim
    rating = Column(Integer, nullable=False)  # 1-5 arası
    comment = Column(Text, nullable=True)
    
    # Hangi randevuyla ilgili (opsiyonel)
    service_type = Column(String(100), nullable=True)
    expert_name = Column(String(100), nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # İlişkiler
    customer = relationship("Customer", back_populates="feedbacks")
    
    def __repr__(self):
        return f"<Feedback {self.rating}/5 from Customer {self.customer_id}>"


class ConversationLog(Base):
    """Konuşma kayıtları (debugging ve analiz için)"""
    __tablename__ = "conversation_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    
    # Konuşma detayları
    user_message = Column(Text, nullable=True)
    agent_response = Column(Text, nullable=True)
    
    # Metadata
    intent_detected = Column(String(100), nullable=True)
    tools_used = Column(Text, nullable=True)  # JSON string
    
    # Müşteri bilgisi (varsa)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<ConversationLog {self.session_id} at {self.created_at}>"


class SystemMetrics(Base):
    """Sistem metrikleri ve istatistikler"""
    __tablename__ = "system_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Metrik bilgileri
    metric_date = Column(DateTime, nullable=False, index=True)
    
    # Randevu istatistikleri
    total_appointments = Column(Integer, default=0)
    confirmed_appointments = Column(Integer, default=0)
    cancelled_appointments = Column(Integer, default=0)
    completed_appointments = Column(Integer, default=0)
    
    # Müşteri istatistikleri
    new_customers = Column(Integer, default=0)
    returning_customers = Column(Integer, default=0)
    
    # Hizmet istatistikleri
    most_popular_service = Column(String(100), nullable=True)
    most_popular_expert = Column(String(100), nullable=True)
    
    # Gelir
    total_revenue = Column(Float, default=0.0)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<SystemMetrics for {self.metric_date.date()}>"
