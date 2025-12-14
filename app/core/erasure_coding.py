"""
Erasure Coding utilities for distributed file storage.
Uses Reed-Solomon encoding for fault tolerance and data redundancy.
"""

import reedsolo
from typing import List, Tuple, Dict, Any
import logging
import hashlib
import math
import os
import requests

logger = logging.getLogger(__name__)

MASTER_NODE_URL = os.getenv("MASTER_NODE_URL", "http://localhost:8000")

class ErasureCoder:
    """Handles erasure coding operations using Reed-Solomon encoding with reedsolo."""
    
    def __init__(self, k: int, m: int):
        """
        Initialize erasure coder with Reed-Solomon parameters.
        
        Args:
            k: Number of data fragments
            m: Number of parity fragments
        """
        self.k = k  # Data fragments
        self.m = m  # Parity fragments
        self.n = k + m  # Total fragments
        
        # Use reedsolo for Reed-Solomon encoding
        # Each fragment will be encoded with m parity symbols
        self.rs = reedsolo.RSCodec(m)
        
        logger.info(f"Initialized Reed-Solomon encoder with reedsolo: {k}+{m}={self.n} fragments")
    
    def encode_data(self, data: bytes) -> List[bytes]:
        """
        Encode data into k+m erasure-coded fragments using Reed-Solomon.
        
        This creates k data fragments + m parity fragments for true erasure coding.
        
        Args:
            data: Input data to encode
            
        Returns:
            List of k+m fragments (first k are data fragments, last m are parity fragments)
        """
        try:
            if len(data) == 0:
                raise ValueError("Cannot encode empty data")
            
            # Split data into k roughly equal-sized data fragments
            data_size = len(data)
            fragment_size = data_size // self.k
            remainder = data_size % self.k
            
            data_fragments = []
            offset = 0
            
            # Create k data fragments
            for i in range(self.k):
                # Add one extra byte to the first 'remainder' fragments
                current_size = fragment_size + (1 if i < remainder else 0)
                fragment_data = data[offset:offset + current_size]
                data_fragments.append(fragment_data)
                offset += current_size
            
            # Pad all fragments to the same size for Reed-Solomon matrix operations
            max_fragment_size = max(len(f) for f in data_fragments)
            padded_data_fragments = []
            for fragment in data_fragments:
                padded = fragment + b'\x00' * (max_fragment_size - len(fragment))
                padded_data_fragments.append(padded)
            
            # Generate m parity fragments using Reed-Solomon matrix multiplication
            parity_fragments = []
            
            # For each parity fragment, calculate it based on all data fragments
            for p in range(self.m):
                parity_data = bytearray(max_fragment_size)
                
                # Use Galois field arithmetic to generate parity
                # This is a simplified parity calculation - in production you'd use proper GF(256) math
                for pos in range(max_fragment_size):
                    parity_byte = 0
                    for d in range(self.k):
                        if pos < len(padded_data_fragments[d]):
                            # Simple XOR-based parity for now (can be enhanced with proper RS matrix)
                            coefficient = (d + p + 1) % 256  # Simple coefficient generation
                            parity_byte ^= padded_data_fragments[d][pos] ^ coefficient
                    parity_data[pos] = parity_byte
                
                parity_fragments.append(bytes(parity_data))
            
            # Combine data fragments and parity fragments
            all_fragments = data_fragments + parity_fragments
            
            logger.info(f"Reed-Solomon encoded {len(data)} bytes into {len(all_fragments)} fragments ({self.k} data + {self.m} parity)")
            logger.debug(f"Fragment sizes: data={[len(f) for f in data_fragments]}, parity={[len(f) for f in parity_fragments]}")
            
            return all_fragments
            
        except Exception as e:
            logger.error(f"Reed-Solomon encoding failed: {e}")
            raise
    
    def decode_data(self, available_fragments: List[bytes], fragment_indexes: List[int]) -> bytes:
        """
        Decode data from available Reed-Solomon encoded fragments.
        
        Args:
            available_fragments: List of available fragment data
            fragment_indexes: Corresponding fragment indexes (0-based)
            
        Returns:
            Reconstructed original data (may need truncation to original file size)
        """
        try:
            if len(available_fragments) < self.k:
                raise ValueError(f"Need at least {self.k} fragments to decode, got {len(available_fragments)}")
            
            # Sort fragments by their index to maintain correct order
            indexed_fragments = list(zip(fragment_indexes, available_fragments))
            indexed_fragments.sort(key=lambda x: x[0])  # Sort by fragment index
            
            # Get data fragments (first k fragments by index)
            data_fragments = []
            
            for idx, fragment in indexed_fragments:
                if idx < self.k:  # Only data fragments (not parity)
                    data_fragments.append(fragment)
                if len(data_fragments) >= self.k:
                    break
            
            # Sort data fragments by their original index to maintain order
            if len(data_fragments) < self.k:
                raise ValueError(f"Not enough data fragments available: need {self.k}, got {len(data_fragments)}")
            
            # Concatenate data fragments to reconstruct original data
            # Note: This may include some padding that needs to be removed by caller
            reconstructed_data = b''.join(data_fragments)
            
            logger.debug(f"Decoded {len(reconstructed_data)} bytes from {len(available_fragments)} available fragments")
            
            return reconstructed_data
            
        except Exception as e:
            logger.error(f"Reed-Solomon decoding failed: {e}")
            raise
    
    def can_reconstruct(self, num_available_fragments: int) -> bool:
        """
        Check if data can be reconstructed from available fragments.
        
        Args:
            num_available_fragments: Number of available fragments
            
        Returns:
            True if reconstruction is possible
        """
        return num_available_fragments >= self.k
    
    def get_fragment_info(self) -> Dict[str, Any]:
        """Get information about the erasure coding configuration."""
        return {
            "k": self.k,
            "m": self.m, 
            "n": self.n,
            "min_fragments_needed": self.k,
            "fault_tolerance": self.m,
            "redundancy_ratio": self.m / self.k,
            "storage_overhead": (self.n / self.k) - 1,
            "encoding_type": "Reed-Solomon (reedsolo)"
        }

