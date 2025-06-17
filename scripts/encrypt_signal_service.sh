#!/bin/bash

set -e

if [ ! -f signal_service.pub ]; then
  echo "Generating new key pair..."
  age-keygen -o signal_service.key
  PUBLIC_KEY=$(grep "^# public key:" signal_service.key | awk '{print $4}')
  echo "$PUBLIC_KEY" > signal_service.pub
  echo "Public key saved to signal_service.pub"
  
  echo -e "\nWARNING: The private key will be displayed ONCE and then securely deleted."
  echo -e "Make sure to save it securely and add it to ROFL secrets before proceeding.\n"
  echo "Private key (save this securely and add to ROFL secrets):"
  cat signal_service.key
  
  rm -f signal_service.key
  echo "Private key deleted"
else
  echo "Using existing public key"
  PUBLIC_KEY=$(cat signal_service.pub)
fi

echo -e "\nPreparing signal service files for encryption..."
tar -czf signal_service.tar.gz src/signal_service/
echo "✓ Created archive of signal service files"

echo "Encrypting signal service files..."
age -e -r "$PUBLIC_KEY" signal_service.tar.gz > src/signal_service.tar.gz.age
echo "✓ Successfully encrypted signal service files"

rm signal_service.tar.gz
echo "✓ Cleaned up temporary files"

echo "Encryption complete: src/signal_service.tar.gz.age" 