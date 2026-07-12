/**
 * persistentTypes tests — detectPersistentType, resolveListIdKey.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import {
  detectPersistentType,
  resolveListIdKey,
} from "../lib/persistentTypes.js";

describe("detectPersistentType", () => {
  it('returns "email-list" for !email list', () => {
    expect(detectPersistentType("!email list")).toBe("email-list");
  });

  it('returns "email-list" for !email search', () => {
    expect(detectPersistentType("!email search hello")).toBe("email-list");
  });

  it('returns "email-trash-list" for !email trash list', () => {
    expect(detectPersistentType("!email trash list")).toBe("email-trash-list");
  });

  it('returns "todo-list" for !todo list', () => {
    expect(detectPersistentType("!todo list")).toBe("todo-list");
  });

  it('returns "todo-list" for !todo search', () => {
    expect(detectPersistentType("!todo search milk")).toBe("todo-list");
  });

  it('returns "todo-list" for !todo tree', () => {
    expect(detectPersistentType("!todo tree")).toBe("todo-list");
  });

  it('returns "contacts-list" for !contact list', () => {
    expect(detectPersistentType("!contact list")).toBe("contacts-list");
  });

  it('returns "contacts-list" for !contacts list (plural alias)', () => {
    expect(detectPersistentType("!contacts list")).toBe("contacts-list");
  });

  it('returns "journal-list" for !journal list', () => {
    expect(detectPersistentType("!journal list")).toBe("journal-list");
  });

  it('returns "calendar-events" for !calendar list', () => {
    expect(detectPersistentType("!calendar list")).toBe("calendar-events");
  });

  it('returns "letter-list" for !letter list', () => {
    expect(detectPersistentType("!letter list")).toBe("letter-list");
  });

  it('returns "sieve-list" for !email sieve list', () => {
    expect(detectPersistentType("!email sieve list")).toBe("sieve-list");
  });

  it('returns "accounts" for !email account list', () => {
    expect(detectPersistentType("!email account list")).toBe("accounts");
  });

  it('returns "accounts" for !account list', () => {
    expect(detectPersistentType("!account list")).toBe("accounts");
  });

  it('returns "calendars" for !calendar account list', () => {
    expect(detectPersistentType("!calendar account list")).toBe("calendars");
  });

  it('returns null for non-list commands', () => {
    expect(detectPersistentType("!email send")).toBeNull();
    expect(detectPersistentType("!todo add Buy milk")).toBeNull();
    expect(detectPersistentType("hello world")).toBeNull();
  });
});

describe("resolveListIdKey", () => {
  it('returns "email-list" for email list tokens', () => {
    expect(resolveListIdKey(["email", "list"])).toBe("email-list");
  });

  it('returns "email-trash-list" for email trash list tokens', () => {
    expect(resolveListIdKey(["email", "trash", "list"])).toBe("email-trash-list");
  });

  it('returns "todo-list" for todo list tokens', () => {
    expect(resolveListIdKey(["todo", "list"])).toBe("todo-list");
  });

  it('returns "contacts-list" for contact list tokens', () => {
    expect(resolveListIdKey(["contact", "list"])).toBe("contacts-list");
  });

  it('returns null for unknown paths', () => {
    expect(resolveListIdKey(["unknown", "command"])).toBeNull();
  });
});
