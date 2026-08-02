const USERNAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]{2,49}$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function issue(code, message, field) {
  return { code, message, ...(field ? { field } : {}) };
}

export function validateRegistration(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return { error: issue("INVALID_JSON", "The request body must be a JSON object.") };
  }

  for (const field of ["username", "email", "password"]) {
    if (!(field in body)) {
      return { error: issue("MISSING_FIELD", `The ${field} field is required.`, field) };
    }
    if (typeof body[field] !== "string") {
      return { error: issue("INVALID_FIELD_TYPE", `The ${field} field must be a string.`, field) };
    }
  }

  const username = body.username.trim();
  const email = body.email.trim();
  const password = body.password;
  const name = body.name === undefined ? username : body.name;

  if (typeof name !== "string" || !name.trim() || name.trim().length > 100) {
    return {
      error: issue("INVALID_NAME", "Name must be a non-empty string of at most 100 characters.", "name"),
    };
  }

  if (!USERNAME_PATTERN.test(username)) {
    return {
      error: issue(
        "INVALID_USERNAME",
        "Username must be 3-50 characters and use only letters, numbers, periods, underscores, or hyphens.",
        "username"
      ),
    };
  }
  if (email.length > 254 || !EMAIL_PATTERN.test(email)) {
    return {
      error: issue("INVALID_EMAIL", "Email must be a valid address such as name@example.com.", "email"),
    };
  }

  const strongPassword =
    password.length >= 12 &&
    password.length <= 128 &&
    /[a-z]/.test(password) &&
    /[A-Z]/.test(password) &&
    /[0-9]/.test(password) &&
    /[^A-Za-z0-9\s]/.test(password) &&
    !/\s/.test(password);
  if (!strongPassword) {
    return {
      error: issue(
        "WEAK_PASSWORD",
        "Password must be 12-128 characters with an uppercase letter, lowercase letter, number, and symbol, with no whitespace.",
        "password"
      ),
    };
  }

  return { value: { username, name: name.trim(), email: email.toLowerCase(), password } };
}

export function validateLogin(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return { error: issue("INVALID_JSON", "The request body must be a JSON object.") };
  }
  if (!("password" in body)) {
    return { error: issue("MISSING_FIELD", "The password field is required.", "password") };
  }
  if (typeof body.password !== "string") {
    return { error: issue("INVALID_FIELD_TYPE", "The password field must be a string.", "password") };
  }

  const hasUsername = "username" in body;
  const hasEmail = "email" in body;
  if (hasUsername === hasEmail) {
    return {
      error: issue(
        "INVALID_LOGIN_IDENTIFIER",
        "Provide either username or email, but not both.",
        "username_or_email"
      ),
    };
  }

  const field = hasUsername ? "username" : "email";
  if (typeof body[field] !== "string") {
    return { error: issue("INVALID_FIELD_TYPE", `The ${field} field must be a string.`, field) };
  }

  const identifier = body[field].trim();
  if (!identifier || identifier.length > 254 || !body.password || body.password.length > 128) {
    return { error: issue("INVALID_CREDENTIALS_INPUT", "Login fields are not valid.") };
  }
  if (field === "email" && !EMAIL_PATTERN.test(identifier)) {
    return { error: issue("INVALID_EMAIL", "Email must be a valid address such as name@example.com.", "email") };
  }

  return { value: { field, identifier, password: body.password } };
}
