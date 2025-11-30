# app/master_node_db.py
import requests
import os
from typing import Any, Dict, List, Optional

class MasterNodeDB:
    """Database interface that connects to master node instead of direct database"""
    
    def __init__(self):
        self.master_node_url = os.getenv("MASTER_NODE_URL", "http://master_node:3000")
        self.query_endpoint = f"{self.master_node_url}/query"
    
    def execute_query(self, sql: str, params: List[Any] = None) -> Dict[str, Any]:
        """Execute a SQL query through the master node"""
        try:
            payload = {
                "sql": sql,
                "params": params or []
            }
            
            response = requests.post(self.query_endpoint, json=payload)
            response.raise_for_status()
            
            return response.json()
        
        except requests.RequestException as e:
            raise Exception(f"Failed to execute query on master node: {str(e)}")
    
    def select(self, sql: str, params: List[Any] = None) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results"""
        result = self.execute_query(sql, params)
        if result.get("success"):
            return result.get("data", [])
        else:
            raise Exception(f"Query failed: {result}")
    
    def execute(self, sql: str, params: List[Any] = None) -> Dict[str, Any]:
        """Execute INSERT, UPDATE, DELETE queries"""
        result = self.execute_query(sql, params)
        if result.get("success"):
            return result.get("data", {})
        else:
            raise Exception(f"Query failed: {result}")
    
    def get_nodes(self) -> List[Dict[str, Any]]:
        """Get all storage nodes from master node"""
        try:
            response = requests.get(f"{self.master_node_url}/nodes")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise Exception(f"Failed to get nodes: {str(e)}")
    
    def get_file_fragments(self, file_id: str) -> List[Dict[str, Any]]:
        """Get fragments for a specific file"""
        try:
            response = requests.get(f"{self.master_node_url}/fragments/{file_id}")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise Exception(f"Failed to get file fragments: {str(e)}")
    
    def store_fragment_info(self, file_id: str, node_id: str, fragment_order: int, 
                           fragment_size: int, fragment_hash: str) -> Dict[str, Any]:
        """Store fragment information in master node database"""
        try:
            payload = {
                "fileId": file_id,
                "nodeId": node_id,
                "fragmentOrder": fragment_order,
                "fragmentSize": fragment_size,
                "fragmentHash": fragment_hash
            }
            
            response = requests.post(f"{self.master_node_url}/fragments", json=payload)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise Exception(f"Failed to store fragment info: {str(e)}")

# Global instance
master_db = MasterNodeDB()

def get_master_db() -> MasterNodeDB:
    """Get master node database instance"""
    return master_db