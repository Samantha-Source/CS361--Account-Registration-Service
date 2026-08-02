import crypto from "node:crypto";

import { MongoMemoryServer } from "mongodb-memory-server";

process.env.JWT_SECRET ||= crypto.randomBytes(32).toString("hex");
process.env.PORT ||= "5002";

const database = await MongoMemoryServer.create();
process.env.MONGODB_URI = database.getUri("cs361_accounts");

console.log("Temporary demo database started.");
await import("./server.js");

async function stop() {
  await database.stop();
  process.exit(0);
}

process.on("SIGINT", stop);
process.on("SIGTERM", stop);
