
from sqlalchemy import select
from database.session import SessionLocal
from database.models import Staff
from config import ADMIN_ID

def get_staff_ids(role=None):
    with SessionLocal() as session:
        query = select(Staff.telegram_id)
        if role:
            query = query.filter(Staff.role == role)
        return [row for row in session.execute(query).scalars().all()]

def is_admin(user_id: int) -> bool:
    if user_id == ADMIN_ID:  # Супер-админ из config.py
        return True
    with SessionLocal() as session:
        staff = session.query(Staff).filter_by(telegram_id=user_id, role='admin').first()
        return staff is not None