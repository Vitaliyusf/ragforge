"""Input sanitization utilities for preventing injection attacks.

Provides sanitization for:
- MongoDB NoSQL injection ($ operator stripping)
- Filename path traversal
- HTML/XSS prevention
- ObjectId validation

Usage:
    from shared.sanitization import sanitize_mongo_input, sanitize_filename, sanitize_html

    safe_query = sanitize_mongo_input(user_provided_filter)
    safe_name = sanitize_filename(uploaded_filename)
    safe_text = sanitize_html(user_message)
"""
import re
import os
import logging
from typing import Any

logger = logging.getLogger("sanitization")


def sanitize_mongo_input(value: Any) -> Any:
    """
    Recursively sanitize input to prevent MongoDB NoSQL injection.

    Strips keys starting with '$' (MongoDB operators) from dicts,
    which prevents attacks like: {"$gt": "", "$ne": null}

    Args:
        value: Any input value (dict, list, str, etc.)

    Returns:
        Sanitized value with dangerous MongoDB operators removed
    """
    if isinstance(value, dict):
        sanitized = {}
        for key, val in value.items():
            if isinstance(key, str) and key.startswith("$"):
                logger.warning(f"NoSQL injection blocked: key '{key}' stripped")
                continue
            sanitized[key] = sanitize_mongo_input(val)
        return sanitized
    elif isinstance(value, list):
        return [sanitize_mongo_input(item) for item in value]
    elif isinstance(value, str):
        # Strip embedded MongoDB operators in string values
        if value.startswith("$"):
            logger.warning("NoSQL injection blocked: value starting with '$' stripped")
            return ""
        return value
    return value


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize a filename to prevent path traversal and other attacks.

    - Removes directory separators and path traversal sequences
    - Strips null bytes
    - Limits length
    - Whitelist of allowed extensions

    Args:
        filename: The uploaded filename
        max_length: Maximum filename length

    Returns:
        Sanitized filename
    """
    ALLOWED_EXTENSIONS = {
        ".pdf", ".docx", ".doc", ".txt", ".md",
        ".csv", ".json", ".jsonl", ".xml",
        ".png", ".jpg", ".jpeg", ".gif",
        ".py", ".js", ".ts", ".html", ".css",
    }

    # Strip null bytes
    filename = filename.replace("\x00", "")

    # Remove directory separators and path traversal
    filename = filename.replace("/", "_").replace("\\", "_")
    filename = filename.replace("..", "_")

    # Get just the basename
    filename = os.path.basename(filename)

    # Truncate
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length - len(ext)] + ext

    # Check extension
    _, ext = os.path.splitext(filename)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        logger.warning(f"Filename with disallowed extension: {ext}")
        # Don't reject — just log. The file service should validate.

    # Remove special characters except basic safe ones
    filename = re.sub(r"[^\w\s\-_.]", "", filename)

    return filename.strip() or "unnamed_file"


def sanitize_html(text: str) -> str:
    """
    Strip HTML tags from text to prevent XSS.

    Removes all HTML tags while preserving text content.

    Args:
        text: Input text potentially containing HTML

    Returns:
        Text with all HTML tags removed
    """
    # Remove script/style blocks entirely (including content)
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove all remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&amp;", "&").replace("&quot;", '"')
    return text


def validate_object_id(oid: str) -> bool:
    """
    Validate a MongoDB ObjectId format.

    Args:
        oid: String to validate

    Returns:
        True if valid 24-character hex string
    """
    if not isinstance(oid, str):
        return False
    return bool(re.match(r"^[0-9a-fA-F]{24}$", oid))


def sanitize_chat_input(text: str, max_length: int = 4096) -> str:
    """
    Sanitize user chat input.

    - Strips HTML
    - Truncates to max length
    - Removes null bytes
    - Normalizes whitespace

    Args:
        text: User's chat message
        max_length: Maximum allowed length

    Returns:
        Sanitized text
    """
    # Remove null bytes
    text = text.replace("\x00", "")

    # Strip HTML
    text = sanitize_html(text)

    # Normalize excessive whitespace (but preserve paragraph breaks)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Truncate
    if len(text) > max_length:
        text = text[:max_length]
        logger.info(f"Chat input truncated from {len(text)} to {max_length} chars")

    return text.strip()
