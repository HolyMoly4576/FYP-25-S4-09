from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.login import router as auth_router
from app.routes.userprofiles import router as userprofiles_router

app = FastAPI(title="FYP Secure File Sharing API", version="0.1.0")

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(userprofiles_router)

# Health check?
@app.get("/healthz")
def healthz() -> dict:
	return {"status": "ok"}


