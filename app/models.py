from sqlalchemy import Column, String, DateTime, CheckConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base
import uuid

# Base declarative class
Base = declarative_base()

# Table model
class Account(Base):
    __tablename__ = "account"

    account_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), nullable=False, unique=True)
    email = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    account_type = Column(String(20), nullable=False)

    __table_args__ = (
        CheckConstraint("account_type IN ('FREE', 'PAID', 'SYSADMIN')", name="check_account_type"),
    )


# Folder model
class Folder(Base):
    __tablename__ = "folder"

    folder_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("account.account_id"), nullable=False)
    parent_folder_id = Column(UUID(as_uuid=True), ForeignKey("folder.folder_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
