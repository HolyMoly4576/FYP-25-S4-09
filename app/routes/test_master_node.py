from fastapi import APIRouter, HTTPException
from app.master_node_db import get_master_db

router = APIRouter(prefix="/test", tags=["testing"])

@router.get("/master-node-connection")
async def test_master_node_connection():
    """Test connection to master node database"""
    try:
        master_db = get_master_db()
        
        # Test basic query
        result = master_db.select("SELECT COUNT(*) as node_count FROM node")
        
        # Get all nodes
        nodes = master_db.select("SELECT * FROM node")
        
        return {
            "status": "success",
            "message": "Successfully connected to master node database",
            "node_count": result[0]["node_count"] if result else 0,
            "nodes": nodes
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to master node: {str(e)}"
        )

@router.get("/storage-nodes")
async def get_storage_nodes():
    """Get all storage nodes from master node"""
    try:
        master_db = get_master_db()
        nodes = master_db.get_nodes()
        storage_nodes = [node for node in nodes if node.get("node_role") == "STORAGE"]
        
        return {
            "status": "success",
            "storage_nodes": storage_nodes,
            "count": len(storage_nodes)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get storage nodes: {str(e)}"
        )