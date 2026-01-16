#!/usr/bin/env python3
"""
Hardware License Generator for PrintQue
Usage: python generate_hardware_license.py
"""

import base64
import hmac
import hashlib
import sys
import os

# MUST match the secret in license_validator.py
HARDWARE_LICENSE_SECRET = "your-hardware-secret-key-change-this"

def generate_license(machine_id, tier, customer):
    """Generate a hardware license."""
    data = f"{machine_id}|{tier}|{customer}"
    signature = hmac.new(
        HARDWARE_LICENSE_SECRET.encode(),
        data.encode(),
        hashlib.sha256
    ).digest()
    
    full_data = data.encode() + b'||' + signature
    encoded = base64.b64encode(full_data).decode()
    
    return f"HW-{encoded[:4]}-{encoded[4:8]}-{encoded[8:]}"

def main():
    print("=== PrintQue Hardware License Generator ===\n")
    
    # Get customer info
    customer_name = input("Customer name/email: ").strip()
    if not customer_name:
        print("Error: Customer name required")
        return
    
    # Get machine ID
    print("\nThe customer needs to provide their Machine ID.")
    print("They can get it by running PrintQue and going to /system-info")
    machine_id = input("Customer's Machine ID: ").strip()
    if not machine_id:
        print("Error: Machine ID required")
        return
    
    # Select tier
    print("\nSelect license tier:")
    print("1. STANDARD (10 printers)")
    print("2. PREMIUM (20 printers)")
    print("3. PROFESSIONAL (50 printers)")
    print("4. ENTERPRISE (Unlimited)")
    
    tier_choice = input("Choice (1-4): ").strip()
    tiers = {
        '1': 'STANDARD',
        '2': 'PREMIUM',
        '3': 'PROFESSIONAL',
        '4': 'ENTERPRISE'
    }
    
    tier = tiers.get(tier_choice)
    if not tier:
        print("Error: Invalid tier selection")
        return
    
    # Generate license
    license_key = generate_license(machine_id, tier, customer_name)
    
    print("\n" + "="*50)
    print("LICENSE GENERATED SUCCESSFULLY!")
    print("="*50)
    print(f"Customer: {customer_name}")
    print(f"Tier: {tier}")
    print(f"Machine ID: {machine_id}")
    print(f"\nLicense Key:\n{license_key}")
    print("\nInstructions for customer:")
    print("1. Open PrintQue")
    print("2. Go to Settings > License")
    print("3. Enter this license key")
    print("4. Click 'Update License'")
    print("5. The license is now permanently activated!")
    print("="*50)
    
    # Save to file option
    save = input("\nSave to file? (y/n): ").lower().strip()
    if save == 'y':
        filename = f"license_{customer_name.replace(' ', '_')}_{machine_id[:8]}.txt"
        with open(filename, 'w') as f:
            f.write(f"PrintQue Hardware License\n")
            f.write(f"========================\n")
            f.write(f"Customer: {customer_name}\n")
            f.write(f"Tier: {tier}\n")
            f.write(f"Machine ID: {machine_id}\n")
            f.write(f"License Key: {license_key}\n")
            f.write(f"\nThis license is permanently tied to the specified machine.\n")
        print(f"License saved to: {filename}")

if __name__ == "__main__":
    main()