from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.login import router as auth_router
from app.routes.userprofiles import router as userprofiles_router
from app.routes.update_user import router as update_user_router
from app.routes.create_folders import router as folders_router
from app.routes.storage_limits import router as storage_router
from app.routes.move_files import router as move_files_router
from app.routes.delete_folders_and_files import folders_router as delete_folders_router, files_router as delete_files_router
from app.routes.password_recovery import router as password_recovery_router
from app.routes.activity_history import router as activity_history_router
from app.routes.account_management import router as account_management_router

app = FastAPI(title="FYP Secure File Sharing API", version="0.1.0")

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
	allow_methods=["*"],		
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(userprofiles_router)
app.include_router(update_user_router)
app.include_router(folders_router)
app.include_router(storage_router)
app.include_router(move_files_router)
app.include_router(delete_folders_router)
app.include_router(delete_files_router)
app.include_router(password_recovery_router)
app.include_router(activity_history_router)
app.include_router(account_management_router)

# Health check
@app.get("/healthz")
def healthz() -> dict:
	return {"status": "ok"}
