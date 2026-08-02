import "dotenv/config"

import { createApp } from "./src/app.js"
import { connectDatabase } from "./src/db.js"

const port = Number(process.env.PORT || 5002)

if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error("PORT must be a valid port number.")
}
if (!process.env.JWT_SECRET || process.env.JWT_SECRET.length < 32) {
  throw new Error("JWT_SECRET must contain at least 32 characters.")
}

await connectDatabase(process.env.MONGODB_URI)

createApp().listen(port, "127.0.0.1", () => {
  console.log(`Account service listening on http://127.0.0.1:${port}`)
})
