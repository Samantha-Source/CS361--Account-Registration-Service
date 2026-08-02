import crypto from "node:crypto"

const baseUrl = (process.env.ACCOUNT_SERVICE_URL || "http://127.0.0.1:5002").replace(/\/$/, "")

function safeBody(body) {
  if (!body || typeof body !== "object") return body
  return Object.fromEntries(
    Object.entries(body).map(([key, value]) => [
      key,
      key === "password" ? "<redacted>" : key === "session_token" ? "<received token>" : value,
    ])
  )
}

async function send(method, path, { body, token, expectedStatus }) {
  console.log(`\nREQUEST  ${method} ${path}`)
  if (body) console.log(JSON.stringify(safeBody(body), null, 2))
  if (token) console.log("Authorization: Bearer <stored token>")

  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const received = response.status === 204 ? null : await response.json()
  console.log(`RECEIVED ${response.status}`)
  console.log(received === null ? "<empty response body>" : JSON.stringify(safeBody(received), null, 2))

  if (response.status !== expectedStatus) {
    throw new Error(`Expected HTTP ${expectedStatus}, received HTTP ${response.status}.`)
  }
  return received
}

const unique = `${Date.now()}_${crypto.randomBytes(3).toString("hex")}`
const credentials = {
  username: `demo_${unique}`,
  email: `demo_${unique}@example.test`,
  password: "Example-Passphrase-42!",
}

try {
  await send("GET", "/health", { expectedStatus: 200 })
  const account = await send("POST", "/accounts", {
    body: credentials,
    expectedStatus: 201,
  })
  const session = await send("POST", "/sessions", {
    body: { email: credentials.email, password: credentials.password },
    expectedStatus: 200,
  })
  if (account.account_id !== session.account_id) {
    throw new Error("Registration and login returned different account IDs.")
  }

  await send("GET", "/accounts/me", {
    token: session.session_token,
    expectedStatus: 200,
  })
  await send("POST", "/sessions/logout", {
    token: session.session_token,
    expectedStatus: 204,
  })
  await send("GET", "/accounts/me", {
    token: session.session_token,
    expectedStatus: 401,
  })
  console.log("\nPASS: MS2 sent and received every response over HTTP.")
} catch (error) {
  console.error(`\nFAIL: ${error.message}`)
  process.exitCode = 1
}
