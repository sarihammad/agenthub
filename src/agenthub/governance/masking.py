"""Data masking for PII and secrets with extended coverage."""

import re
from typing import Any, Dict, List, Union


# Patterns for sensitive data
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

# AWS keys
AWS_KEY_PATTERN = re.compile(r"(AWS|aws)(_)?([A-Z0-9]{20})")
AWS_SECRET_PATTERN = re.compile(r"(aws_secret_access_key|AWS_SECRET_ACCESS_KEY)\s*[:=]\s*([A-Za-z0-9/+=]{40})")

# API keys
API_KEY_PATTERN = re.compile(r"(sk|pk)-[A-Za-z0-9]{20,}")

# GCP keys
GCP_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z\-_]{35}")

# Azure keys
AZURE_KEY_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# Credit cards
CREDIT_CARD_PATTERN = re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b")

# IPv4 addresses
IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# IPv6 addresses (simplified)
IPV6_PATTERN = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b")

# Phone numbers (North American format and international)
PHONE_NA_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b")

# SSN
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Keys that should be masked
SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credit_card",
    "ssn",
    "social_security",
    "authorization",
    "bearer",
    "jwt",
}


def _mask_string(value: str) -> str:
    """Mask sensitive patterns in a string."""
    # Mask emails (keep domain)
    value = EMAIL_PATTERN.sub(lambda m: f"***@{m.group(0).split('@')[1]}", value)
    
    # Mask AWS keys
    value = AWS_KEY_PATTERN.sub(r"\1\2***", value)
    value = AWS_SECRET_PATTERN.sub(r"\1: ***", value)
    
    # Mask API keys (keep first 10 chars)
    value = API_KEY_PATTERN.sub(lambda m: f"{m.group(0)[:10]}***", value)
    
    # Mask GCP keys
    value = GCP_KEY_PATTERN.sub("AIza***", value)
    
    # Mask Azure keys (keep format)
    value = AZURE_KEY_PATTERN.sub("********-****-****-****-************", value)
    
    # Mask credit cards (keep last 4)
    value = CREDIT_CARD_PATTERN.sub(lambda m: f"****-****-****-{m.group(0)[-4:]}", value)
    
    # Mask IPv4 (keep first octet)
    value = IPV4_PATTERN.sub(lambda m: f"{m.group(0).split('.')[0]}.*.*.*", value)
    
    # Mask IPv6 (keep first segment)
    value = IPV6_PATTERN.sub(lambda m: f"{m.group(0).split(':')[0]}:****:****:****:****:****:****:****", value)
    
    # Mask phone numbers (keep area code)
    value = PHONE_NA_PATTERN.sub(r"(\1) ***-****", value)
    
    # Mask SSN
    value = SSN_PATTERN.sub("***-**-****", value)
    
    return value


def mask_sensitive_data(data: Any) -> Any:
    """Recursively mask sensitive data in dicts, lists, and strings.
    
    Args:
        data: Data to mask
        
    Returns:
        Masked data
    """
    if isinstance(data, dict):
        return {
            key: "***" if key.lower() in SENSITIVE_KEYS else mask_sensitive_data(value)
            for key, value in data.items()
        }
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    elif isinstance(data, str):
        return _mask_string(data)
    else:
        return data
