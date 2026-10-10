const defaultApiProtocol = window.location.protocol === "https:" ? "https:" : "http:";
const defaultApiHost = window.location.hostname || "127.0.0.1";
const isLocalDevelopment = ["localhost", "127.0.0.1"].includes(defaultApiHost);

window.ASSIGNMENT_CHECKER_API_URL = (
    window.ASSIGNMENT_CHECKER_API_URL ||
    (isLocalDevelopment
        ? `${defaultApiProtocol}//${defaultApiHost}:8000`
        : "/api")
).replace(/\/+$/, "");