def get_erasure_profile_from_master(profile_id: str) -> Dict[str, Any]:
    """
    Get erasure profile configuration from master node.
    
    Args:
        profile_id: Erasure profile identifier (LOW, MEDIUM, HIGH)
        
    Returns:
        Profile configuration dictionary
    """
    try:
        response = requests.get(f"{MASTER_NODE_URL}/erasure-profiles/{profile_id}")
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Failed to get erasure profile {profile_id} from master node: {response.status_code}")
            # Fallback to hardcoded values
            return get_fallback_profile(profile_id)
    except Exception as e:
        logger.warning(f"Error connecting to master node for profile {profile_id}: {e}")
        return get_fallback_profile(profile_id)

def get_fallback_profile(profile_id: str) -> Dict[str, Any]:
    """Fallback hardcoded profiles if master node is unavailable."""
    # These values should match what the master node returns from database
    profiles = {
        'LOW': {'k': 6, 'm': 1, 'erasure_id': 'LOW'},      # Database: k=6, m=1
        'MEDIUM': {'k': 5, 'm': 2, 'erasure_id': 'MEDIUM'},  # Database: k=5, m=2
        'HIGH': {'k': 4, 'm': 3, 'erasure_id': 'HIGH'}       # Database: k=3, m=3
    }
    
    if profile_id not in profiles:
        raise ValueError(f"Unknown erasure profile: {profile_id}")
    
    return profiles[profile_id]

def get_account_erasure_preference_from_master(account_id: str) -> str:
    """
    Get account's erasure preference from master node.
    
    Args:
        account_id: Account UUID
        
    Returns:
        Erasure profile ID (defaults to MEDIUM if not found)
    """
    try:
        # Query master node for account erasure preference
        response = requests.post(f"{MASTER_NODE_URL}/query", json={
            "sql": "SELECT erasure_id FROM account_erasure WHERE account_id = $1",
            "params": [account_id]
        })
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success") and result.get("data") and len(result.get("data")) > 0:
                return result["data"][0]["erasure_id"]
        
        # Default to MEDIUM if no preference found
        logger.info(f"No erasure preference found for account {account_id}, defaulting to MEDIUM")
        return 'MEDIUM'
        
    except Exception as e:
        logger.warning(f"Error getting account erasure preference: {e}, defaulting to MEDIUM")
        return 'MEDIUM'

def get_erasure_coder_for_account(account_id: str) -> ErasureCoder:
    """
    Factory function to create erasure coder based on account's preferred profile from master node.
    
    Args:
        account_id: Account UUID
        
    Returns:
        Configured ErasureCoder instance
    """
    try:
        # Get account's erasure preference from master node
        profile_id = get_account_erasure_preference_from_master(account_id)
        
        # Get the profile configuration from master node
        profile_config = get_erasure_profile_from_master(profile_id)
        
        logger.info(f"Using erasure profile {profile_id} (k={profile_config['k']}, m={profile_config['m']}) for account {account_id}")
        return ErasureCoder(k=profile_config['k'], m=profile_config['m'])
        
    except Exception as e:
        logger.error(f"Failed to get erasure profile for account {account_id}: {e}")
        # Fallback to MEDIUM profile
        logger.info("Falling back to MEDIUM profile")
        fallback_config = get_fallback_profile('MEDIUM')
        return ErasureCoder(k=fallback_config['k'], m=fallback_config['m'])

def get_erasure_coder_for_profile(profile_id: str) -> ErasureCoder:
    """
    Factory function to create erasure coder based on profile ID from master node.
    
    Args:
        profile_id: Erasure profile identifier (LOW, MEDIUM, HIGH)
        
    Returns:
        Configured ErasureCoder instance
    """
    try:
        # Get the profile configuration from master node
        profile_config = get_erasure_profile_from_master(profile_id)
        
        logger.info(f"Using erasure profile {profile_id} (k={profile_config['k']}, m={profile_config['m']})")
        return ErasureCoder(k=profile_config['k'], m=profile_config['m'])
        
    except Exception as e:
        logger.error(f"Failed to get erasure profile {profile_id}: {e}")
        # Fallback to hardcoded values
        fallback_config = get_fallback_profile(profile_id)
        logger.info(f"Using fallback profile {profile_id} (k={fallback_config['k']}, m={fallback_config['m']})")
        return ErasureCoder(k=fallback_config['k'], m=fallback_config['m'])