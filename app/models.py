from sqlalchemy import Column, String, DateTime, CheckConstraint, ForeignKey, Integer, Numeric, BigInteger, Text
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


# Free Account model
class FreeAccount(Base):
    __tablename__ = "free_account"

    account_id = Column(UUID(as_uuid=True), ForeignKey("account.account_id", ondelete="CASCADE"), primary_key=True)
    storage_limit_gb = Column(Integer, nullable=False, default=2)


# Paid Account model
class PaidAccount(Base):
    __tablename__ = "paid_account"

    account_id = Column(UUID(as_uuid=True), ForeignKey("account.account_id", ondelete="CASCADE"), primary_key=True)
    storage_limit_gb = Column(Integer, nullable=False, default=30)
    monthly_cost = Column(Numeric(10, 2), nullable=False, default=10.00)
    start_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    renewal_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'CANCELLED', 'EXPIRED')", name="check_paid_account_status"),
    )


# Folder model
class Folder(Base):
    __tablename__ = "folder"

    folder_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("account.account_id", ondelete="CASCADE"), nullable=False)
    parent_folder_id = Column(UUID(as_uuid=True), ForeignKey("folder.folder_id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# FileObject model (minimal model for table creation in tests)
class FileObject(Base):
    __tablename__ = "file_objects"

    file_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("account.account_id"), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    logical_path = Column(Text, nullable=False)
