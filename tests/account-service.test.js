import assert from "node:assert/strict";
import crypto from "node:crypto";
import { after, before, beforeEach, test } from "node:test";

import bcrypt from "bcryptjs";
import { MongoMemoryServer } from "mongodb-memory-server";
import request from "supertest";

import { createApp } from "../src/app.js";
import { connectDatabase, disconnectDatabase } from "../src/db.js";
import User from "../src/models/User.js";

let database;
let app;

const credentials = {
  username: "demo_user",
  email: "demo@example.test",
  password: "Example-Passphrase-42!",
};

before(async () => {
  process.env.JWT_SECRET = crypto.randomBytes(32).toString("hex");
  process.env.JWT_EXPIRES_IN = "1h";
  database = await MongoMemoryServer.create();
  await connectDatabase(database.getUri("account_service_test"));
  app = createApp();
  await User.syncIndexes();
});

beforeEach(async () => {
  await User.deleteMany({});
});

after(async () => {
  await disconnectDatabase();
  await database.stop();
});

async function register(values = credentials) {
  return request(app).post("/accounts").send(values);
}

async function login(values = { username: credentials.username, password: credentials.password }) {
  return request(app).post("/sessions").send(values);
}

test("health returns the service status", async () => {
  const response = await request(app).get("/health");

  assert.equal(response.status, 200);
  assert.deepEqual(response.body, { status: "ok" });
});

test("registration stores a bcrypt hash and returns public fields", async () => {
  const response = await register();

  assert.equal(response.status, 201);
  assert.equal(response.body.username, credentials.username);
  assert.equal(response.body.name, credentials.username);
  assert.equal(response.body.email, credentials.email);
  assert.match(response.body.account_id, /^[a-f0-9]{24}$/);
  assert.equal(response.body.password, undefined);

  const stored = await User.findById(response.body.account_id).select("+passwordHash");
  assert.notEqual(stored.passwordHash, credentials.password);
  assert.equal(await bcrypt.compare(credentials.password, stored.passwordHash), true);
});

test("registration rejects duplicate usernames and emails", async () => {
  assert.equal((await register()).status, 201);

  const duplicateUsername = await register({
    ...credentials,
    username: credentials.username.toUpperCase(),
    email: "other@example.test",
  });
  const duplicateEmail = await register({
    ...credentials,
    username: "other_user",
    email: credentials.email.toUpperCase(),
  });

  assert.equal(duplicateUsername.status, 409);
  assert.equal(duplicateUsername.body.error.code, "DUPLICATE_USERNAME");
  assert.equal(duplicateEmail.status, 409);
  assert.equal(duplicateEmail.body.error.code, "DUPLICATE_EMAIL");
});

test("registration returns structured validation errors", async () => {
  const missing = await request(app).post("/accounts").send({});
  const weak = await register({ ...credentials, password: "short" });

  assert.equal(missing.status, 400);
  assert.equal(missing.body.error.code, "MISSING_FIELD");
  assert.equal(weak.status, 400);
  assert.equal(weak.body.error.code, "WEAK_PASSWORD");
});

test("login works with either username or email", async () => {
  const account = (await register()).body;
  const usernameSession = await login();
  const emailSession = await login({
    email: credentials.email.toUpperCase(),
    password: credentials.password,
  });

  assert.equal(usernameSession.status, 200);
  assert.equal(usernameSession.body.account_id, account.account_id);
  assert.equal(usernameSession.body.authenticated, true);
  assert.equal(typeof usernameSession.body.session_token, "string");
  assert.equal(emailSession.status, 200);
  assert.equal(emailSession.body.account_id, account.account_id);
});

test("bad credentials return a generic error", async () => {
  await register();

  const response = await login({
    username: credentials.username,
    password: "Wrong-Passphrase-42!",
  });

  assert.equal(response.status, 401);
  assert.equal(response.body.authenticated, false);
  assert.equal(response.body.error.code, "INVALID_CREDENTIALS");
  assert.equal(response.body.session_token, undefined);
});

test("the bearer token reads the account and logout invalidates it", async () => {
  const account = (await register()).body;
  const session = (await login()).body;
  const authorization = { Authorization: `Bearer ${session.session_token}` };

  const beforeLogout = await request(app).get("/accounts/me").set(authorization);
  const logout = await request(app).post("/sessions/logout").set(authorization);
  const afterLogout = await request(app).get("/accounts/me").set(authorization);

  assert.equal(beforeLogout.status, 200);
  assert.deepEqual(beforeLogout.body, account);
  assert.equal(logout.status, 204);
  assert.equal(logout.text, "");
  assert.equal(afterLogout.status, 401);
  assert.equal(afterLogout.body.error.code, "UNAUTHORIZED");
});

test("an allowed browser origin receives CORS headers", async () => {
  const response = await request(app)
    .options("/accounts")
    .set("Origin", "http://localhost:5173")
    .set("Access-Control-Request-Method", "POST");

  assert.equal(response.status, 204);
  assert.equal(response.headers["access-control-allow-origin"], "http://localhost:5173");
});

test("unknown endpoints use the JSON error shape", async () => {
  const response = await request(app).get("/missing");

  assert.equal(response.status, 404);
  assert.equal(response.body.error.code, "NOT_FOUND");
});
