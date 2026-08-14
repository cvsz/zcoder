# ZCoder Key Management & Lifecycle

## Envelope Encryption Architecture
1. **Data Encryption Key (DEK)**: Generated per resource or backup snapshot.
2. **Key Encryption Key (KEK)**: Managed by external KMS / HSM.
3. **Rotation**: Re-wrapping DEKs without rewriting bulk data objects.
