#!/usr/bin/env python3
"""
VAPID Key Generator for Vitya AI Web Push Notifications.
Generates an uncompressed P-256 (prime256v1) elliptic curve keypair formatted as URL-safe base64.
"""
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def generate_vapid_keys():
    private_key = ec.generate_private_key(ec.SECP256R1())

    # Raw 32-byte scalar private key
    private_bytes = private_key.private_numbers().private_value.to_bytes(32, "big")
    private_b64 = base64.urlsafe_b64encode(private_bytes).decode().rstrip("=")

    # Uncompressed 65-byte point public key (0x04 || X || Y)
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    public_b64 = base64.urlsafe_b64encode(public_bytes).decode().rstrip("=")

    print("=================================================================")
    print("           Vitya AI - Web Push VAPID Keypair Generated            ")
    print("=================================================================")
    print(f"VAPID_PUBLIC_KEY={public_b64}")
    print(f"VAPID_PRIVATE_KEY={private_b64}")
    print("VAPID_SUBJECT=mailto:notifications@vitya-chat.onrender.com")
    print("=================================================================")
    print("Copy these values into your .env file or production environment.")
    print("Never commit the VAPID_PRIVATE_KEY into version control.")
    print("=================================================================")


if __name__ == "__main__":
    generate_vapid_keys()
