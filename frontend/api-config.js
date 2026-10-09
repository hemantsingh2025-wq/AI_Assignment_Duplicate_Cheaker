const defaultApiProtocol = window.location.protocol === "https:" ? "https:" : "http:";
const defaultApiHost = window.location.hostname || "127.0.0.1";

window.ASSIGNMENT_CHECKER_API_URL = (
    window.ASSIGNMENT_CHECKER_API_URL ||
    `${defaultApiProtocol}//${defaultApiHost}:8000`
).replace(/\/+$/, "");
