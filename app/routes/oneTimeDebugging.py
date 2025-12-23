# app/routes/debug_migrations.py
from fastapi import APIRouter, Depends
from app.master_node_db import MasterNodeDB, get_master_db

router = APIRouter(prefix="/debug", tags=["debug"])

@router.post("/migrate-add-account-status")
def migrate_add_account_status(master_db: MasterNodeDB = Depends(get_master_db)):
    master_db.execute(
        """
        ALTER TABLE account
        ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';
        """,
        [],
    )
    return {"message": "account.status column ensured"}
