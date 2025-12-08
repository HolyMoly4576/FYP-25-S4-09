from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from typing import Optional, List
import logging
import uuid
import json
from app.master_node_db import MasterNodeDB, get_master_db
from app.core.security import decode_access_token
from app.routes.login import oauth2_scheme

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/folders", tags=["folders"])

class CreateFolderRequest(BaseModel):
    name: str
    parent_folder_id: Optional[uuid.UUID] = None

class FolderResponse(BaseModel):
    folder_id: uuid.UUID
    name: str
    account_id: uuid.UUID
    parent_folder_id: Optional[uuid.UUID] = None
    created_at: str

class FoldersListResponse(BaseModel):
    folders: List[FolderResponse]
    total: int

def get_current_account(
    token=Depends(oauth2_scheme),
    master_db: MasterNodeDB = Depends(get_master_db)
) -> dict:
    token_str = token.credentials if hasattr(token, "credentials") else token
    payload = decode_access_token(token_str)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    
    account_id = payload.get("sub")
    if not account_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    
    account_result = master_db.select(
        "SELECT ACCOUNT_ID, USERNAME, EMAIL, ACCOUNT_TYPE, CREATED_AT FROM ACCOUNT WHERE ACCOUNT_ID = $1",
        [account_id]
    )
    
    if not account_result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    result = account_result[0]
    account_dict = {}
    for k, v in result.items():
        key_lower = k.lower()
        account_dict[key_lower] = v
    
    return account_dict

@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
def create_folder(
    body: CreateFolderRequest,
    request: Request,
    current_account: dict = Depends(get_current_account),
    master_db: MasterNodeDB = Depends(get_master_db)
):
    if body.name is None or body.name.strip() == "":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder name cannot be empty")
    
    try:
        if body.parent_folder_id is not None:
            parent = master_db.select(
                "SELECT FOLDER_ID FROM FOLDER WHERE FOLDER_ID = $1 AND ACCOUNT_ID = $2",
                [str(body.parent_folder_id), current_account["account_id"]]
            )
            
            if not parent:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent folder not found")
        
        if body.parent_folder_id is None:
            existing = master_db.select(
                "SELECT FOLDER_ID FROM FOLDER WHERE ACCOUNT_ID = $1 AND PARENT_FOLDER_ID IS NULL AND NAME = $2",
                [current_account["account_id"], body.name]
            )
        else:
            existing = master_db.select(
                "SELECT FOLDER_ID FROM FOLDER WHERE ACCOUNT_ID = $1 AND PARENT_FOLDER_ID = $2 AND NAME = $3",
                [current_account["account_id"], str(body.parent_folder_id), body.name]
            )
        
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder with same name already exists in this location")
        
        folder_id = uuid.uuid4()
        
        master_db.execute(
            """
            INSERT INTO FOLDER (FOLDER_ID, NAME, ACCOUNT_ID, PARENT_FOLDER_ID, CREATED_AT)
            VALUES ($1, $2, $3, $4, NOW())
            """,
            [str(folder_id), body.name.strip(), current_account["account_id"], 
             str(body.parent_folder_id) if body.parent_folder_id else None]
        )
        
        folder_result = master_db.select(
            "SELECT FOLDER_ID, NAME, ACCOUNT_ID, PARENT_FOLDER_ID, CREATED_AT FROM FOLDER WHERE FOLDER_ID = $1",
            [str(folder_id)]
        )
        
        if not folder_result:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created folder")
        
        folder = folder_result[0]
        
        try:
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            
            details = json.dumps({
                "folder_name": body.name,
                "parent_folder_id": str(body.parent_folder_id) if body.parent_folder_id else None
            })
            
            master_db.execute(
                """
                INSERT INTO ACTIVITY_LOG (ACTIVITY_ID, ACCOUNT_ID, ACTION_TYPE, RESOURCE_TYPE, RESOURCE_ID, IP_ADDRESS, USER_AGENT, DETAILS, CREATED_AT)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                """,
                [str(uuid.uuid4()), current_account["account_id"], "FOLDER_CREATE", "FOLDER",
                 str(folder_id), client_ip, user_agent, details]
            )
        except Exception as log_error:
            logger.warning(f"Failed to log folder creation activity: {str(log_error)}")
        
        folder_id_val = folder.get("folder_id") or folder.get("FOLDER_ID")
        name_val = folder.get("name") or folder.get("NAME")
        account_id_val = folder.get("account_id") or folder.get("ACCOUNT_ID")
        parent_folder_id_val = folder.get("parent_folder_id") or folder.get("PARENT_FOLDER_ID")
        created_at_val = folder.get("created_at") or folder.get("CREATED_AT")
        
        if hasattr(created_at_val, "isoformat"):
            created_at_str = created_at_val.isoformat()
        else:
            created_at_str = str(created_at_val)
        
        return FolderResponse(
            folder_id=uuid.UUID(str(folder_id_val)),
            name=name_val,
            account_id=uuid.UUID(str(account_id_val)),
            parent_folder_id=uuid.UUID(str(parent_folder_id_val)) if parent_folder_id_val else None,
            created_at=created_at_str
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating folder: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create folder: {str(e)}"
        )


