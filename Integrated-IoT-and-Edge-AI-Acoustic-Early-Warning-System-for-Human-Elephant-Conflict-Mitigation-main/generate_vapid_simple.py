"""
Simple VAPID Key Generator for Web Push
Generates properly formatted VAPID keys for web push notifications
"""
import base64
import json
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Generate a new ECDSA P-256 key pair
private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
public_key = private_key.public_key()

# Get public key in uncompressed format (65 bytes: 0x04 + x + y)
pub_bytes = public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint
)

print(f"Public key bytes length: {len(pub_bytes)}")
print(f"First byte (should be 0x04): {hex(pub_bytes[0])}")

# For Web Push, we need to encode the full 65 bytes (including 0x04 prefix)
# in base64url format without removing the prefix
public_key_base64 = base64.urlsafe_b64encode(pub_bytes).decode().rstrip('=')

print(f"VAPID public key length: {len(public_key_base64)}")

# Verify decoding
padding = '=' * ((4 - len(public_key_base64) % 4) % 4)
base64_str = (public_key_base64 + padding).replace('-', '+').replace('_', '/')
decoded = base64.b64decode(base64_str)
print(f"Decoded length: {len(decoded)} (should be 65)")

# Get private key in PEM format
priv_bytes = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)
private_key_pem = priv_bytes.decode()

print("VAPID Keys Generated:")
print("=" * 50)
print(f"VAPID_PUBLIC_KEY={public_key_base64}")
print(f"VAPID_PRIVATE_KEY={private_key_pem}")
print("VAPID_CLAIMS_EMAIL=admin@example.com")

# Also print as JSON for easy copying
print("\nJSON format:")
print(json.dumps({
    "VAPID_PUBLIC_KEY": public_key_base64,
    "VAPID_PRIVATE_KEY": private_key_pem,
    "VAPID_CLAIMS_EMAIL": "admin@example.com"
}, indent=2))
