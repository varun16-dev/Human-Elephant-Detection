from py_vapid import Vapid
import base64
from cryptography.hazmat.primitives import serialization

v = Vapid()
v.generate_keys()

# Get public key in base64url format for Web Push
pub_bytes = v.public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint
)
# For Web Push, encode the full 65 bytes (including 0x04 prefix)
public_key = base64.urlsafe_b64encode(pub_bytes).decode().rstrip('=')

# Get private key in PEM format (what pywebpush expects)
priv_bytes = v.private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)
private_key_pem = priv_bytes.decode()

print("VAPID Keys Generated:")
print("=" * 50)
print(f"VAPID_PUBLIC_KEY={public_key}")
print(f"VAPID_PRIVATE_KEY={private_key_pem}")
print("VAPID_CLAIMS_EMAIL=admin@example.com")
