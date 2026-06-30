/* eslint-disable */
/**
 * Generated `api` utility.
 *
 * THIS CODE IS AUTOMATICALLY GENERATED.
 *
 * To regenerate, run `npx convex dev`.
 * @module
 */

import type * as auth_acl from "../auth/acl.js";
import type * as auth_guards from "../auth/guards.js";
import type * as auth_internal from "../auth/internal.js";
import type * as auth_permissions from "../auth/permissions.js";
import type * as auth_smoke from "../auth/smoke.js";
import type * as auth_types from "../auth/types.js";
import type * as auth_wrappers from "../auth/wrappers.js";
import type * as chat from "../chat.js";
import type * as chatDebug from "../chatDebug.js";
import type * as chatLogging from "../chatLogging.js";
import type * as conversations from "../conversations.js";
import type * as domain from "../domain.js";
import type * as messageContent from "../messageContent.js";
import type * as messageQuote from "../messageQuote.js";
import type * as users from "../users.js";
import type * as widgets from "../widgets.js";

import type {
  ApiFromModules,
  FilterApi,
  FunctionReference,
} from "convex/server";

declare const fullApi: ApiFromModules<{
  "auth/acl": typeof auth_acl;
  "auth/guards": typeof auth_guards;
  "auth/internal": typeof auth_internal;
  "auth/permissions": typeof auth_permissions;
  "auth/smoke": typeof auth_smoke;
  "auth/types": typeof auth_types;
  "auth/wrappers": typeof auth_wrappers;
  chat: typeof chat;
  chatDebug: typeof chatDebug;
  chatLogging: typeof chatLogging;
  conversations: typeof conversations;
  domain: typeof domain;
  messageContent: typeof messageContent;
  messageQuote: typeof messageQuote;
  users: typeof users;
  widgets: typeof widgets;
}>;

/**
 * A utility for referencing Convex functions in your app's public API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = api.myModule.myFunction;
 * ```
 */
export declare const api: FilterApi<
  typeof fullApi,
  FunctionReference<any, "public">
>;

/**
 * A utility for referencing Convex functions in your app's internal API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = internal.myModule.myFunction;
 * ```
 */
export declare const internal: FilterApi<
  typeof fullApi,
  FunctionReference<any, "internal">
>;

export declare const components: {};
