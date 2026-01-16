"""Cryptographic utilities for MeowTV (Castle) API."""

import base64
import os

from Crypto.Cipher import AES


def _derive_key(api_key_b64: str) -> bytes:
    """Derive AES key from API key."""
    api_key_bytes = base64.b64decode(api_key_b64)
    # Default CASTLE_SUFFIX for MeowTV decryption
    key_suffix = os.environ.get("CASTLE_SUFFIX", "T!BgJB").encode("ascii")
    
    key_material = api_key_bytes + key_suffix
    
    if len(key_material) < 16:
        # Pad with zeros
        key_material = key_material + bytes(16 - len(key_material))
    elif len(key_material) > 16:
        # Truncate to 16 bytes
        key_material = key_material[:16]
    
    return key_material


def decrypt_data(encrypted_b64: str, api_key_b64: str) -> str | None:
    """Decrypt AES-128-CBC encrypted data from the Castle API."""
    try:
        aes_key = _derive_key(api_key_b64)
        iv = aes_key  # IV is same as key per Kotlin implementation
        
        encrypted_data = base64.b64decode(encrypted_b64)
        
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(encrypted_data)
        
        # Remove PKCS7 padding
        padding_len = decrypted[-1]
        decrypted = decrypted[:-padding_len]
        
        return decrypted.decode("utf-8")
    except Exception as e:
        print(f"[Crypto] Decryption failed: {e}")
        return None
