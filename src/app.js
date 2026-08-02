import bcrypt from "bcryptjs";
import cors from "cors";
import express from "express";
import jwt from "jsonwebtoken";

import User from "./models/User.js";
import { validateLogin, validateRegistration } from "./validation.js";

function publicAccount(user) {
  return {
    account_id: user._id.toString(),
    name: user.name,
    username: user.username,
    email: user.email,
  };
}

function sendError(response, status, code, message, field) {
  return response.status(status).json({
    error: { code, message, ...(field ? { field } : {}) },
  });
}

function jwtSecret() {
  const secret = process.env.JWT_SECRET;
  if (!secret || secret.length < 32) {
    throw new Error("JWT_SECRET must contain at least 32 characters.");
  }
  return secret;
}

function createToken(user) {
  return jwt.sign(
    {
      userId: user._id.toString(),
      sessionVersion: user.sessionVersion,
    },
    jwtSecret(),
    { expiresIn: process.env.JWT_EXPIRES_IN || "1h" }
  );
}

function bearerToken(request) {
  const match = request.get("Authorization")?.match(/^Bearer\s+(\S+)$/i);
  return match?.[1];
}

async function requireAccount(request, response, next) {
  const token = bearerToken(request);
  if (!token) {
    response.set("WWW-Authenticate", "Bearer");
    return sendError(response, 401, "UNAUTHORIZED", "A valid bearer token is required.");
  }

  try {
    const payload = jwt.verify(token, jwtSecret());
    const account = await User.findById(payload.userId);
    if (!account || account.sessionVersion !== payload.sessionVersion) {
      throw new Error("inactive session");
    }
    request.account = account;
    request.sessionToken = token;
    request.sessionVersion = payload.sessionVersion;
    return next();
  } catch (_error) {
    response.set("WWW-Authenticate", "Bearer");
    return sendError(response, 401, "UNAUTHORIZED", "A valid bearer token is required.");
  }
}

export function createApp() {
  const app = express();
  const allowedOrigins = (process.env.ACCOUNT_ALLOWED_ORIGINS ||
    "http://localhost:5173,http://127.0.0.1:5173")
    .split(",")
    .map((origin) => origin.trim().replace(/\/$/, ""))
    .filter(Boolean);

  app.use(
    cors({
      origin(origin, callback) {
        if (!origin || allowedOrigins.includes(origin.replace(/\/$/, ""))) {
          return callback(null, true);
        }
        return callback(null, false);
      },
      methods: ["GET", "POST", "OPTIONS"],
      allowedHeaders: ["Authorization", "Content-Type"],
    })
  );
  app.use(express.json({ limit: "16kb" }));

  app.get("/health", (_request, response) => {
    response.json({ status: "ok" });
  });

  app.post("/accounts", async (request, response, next) => {
    try {
      const result = validateRegistration(request.body);
      if (result.error) {
        return response.status(400).json({ error: result.error });
      }

      const { username, name, email, password } = result.value;
      const usernameKey = username.toLowerCase();
      const duplicate = await User.findOne({ $or: [{ usernameKey }, { email }] });
      if (duplicate?.usernameKey === usernameKey) {
        return sendError(
          response,
          409,
          "DUPLICATE_USERNAME",
          "An account already uses that username.",
          "username"
        );
      }
      if (duplicate) {
        return sendError(
          response,
          409,
          "DUPLICATE_EMAIL",
          "An account already uses that email address.",
          "email"
        );
      }

      const passwordHash = await bcrypt.hash(password, 10);
      const account = await User.create({
        name,
        username,
        usernameKey,
        email,
        passwordHash,
      });
      return response.status(201).json(publicAccount(account));
    } catch (error) {
      if (error?.code === 11000) {
        const field = error.keyPattern?.usernameKey ? "username" : "email";
        const code = field === "username" ? "DUPLICATE_USERNAME" : "DUPLICATE_EMAIL";
        return sendError(
          response,
          409,
          code,
          `An account already uses that ${field}.`,
          field
        );
      }
      return next(error);
    }
  });

  app.post("/sessions", async (request, response, next) => {
    try {
      const result = validateLogin(request.body);
      if (result.error) {
        return response.status(400).json({ error: result.error });
      }

      const { field, identifier, password } = result.value;
      const query = field === "username"
        ? { usernameKey: identifier.toLowerCase() }
        : { email: identifier.toLowerCase() };
      const account = await User.findOne(query).select("+passwordHash");
      const matches = account ? await bcrypt.compare(password, account.passwordHash) : false;
      if (!matches) {
        return response.status(401).json({
          authenticated: false,
          error: {
            code: "INVALID_CREDENTIALS",
            message: "Invalid username, email, or password.",
          },
        });
      }

      return response.json({
        authenticated: true,
        account_id: account._id.toString(),
        session_token: createToken(account),
      });
    } catch (error) {
      return next(error);
    }
  });

  app.get("/accounts/me", requireAccount, (request, response) => {
    response.json(publicAccount(request.account));
  });

  app.post("/sessions/logout", requireAccount, async (request, response, next) => {
    try {
      const result = await User.updateOne(
        { _id: request.account._id, sessionVersion: request.sessionVersion },
        { $inc: { sessionVersion: 1 } }
      );
      if (result.modifiedCount !== 1) {
        return sendError(response, 401, "UNAUTHORIZED", "A valid bearer token is required.");
      }
      return response.status(204).send();
    } catch (error) {
      return next(error);
    }
  });

  app.use((request, response) => {
    sendError(response, 404, "NOT_FOUND", "The requested endpoint does not exist.");
  });

  app.use((error, _request, response, _next) => {
    if (error instanceof SyntaxError && "body" in error) {
      return sendError(response, 400, "INVALID_JSON", "The request body must be valid JSON.");
    }
    if (error?.type === "entity.too.large") {
      return sendError(response, 400, "REQUEST_TOO_LARGE", "The request body is too large.");
    }
    console.error(error);
    return sendError(response, 500, "INTERNAL_ERROR", "The service could not complete the request.");
  });

  return app;
}
