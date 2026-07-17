import datetime
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, UniqueConstraint
from app.infrastructure.database import Base

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)       
    type = Column(String)                                                               
    message = Column(String)                                                            
    is_read = Column(Boolean, default=False)                                            
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
