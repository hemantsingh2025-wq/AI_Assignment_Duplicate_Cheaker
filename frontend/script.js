const API_BASE = window.ASSIGNMENT_CHECKER_API_URL;

function setMessage(text, isError = false) {
    const message = document.getElementById("message");
    if (!message) return;

    message.innerText = text;
    message.style.color = isError ? "#d93025" : "#1f7a1f";
}

function isCollegeEmail(email) {
    if (!email || !email.includes("@")) return false;

    const domain = email.split("@")[1].toLowerCase();
    const personalDomains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"];

    if (personalDomains.includes(domain)) return false;
    if (!domain.includes(".")) return false;

    return true;
}

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });

    let payload = {};
    const text = await response.text();

    if (text) {
        try {
            payload = JSON.parse(text);
        } catch (error) {
            payload = { detail: text };
        }
    }

    if (!response.ok) {
        throw new Error(payload.detail || payload.message || "Request failed");
    }

    return payload;
}

function setAuthPanel(mode) {
    const panels = document.querySelectorAll(".auth-panel");
    const buttons = document.querySelectorAll(".toggle-btn");

    panels.forEach((panel) => {
        panel.classList.toggle("active", panel.id === `${mode}Panel`);
    });

    buttons.forEach((button) => {
        button.classList.toggle("active", button.dataset.mode === mode);
    });
}

async function login() {
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;

    if (!email || !password) {
        setMessage("Please enter your email and password.", true);
        return;
    }

    setMessage("Logging in...");

    try {
        const data = await apiRequest("/login", {
            method: "POST",
            body: JSON.stringify({ email, password }),
        });

        localStorage.setItem("access_token", data.access_token);
        localStorage.setItem("user", JSON.stringify(data.user));

        setMessage("Login successful!");
        setTimeout(() => {
            window.location.href = "dashboard.html";
        }, 500);
    } catch (error) {
        console.error(error);
        setMessage(error.message || "Unable to connect to the server. Please try again.", true);
    }
}

async function signup() {
    const name = document.getElementById("signupName").value.trim();
    const email = document.getElementById("signupEmail").value.trim();
    const password = document.getElementById("signupPassword").value;
    const role = document.getElementById("signupRole").value;
    const subject = document.getElementById("signupSubject").value;

    if (!name || !email || !password) {
        setMessage("Please complete all required signup fields.", true);
        return;
    }

    if (!isCollegeEmail(email)) {
        setMessage("Please use a valid college or university email address.", true);
        return;
    }

    if (password.length < 6 || password.length > 72) {
        setMessage("Password must be between 6 and 72 characters.", true);
        return;
    }

    if (role === "teacher" && !subject) {
        setMessage("Teachers must select a subject.", true);
        return;
    }

    setMessage("Sending verification code...");

    try {
        const data = await apiRequest("/signup", {
            method: "POST",
            body: JSON.stringify({
                name,
                email,
                password,
                role,
                subject: role === "teacher" ? subject : undefined,
            }),
        });

        document.getElementById("verifyEmail").value = email;
        setAuthPanel("verify");
        if (data.development_otp) {
            setMessage(`Development mode is active. Use OTP ${data.development_otp} to verify your account.`);
        } else {
            setMessage("Verification code sent to your email.");
        }
    } catch (error) {
        console.error(error);
        setMessage(error.message || "Unable to create your account right now.", true);
    }
}

async function verifySignup() {
    const email = document.getElementById("verifyEmail").value.trim();
    const otp = document.getElementById("otpCode").value.trim();

    if (!email || !otp) {
        setMessage("Please enter your email and OTP.", true);
        return;
    }

    try {
        const data = await apiRequest("/signup/verify", {
            method: "POST",
            body: JSON.stringify({ email, otp }),
        });

        setMessage(data.message || "Signup complete! You can now log in.");
        setAuthPanel("login");
        document.getElementById("email").value = email;
        document.getElementById("password").value = "";
        document.getElementById("signupName").value = "";
        document.getElementById("signupEmail").value = "";
        document.getElementById("signupPassword").value = "";
        document.getElementById("otpCode").value = "";
    } catch (error) {
        console.error(error);
        setMessage(error.message || "OTP verification failed.", true);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".toggle-btn").forEach((button) => {
        button.addEventListener("click", () => {
            setAuthPanel(button.dataset.mode);
            setMessage("");
        });
    });

    document.getElementById("otpCode")?.addEventListener("input", (event) => {
        event.target.value = event.target.value.replace(/\D/g, "").slice(0, 6);
    });
});