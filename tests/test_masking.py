"""Test data masking with extended coverage."""

import pytest

from agenthub.governance.masking import mask_sensitive_data


def test_mask_emails() -> None:
    """Test email masking."""
    data = {"email": "user@example.com", "text": "Contact me at john.doe@company.org"}
    masked = mask_sensitive_data(data)
    
    assert masked["email"] == "***@example.com"
    assert "***@company.org" in masked["text"]
    assert "john.doe" not in masked["text"]


def test_mask_credit_cards() -> None:
    """Test credit card masking."""
    data = {
        "card1": "4532-1234-5678-9012",
        "card2": "4532 1234 5678 9012",
        "card3": "4532123456789012",
    }
    masked = mask_sensitive_data(data)
    
    assert masked["card1"] == "****-****-****-9012"
    assert masked["card2"] == "****-****-****-9012"
    assert masked["card3"] == "****-****-****-9012"


def test_mask_api_keys() -> None:
    """Test API key masking."""
    data = {
        "openai": "sk-abc123def456ghi789jkl012mno345pqr678",
        "stripe": "pk-test-1234567890",
    }
    masked = mask_sensitive_data(data)
    
    assert masked["openai"][:10] == "sk-abc123d"
    assert "***" in masked["openai"]
    assert "def456ghi789" not in masked["openai"]
    
    assert masked["stripe"][:10] == "pk-test-12"
    assert "***" in masked["stripe"]


def test_mask_aws_keys() -> None:
    """Test AWS key masking."""
    data = {
        "text": "AWS_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE",
        "secret": "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    }
    masked = mask_sensitive_data(data)
    
    assert "AKI***" in masked["text"]
    assert "AKIAIOSFODNN7EXAMPLE" not in masked["text"]
    
    assert "***" in masked["secret"]
    assert "wJalrXUtnFEMI" not in masked["secret"]


def test_mask_gcp_keys() -> None:
    """Test GCP key masking."""
    data = {"gcp_key": "AIzaSyD-abc123def456ghi789jkl012"}
    masked = mask_sensitive_data(data)
    
    assert masked["gcp_key"] == "AIza***"


def test_mask_azure_keys() -> None:
    """Test Azure subscription ID masking."""
    data = {"azure_id": "12345678-1234-5678-1234-567812345678"}
    masked = mask_sensitive_data(data)
    
    assert masked["azure_id"] == "********-****-****-****-************"


def test_mask_ipv4_addresses() -> None:
    """Test IPv4 masking."""
    data = {"ip": "192.168.1.100", "text": "Server at 10.0.0.5"}
    masked = mask_sensitive_data(data)
    
    assert masked["ip"] == "192.*.*.*"
    assert masked["text"] == "Server at 10.*.*.*"


def test_mask_ipv6_addresses() -> None:
    """Test IPv6 masking."""
    data = {"ipv6": "2001:0db8:85a3:0000:0000:8a2e:0370:7334"}
    masked = mask_sensitive_data(data)
    
    assert masked["ipv6"].startswith("2001:")
    assert "****" in masked["ipv6"]
    assert "85a3" not in masked["ipv6"]


def test_mask_phone_numbers() -> None:
    """Test phone number masking (North American)."""
    data = {
        "phone1": "+1 (555) 123-4567",
        "phone2": "555-123-4567",
        "phone3": "(555) 123-4567",
    }
    masked = mask_sensitive_data(data)
    
    assert "(555) ***-****" in masked["phone1"]
    assert "123-4567" not in masked["phone1"]


def test_mask_ssn() -> None:
    """Test SSN masking."""
    data = {"ssn": "123-45-6789"}
    masked = mask_sensitive_data(data)
    
    assert masked["ssn"] == "***-**-****"


def test_mask_sensitive_keys() -> None:
    """Test that sensitive keys are completely masked."""
    data = {
        "password": "super_secret_password",
        "secret": "my_secret_value",
        "token": "jwt_token_here",
        "api_key": "sk-1234567890",
        "private_key": "-----BEGIN PRIVATE KEY-----",
        "normal_field": "this_should_not_be_masked",
    }
    masked = mask_sensitive_data(data)
    
    assert masked["password"] == "***"
    assert masked["secret"] == "***"
    assert masked["token"] == "***"
    assert masked["api_key"] == "***"
    assert masked["private_key"] == "***"
    assert masked["normal_field"] == "this_should_not_be_masked"


def test_mask_nested_structures() -> None:
    """Test masking in nested dictionaries and lists."""
    data = {
        "user": {
            "email": "user@example.com",
            "password": "secret123",
            "preferences": {
                "api_key": "sk-abc123",
            },
        },
        "ips": ["192.168.1.1", "10.0.0.1"],
    }
    masked = mask_sensitive_data(data)
    
    assert masked["user"]["email"] == "***@example.com"
    assert masked["user"]["password"] == "***"
    assert masked["user"]["preferences"]["api_key"] == "***"
    assert masked["ips"][0] == "192.*.*.*"
    assert masked["ips"][1] == "10.*.*.*"


def test_mask_edge_cases() -> None:
    """Test edge cases and invalid inputs."""
    # Empty string
    assert mask_sensitive_data("") == ""
    
    # None
    assert mask_sensitive_data(None) is None
    
    # Number
    assert mask_sensitive_data(12345) == 12345
    
    # Boolean
    assert mask_sensitive_data(True) is True
    
    # Empty dict
    assert mask_sensitive_data({}) == {}
    
    # Empty list
    assert mask_sensitive_data([]) == []


def test_mask_multiple_patterns_in_text() -> None:
    """Test masking multiple sensitive patterns in the same text."""
    text = (
        "Email: user@example.com, "
        "API Key: sk-abc123def456, "
        "Card: 4532-1234-5678-9012, "
        "IP: 192.168.1.1"
    )
    masked = mask_sensitive_data(text)
    
    assert "***@example.com" in masked
    assert "sk-abc123d***" in masked
    assert "****-****-****-9012" in masked
    assert "192.*.*.*" in masked
    
    # Verify originals are gone
    assert "user@example.com" not in masked
    assert "def456" not in masked
    assert "4532-1234-5678-9012" not in masked
    assert "192.168.1.1" not in masked