@router.get("/list", response_model=FoldersListResponse)
def list_folders(
    parent_folder_id: Optional[uuid.UUID] = None,
    current_account: dict = Depends(get_current_account),
    master_db: MasterNodeDB = Depends(get_master_db)
):
    """
    List all folders for the current user.
    Optional: Filter by parent_folder_id to get folders within a specific folder.
    If parent_folder_id is None, returns root-level folders.
    If parent_folder_id is omitted as query param, returns ALL folders.
    """
    try:
        if parent_folder_id is None:
            # No query parameter provided - return ALL folders (excluding those in recycle bin)
            folders = master_db.select(
                """SELECT f.FOLDER_ID, f.NAME, f.ACCOUNT_ID, f.PARENT_FOLDER_ID, f.CREATED_AT 
                   FROM FOLDER f
                   LEFT JOIN recycle_bin rb ON (f.FOLDER_ID = rb.resource_id AND rb.resource_type = 'FOLDER' AND rb.is_recovered = 'FALSE')
                   WHERE f.ACCOUNT_ID = $1 AND rb.resource_id IS NULL
                   ORDER BY f.NAME""",
                [current_account["account_id"]]
            )
        else:
            # Specific parent provided - return children of that parent (excluding those in recycle bin)
            folders = master_db.select(
                """SELECT f.FOLDER_ID, f.NAME, f.ACCOUNT_ID, f.PARENT_FOLDER_ID, f.CREATED_AT 
                   FROM FOLDER f
                   LEFT JOIN recycle_bin rb ON (f.FOLDER_ID = rb.resource_id AND rb.resource_type = 'FOLDER' AND rb.is_recovered = 'FALSE')
                   WHERE f.ACCOUNT_ID = $1 AND f.PARENT_FOLDER_ID = $2 AND rb.resource_id IS NULL
                   ORDER BY f.NAME""",
                [current_account["account_id"], str(parent_folder_id)]
            )
        
        folder_responses = []
        for folder in folders:
            folder_id_val = folder.get("folder_id") or folder.get("FOLDER_ID")
            name_val = folder.get("name") or folder.get("NAME")
            account_id_val = folder.get("account_id") or folder.get("ACCOUNT_ID")
            parent_folder_id_val = folder.get("parent_folder_id") or folder.get("PARENT_FOLDER_ID")
            created_at_val = folder.get("created_at") or folder.get("CREATED_AT")
            
            if hasattr(created_at_val, "isoformat"):
                created_at_str = created_at_val.isoformat()
            else:
                created_at_str = str(created_at_val)
            
            folder_responses.append(FolderResponse(
                folder_id=uuid.UUID(str(folder_id_val)),
                name=name_val,
                account_id=uuid.UUID(str(account_id_val)),
                parent_folder_id=uuid.UUID(str(parent_folder_id_val)) if parent_folder_id_val else None,
                created_at=created_at_str
            ))
        
        return FoldersListResponse(
            folders=folder_responses,
            total=len(folder_responses)
        )
    
    except Exception as e:
        logger.error(f"Error listing folders: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list folders"
        )
