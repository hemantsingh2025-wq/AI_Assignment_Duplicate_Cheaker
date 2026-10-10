const defaultApiProtocol = window.location.protocol === "https:" ? "https:" : "http:";
const defaultApiHost = window.location.hostname || "127.0.0.1";
const deployedApiUrl = "https://backend-hemant-singh2.vercel.app/api";

window.ASSIGNMENT_CHECKER_API_URL = (
    window.ASSIGNMENT_CHECKER_API_URL ||
    (window.location.hostname.endsWith("vercel.app")
        ? deployedApiUrl
        : `${defaultApiProtocol}//${defaultApiHost}:8000`)
).replace(/\/+$/, "");
