/**
 * Small compatibility layer for A Habit A Day's existing form data.
 *
 * This only maps fields and response names. The shared MS2 service still owns
 * account storage, password hashing, and sessions.
 */

import { AccountServiceClient } from "./account-service-client.js";

function stableEmailSuffix(email) {
  let hash = 2166136261;
  for (const character of String(email).trim().toLocaleLowerCase()) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

export function createAccountUsername(name, email) {
  const readableName = String(name)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^A-Za-z0-9_.-]+/g, "_")
    .replace(/^[_\.-]+|[_\.-]+$/g, "")
    .slice(0, 38);
  const base = readableName || "habit_user";
  return `${base}_${stableEmailSuffix(email)}`.slice(0, 50);
}

function toHabitUser(account) {
  return {
    _id: account.account_id,
    name: account.username,
    email: account.email,
  };
}

export class HabitAccountClient {
  constructor(serviceUrl) {
    this.accounts = new AccountServiceClient(serviceUrl);
  }

  async register({ name, email, password }) {
    const account = await this.accounts.register({
      username: createAccountUsername(name, email),
      email,
      password,
    });
    return { user: toHabitUser(account) };
  }

  async login({ email, password }) {
    const session = await this.accounts.login({ email, password });
    const account = await this.accounts.currentAccount(session.session_token);
    return {
      token: session.session_token,
      user: toHabitUser(account),
    };
  }

  logout(token) {
    return this.accounts.logout(token);
  }
}
