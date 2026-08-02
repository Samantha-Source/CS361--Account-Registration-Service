"""Check public account input before it reaches SQLite."""

import re
from dataclasses import dataclass


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,49}$")
LOCAL_PART_PATTERN = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$")
DOMAIN_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


@dataclass(frozen=True)
class ValidationIssue:
    """One client-safe validation problem."""

    code: str
    message: str
    field: str | None = None


def validate_registration(data: object) -> tuple[dict[str, str] | None, ValidationIssue | None]:
    """Check and normalize one registration body.

    :param data: decoded JSON value
    :return: normalized fields and no issue, or no fields and one issue
    """

    if not isinstance(data, dict):
        return None, ValidationIssue("INVALID_JSON", "The request body must be a JSON object.")

    for field in ("username", "email", "password"):
        if field not in data:
            return None, ValidationIssue(
                "MISSING_FIELD",
                f"The {field} field is required.",
                field,
            )
        if not isinstance(data[field], str):
            return None, ValidationIssue(
                "INVALID_FIELD_TYPE",
                f"The {field} field must be a string.",
                field,
            )

    username = data["username"].strip()
    email = data["email"].strip()
    password = data["password"]

    if not USERNAME_PATTERN.fullmatch(username):
        return None, ValidationIssue(
            "INVALID_USERNAME",
            "Username must be 3-50 characters and use only letters, numbers, periods, underscores, or hyphens.",
            "username",
        )
    if not is_valid_email(email):
        return None, ValidationIssue(
            "INVALID_EMAIL",
            "Email must be a valid address such as name@example.com.",
            "email",
        )

    password_issue = validate_password(password)
    if password_issue:
        return None, password_issue

    return {"username": username, "email": email, "password": password}, None


def validate_login(data: object) -> tuple[dict[str, str] | None, ValidationIssue | None]:
    """Check the username/email and password shape for one login request.

    :param data: decoded JSON value
    :return: login fields and no issue, or no fields and one issue
    """

    if not isinstance(data, dict):
        return None, ValidationIssue("INVALID_JSON", "The request body must be a JSON object.")

    if "password" not in data:
        return None, ValidationIssue(
            "MISSING_FIELD",
            "The password field is required.",
            "password",
        )
    if not isinstance(data["password"], str):
        return None, ValidationIssue(
            "INVALID_FIELD_TYPE",
            "The password field must be a string.",
            "password",
        )

    has_username = "username" in data
    has_email = "email" in data
    if has_username == has_email:
        return None, ValidationIssue(
            "INVALID_LOGIN_IDENTIFIER",
            "Provide either username or email, but not both.",
            "username_or_email",
        )

    identifier_field = "username" if has_username else "email"
    if not isinstance(data[identifier_field], str):
        return None, ValidationIssue(
            "INVALID_FIELD_TYPE",
            f"The {identifier_field} field must be a string.",
            identifier_field,
        )

    identifier = data[identifier_field].strip()
    if identifier_field == "username" and (not identifier or len(identifier) > 50):
        return None, ValidationIssue(
            "INVALID_USERNAME",
            "Username must be a non-empty string of at most 50 characters.",
            "username",
        )
    if identifier_field == "email" and not is_valid_email(identifier):
        return None, ValidationIssue(
            "INVALID_EMAIL",
            "Email must be a valid address such as name@example.com.",
            "email",
        )

    password = data["password"]
    if not password or len(password) > 128:
        return None, ValidationIssue(
            "INVALID_PASSWORD",
            "Password must be a non-empty string of at most 128 characters.",
            "password",
        )

    return {identifier_field: identifier, "password": password}, None


def is_valid_email(email: str) -> bool:
    """Check the practical ASCII email shape promised by the contract."""

    if len(email) > 254 or email.count("@") != 1 or any(character.isspace() for character in email):
        return False
    local_part, domain = email.rsplit("@", 1)
    if not local_part or len(local_part) > 64 or local_part.startswith(".") or local_part.endswith("."):
        return False
    if ".." in local_part or not LOCAL_PART_PATTERN.fullmatch(local_part):
        return False
    labels = domain.split(".")
    return len(labels) >= 2 and all(DOMAIN_LABEL_PATTERN.fullmatch(label) for label in labels)


def validate_password(password: str) -> ValidationIssue | None:
    """Check the registration password rules from the README."""

    requirements = (
        12 <= len(password) <= 128,
        any(character.islower() for character in password),
        any(character.isupper() for character in password),
        any(character.isdigit() for character in password),
        any(not character.isalnum() and not character.isspace() for character in password),
        not any(character.isspace() for character in password),
        not any(ord(character) < 32 or ord(character) == 127 for character in password),
    )
    if all(requirements):
        return None
    return ValidationIssue(
        "WEAK_PASSWORD",
        "Password must be 12-128 characters with an uppercase letter, lowercase letter, number, and symbol, with no whitespace.",
        "password",
    )


def normalized_key(value: str) -> str:
    """Make the case-insensitive key used for unique lookups."""

    return value.casefold()
