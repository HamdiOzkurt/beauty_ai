"""
Güzellik Merkezi Sesli Asistan - Veritabanı Yönetimi
SQLAlchemy session ve CRUD işlemleri
"""
from sqlalchemy import create_engine, and_, or_
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from typing import Optional, List
import logging

from models import Base, Customer, Appointment, Feedback, ConversationLog, SystemMetrics, AppointmentStatus
from config import settings

logger = logging.getLogger(__name__)

# Engine oluştur (PostgreSQL)
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Bağlantı kontrolü
    pool_size=10,        # Connection pool
    max_overflow=20,     # Max ekstra bağlantı
    echo=settings.DEBUG
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Veritabanını başlat ve tabloları oluştur"""
    Base.metadata.create_all(bind=engine)
    logger.info("Veritabanı tabloları oluşturuldu")


def get_db():
    """Veritabanı session'ı al (FastAPI dependency için)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== CUSTOMER CRUD ====================






def confirm_appointment(db: Session, appointment_code: str) -> Optional[Appointment]:
    """Randevuyu onayla"""
    appointment = get_appointment_by_code(db, appointment_code)
    if appointment:
        appointment.status = AppointmentStatus.CONFIRMED
        db.commit()
        db.refresh(appointment)
        logger.info(f"Randevu onaylandı: {appointment_code}")
        return appointment
    return None


def get_upcoming_appointments(db: Session, hours_ahead: int = 24) -> List[Appointment]:
    """Yaklaşan randevuları getir (hatırlatma için)"""
    now = datetime.utcnow()
    future = now + timedelta(hours=hours_ahead)
    
    return db.query(Appointment).filter(
        and_(
            Appointment.appointment_date >= now,
            Appointment.appointment_date <= future,
            Appointment.status == AppointmentStatus.CONFIRMED,
            Appointment.reminder_sent == False
        )
    ).all()


# ==================== FEEDBACK CRUD ====================

def create_feedback(
    db: Session,
    customer_id: int,
    rating: int,
    comment: Optional[str] = None,
    service_type: Optional[str] = None,
    expert_name: Optional[str] = None
) -> Feedback:
    """Yeni geri bildirim oluştur"""
    feedback = Feedback(
        customer_id=customer_id,
        rating=rating,
        comment=comment,
        service_type=service_type,
        expert_name=expert_name
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    logger.info(f"Yeni geri bildirim oluşturuldu: {rating}/5")
    return feedback


# ==================== CONVERSATION LOG ====================

def log_conversation(
    db: Session,
    session_id: str,
    user_message: Optional[str] = None,
    agent_response: Optional[str] = None,
    intent_detected: Optional[str] = None,
    customer_id: Optional[int] = None
):
    """Konuşmayı logla"""
    log = ConversationLog(
        session_id=session_id,
        user_message=user_message,
        agent_response=agent_response,
        intent_detected=intent_detected,
        customer_id=customer_id
    )
    db.add(log)
    db.commit()


# ==================== METRICS ====================

def get_daily_metrics(db: Session, date: datetime) -> Optional[SystemMetrics]:
    """Belirli bir günün metriklerini getir"""
    return db.query(SystemMetrics).filter(
        SystemMetrics.metric_date == date.date()
    ).first()


def calculate_daily_metrics(db: Session, date: datetime) -> SystemMetrics:
    """Günlük metrikleri hesapla ve kaydet"""
    start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)
    
    # Randevu istatistikleri
    appointments = db.query(Appointment).filter(
        and_(
            Appointment.created_at >= start_of_day,
            Appointment.created_at < end_of_day
        )
    ).all()
    
    metrics = SystemMetrics(
        metric_date=start_of_day,
        total_appointments=len(appointments),
        confirmed_appointments=sum(1 for a in appointments if a.status == AppointmentStatus.CONFIRMED),
        cancelled_appointments=sum(1 for a in appointments if a.status == AppointmentStatus.CANCELLED),
        completed_appointments=sum(1 for a in appointments if a.status == AppointmentStatus.COMPLETED),
        total_revenue=sum(a.price or 0 for a in appointments if a.status == AppointmentStatus.COMPLETED)
    )
    
    db.add(metrics)
    db.commit()
    db.refresh(metrics)
    return metrics
