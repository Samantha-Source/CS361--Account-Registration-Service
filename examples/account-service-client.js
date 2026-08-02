/**
 * connects a JavaScript Main Program to the MS2 REST API using JSON
 *
 * Vite apps can set VITE_ACCOUNT_SERVICE_URL
 * other apps can pass a baseUrl when they create the client
 */

const localServiceUrl = "http://127.0.0.1:5002"
const viteServiceUrl = import.meta.env?.VITE_ACCOUNT_SERVICE_URL

export class AccountServiceError extends Error {
  constructor(status, error) {
    super(error?.message ?? `Account service returned HTTP ${status}.`)
    this.name = "AccountServiceError"
    this.status = status
    this.code = error?.code ?? "UNEXPECTED_RESPONSE"
    this.field = error?.field
  }
}

export class AccountServiceClient {
  constructor(baseUrl = viteServiceUrl || localServiceUrl) {
    this.baseUrl = String(baseUrl).trim().replace(/\/+$/, "") || localServiceUrl
  }

  async request(path, options = {}) {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    })

    const data = response.status === 204 ? null : await response.json()
    if (!response.ok) {
      throw new AccountServiceError(response.status, data?.error)
    }
    return data
  }

  health() {
    return this.request("/health")
  }

  register({ username, name, email, password }) {
    return this.request("/accounts", {
      method: "POST",
      body: JSON.stringify({ username, ...(name ? { name } : {}), email, password }),
    })
  }

  login({ username, email, password }) {
    const identifier = email === undefined ? { username } : { email }
    return this.request("/sessions", {
      method: "POST",
      body: JSON.stringify({ ...identifier, password }),
    })
  }

  currentAccount(sessionToken) {
    return this.request("/accounts/me", {
      headers: { Authorization: `Bearer ${sessionToken}` },
    })
  }

  async logout(sessionToken) {
    await this.request("/sessions/logout", {
      method: "POST",
      headers: { Authorization: `Bearer ${sessionToken}` },
    })
  }
}
