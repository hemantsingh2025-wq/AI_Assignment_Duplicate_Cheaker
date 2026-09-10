async function login() {

    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const message = document.getElementById("message");

    if (!email || !password) {
        message.innerText = "Please enter email and password.";
        return;
    }

    if (email.includes("@gmail.com") || email.includes("@yahoo.com") || email.includes("@outlook.com") || email.includes("@hotmail.com")) {
        message.innerText = "Students must login with their college email only.";
        return;
    }

    message.innerText = "Logging in...";

    try {

        const response = await fetch("http://127.0.0.1:8000/login", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                email: email,
                password: password
            })
        });

        const data = await response.json();

        if (!response.ok) {
            message.innerText = data.detail || "Invalid email or password.";
            return;
        }

        localStorage.setItem("access_token", data.access_token);
        localStorage.setItem("user", JSON.stringify(data.user));

        message.innerText = "Login successful!";

        setTimeout(() => {
            window.location.href = "dashboard.html";
        }, 500);

    } catch (error) {

        console.error(error);
        message.innerText = "Unable to connect to the server. Please try again.";

    }
}