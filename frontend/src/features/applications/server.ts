import "server-only";
import { cache } from "react";
import { readBackend } from "@/lib/api/server";
import { applicationRepository, type Reader } from "./repository";

const read: Reader = (path, decode, query) => readBackend({ path, decode, query });
export const applications = applicationRepository(read);
// Request-scoped only. Never persist mutable Application/Job context across requests.
export const getApplicationContext = cache(applications.context);
