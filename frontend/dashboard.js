let user = null;
let token = localStorage.getItem("access_token");
const API_BASE = window.ASSIGNMENT_CHECKER_API_URL;

try {
    const storedUser = localStorage.getItem("user");
    user = storedUser ? JSON.parse(storedUser) : null;
} catch (error) {
    console.error("Invalid saved user data", error);
    user = null;
    localStorage.removeItem("user");
}

if (!user || !token) {
    window.location.href = "index.html";
}

const role = user?.role || "student";

async function requestApi(path, options = {}) {
    const headers = {
        Authorization: `Bearer ${token}`,
        ...(options.headers || {}),
    };

    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
        headers["Content-Type"] = "application/json";
    }

    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
    });
    const text = await response.text();
    let data = {};

    if (text) {
        try {
            data = JSON.parse(text);
        } catch {
            data = { detail: text };
        }
    }

    if (!response.ok) {
        throw new Error(data.detail || data.message || "Request failed.");
    }

    return data;
}

if (user) {
    const adminNameEl = document.getElementById("adminName");
    const adminRoleEl = document.querySelector(".admin-info small");

    if (adminNameEl) adminNameEl.innerText = user.name || "User";
    if (adminRoleEl) {
        adminRoleEl.innerText = role === "super_admin" ? "Super Admin" : role === "teacher" ? "Teacher" : "Student";
    }
}

function renderRoleLayout() {
    const teacherButton = document.querySelector('[data-section="teachers"]');
    const isTeacherAccess = ["teacher", "super_admin"].includes(role);

    if (teacherButton && !isTeacherAccess) {
        teacherButton.style.display = "none";
    }

    const welcomeHeader = document.querySelector("#home h2");
    const sectionText = document.querySelector("#home p");

    if (welcomeHeader) {
        welcomeHeader.innerText =
            role === "teacher" || role === "super_admin"
                ? "Welcome, Teacher/Admin 👋"
                : "Welcome, Student 👋";
    }

    if (sectionText) {
        sectionText.innerText =
            role === "teacher" || role === "super_admin"
                ? "Review uploaded assignments and check duplication across the class."
                : "Upload your assignments and check whether they are similar to each other.";
    }
}

function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    window.location.href = "index.html";
}

function showSection(sectionName) {

    const sections = document.querySelectorAll(".section");
    const navItems = document.querySelectorAll(".nav-item");

    sections.forEach(section => {
        section.classList.remove("active");
    });

    navItems.forEach(item => {
        item.classList.remove("active");
    });

    const targetSection = document.getElementById(sectionName);
    if (targetSection) {
        targetSection.classList.add("active");
    }

    const titles = {
        home: "Dashboard",
        upload: "Upload Assignments",
        results: "Similarity Results",
        classrooms: "Classrooms",
        teachers: "Teachers"
    };

    document.getElementById("pageTitle").innerText = titles[sectionName] || "Dashboard";

    const targetNav = document.querySelector(`[data-section="${sectionName}"]`);
    if (targetNav) {
        targetNav.classList.add("active");
    }
}

function showSelectedFiles() {

    const input = document.getElementById("assignmentFiles");
    const fileList = document.getElementById("fileList");

    fileList.innerHTML = "";

    const files = Array.from(input.files);

    if (files.length < 2) {

        fileList.innerHTML =
            "<p>Please select at least 2 assignments.</p>";

        return;
    }

    if (files.length > 100) {

        fileList.innerHTML =
            "<p>You can upload maximum 100 assignments.</p>";

        return;
    }

    files.forEach((file, index) => {

        const item = document.createElement("div");

        item.className = "file-item";

        item.innerText =
            `${index + 1}. ${file.name}`;

        fileList.appendChild(item);
    });
}

function renderComparisonResults(data) {
    const container = document.getElementById("resultsContainer");

    if (!data.comparisons || data.comparisons.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div>🔍</div>
                <h3>No duplicate patterns found</h3>
                <p>Assignments are below the similarity threshold.</p>
            </div>
        `;
        return;
    }

    const heading = document.createElement("p");
    heading.className = "similarity-method";
    heading.textContent = `Comparison method: ${data.method || "TF-IDF cosine similarity"}`;

    const cards = data.comparisons.map(item => {
        const card = document.createElement("article");
        card.className = "result-card";

        const title = document.createElement("h3");
        title.textContent =
            `${item.assignment_1_name || `Assignment ${item.assignment_1}`} vs ` +
            `${item.assignment_2_name || `Assignment ${item.assignment_2}`}`;

        const score = Number(item.similarity_percentage);
        const percentage = Number.isFinite(score)
            ? Math.min(100, Math.max(0, score))
            : 0;
        const scoreLabel = document.createElement("p");
        scoreLabel.innerHTML = "<strong>Cosine similarity:</strong> ";
        scoreLabel.append(`${percentage.toFixed(2)}%`);

        const progress = document.createElement("progress");
        progress.className = "similarity-progress";
        progress.max = 100;
        progress.value = percentage;
        progress.setAttribute("aria-label", `Cosine similarity ${percentage.toFixed(2)}%`);

        const status = document.createElement("p");
        status.innerHTML = "<strong>Status:</strong> ";
        status.append(item.status || "Unknown");

        card.append(title, scoreLabel, progress, status);
        return card;
    });

    container.replaceChildren(heading, ...cards);
}

async function compareAssignments(ids) {
    const response = await fetch(`${API_BASE}/assignments/check-similarity`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ assignment_ids: ids })
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.detail || "Similarity check failed.");
    }

    renderComparisonResults(data);
    return data;
}

async function loadMyAssignments() {
    const response = await fetch(`${API_BASE}/assignments/my-uploads`, {
        headers: {
            "Authorization": `Bearer ${token}`
        }
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.detail || "Unable to load assignments.");
    }

    return data.assignments || [];
}

async function loadAllAssignments() {
    const response = await fetch(`${API_BASE}/assignments/all`, {
        headers: {
            "Authorization": `Bearer ${token}`
        }
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.detail || "Unable to load assignments.");
    }

    return data.assignments || [];
}

async function reviewAssignment(assignmentId, decision) {
    const response = await fetch(`${API_BASE}/assignments/review`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ assignment_id: assignmentId, decision })
    });

    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.detail || "Review action failed.");
    }

    return data;
}

async function loadTeacherReviewList() {
    const reviewList = document.getElementById("teacherReviewList");
    if (!reviewList) return;

    try {
        const response = await fetch(`${API_BASE}/assignments/all`, {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Failed to load assignments.");
        }

        const items = data.assignments || [];
        if (!items.length) {
            reviewList.innerHTML = "<p>No assignments for review yet.</p>";
            return;
        }

        reviewList.innerHTML = items.map(item => `
            <div class="result-card">
                <p><strong>Student:</strong> ${item.uploader_name || "Unknown"}</p>
                <p><strong>Subject:</strong> ${item.subject || "General"}</p>
                <p><strong>File:</strong> ${item.filename}</p>
                <p><strong>Status:</strong> ${item.review_status || "pending"}</p>
                <div style="display:flex; gap:10px; margin-top:10px;">
                    <button onclick="reviewAssignment(${item.id}, 'pass').then(() => loadTeacherReviewList()).catch(err => alert(err.message))">Pass</button>
                    <button onclick="reviewAssignment(${item.id}, 'reject').then(() => loadTeacherReviewList()).catch(err => alert(err.message))">Reject</button>
                </div>
            </div>
        `).join("");

    } catch (error) {
        reviewList.innerHTML = `<p>${error.message}</p>`;
    }
}

function renderClassroomActions() {
    const actions = document.getElementById("classroomActions");
    const subjects = Array.from(document.getElementById("subjectSelect").options)
        .filter(option => option.value)
        .map(option => `<option value="${option.value}">${option.textContent}</option>`)
        .join("");

    if (role === "student") {
        actions.innerHTML = `
            <form class="classroom-form" onsubmit="joinClassroom(event)">
                <h3>Join a Classroom</h3>
                <label for="classroomJoinCode">Classroom join code</label>
                <input id="classroomJoinCode" type="text" required maxlength="32" autocomplete="off">
                <button type="submit">Join Classroom</button>
            </form>
        `;
        return;
    }

    actions.innerHTML = `
        <form class="classroom-form" onsubmit="createClassroom(event)">
            <h3>Create a Classroom</h3>
            <label for="classroomName">Classroom name</label>
            <input id="classroomName" type="text" required maxlength="100">
            <label for="classroomSubject">Subject</label>
            <select id="classroomSubject" required>
                <option value="">Select a subject</option>
                ${subjects}
            </select>
            <label for="classroomCreateCode">Join code (optional)</label>
            <input id="classroomCreateCode" type="text" maxlength="32" autocomplete="off">
            <button type="submit">Create Classroom</button>
        </form>
    `;
}

async function loadClassrooms() {
    const classroomList = document.getElementById("classroomList");
    const classroomSelect = document.getElementById("classroomSelect");
    const classroomField = document.getElementById("classroomUploadField");
    const subjectSelect = document.getElementById("subjectSelect");

    classroomField.hidden = role !== "student";
    subjectSelect.disabled = role === "student";
    renderClassroomActions();

    try {
        const data = await requestApi("/classrooms");
        const classrooms = data.classrooms || [];

        classroomSelect.replaceChildren(new Option("Select a classroom", ""));
        classroomList.replaceChildren();

        if (!classrooms.length) {
            classroomList.innerHTML = "<p>No classrooms yet.</p>";
        } else {
            classrooms.forEach(classroom => {
                const item = document.createElement("div");
                item.className = "classroom-item";

                const details = document.createElement("p");
                details.textContent = `${classroom.name} — ${classroom.subject}`;
                item.appendChild(details);

                if (classroom.join_code && role !== "student") {
                    const code = document.createElement("p");
                    code.textContent = `Join code: ${classroom.join_code}`;
                    item.appendChild(code);
                }

                classroomList.appendChild(item);
                classroomSelect.add(new Option(
                    `${classroom.name} — ${classroom.subject}`,
                    String(classroom.id),
                ));
            });
        }

        classroomSelect.onchange = () => {
            const classroom = classrooms.find(item =>
                String(item.id) === classroomSelect.value
            );
            if (classroom) {
                subjectSelect.value = classroom.subject;
            }
        };

        document.getElementById("classroomUploadHint").textContent =
            classrooms.length
                ? "Choose the classroom this assignment belongs to."
                : "Join a classroom before uploading assignments.";
    } catch (error) {
        classroomList.textContent = error.message;
        document.getElementById("classroomUploadHint").textContent =
            "Unable to load classrooms. Please try again.";
    }
}

async function createClassroom(event) {
    event.preventDefault();
    const message = document.getElementById("classroomMessage");

    try {
        const data = await requestApi("/classrooms", {
            method: "POST",
            body: JSON.stringify({
                name: document.getElementById("classroomName").value.trim(),
                subject: document.getElementById("classroomSubject").value,
                join_code: document.getElementById("classroomCreateCode").value.trim() || null,
            }),
        });
        message.textContent =
            `${data.message}. Share join code ${data.classroom.join_code} with students.`;
        event.target.reset();
        await loadClassrooms();
    } catch (error) {
        message.textContent = error.message;
    }
}

async function joinClassroom(event) {
    event.preventDefault();
    const message = document.getElementById("classroomMessage");

    try {
        const data = await requestApi("/classrooms/join", {
            method: "POST",
            body: JSON.stringify({
                join_code: document.getElementById("classroomJoinCode").value.trim(),
            }),
        });
        message.textContent = data.message;
        event.target.reset();
        await loadClassrooms();
    } catch (error) {
        message.textContent = error.message;
    }
}

async function checkSimilarity() {

    const input = document.getElementById("assignmentFiles");
    const subjectSelect = document.getElementById("subjectSelect");
    const message = document.getElementById("uploadMessage");

    if (input.files.length < 2) {
        message.innerText = "Please upload at least 2 assignments.";
        return;
    }

    if (input.files.length > 100) {
        message.innerText = "Maximum 100 assignments allowed.";
        return;
    }

    const subject = subjectSelect.value;
    const classroomId = document.getElementById("classroomSelect").value;

    if (!subject) {
        message.innerText = "Please select a subject.";
        return;
    }

    if (role === "student" && !classroomId) {
        message.innerText = "Join and select a classroom before uploading.";
        return;
    }

    const formData = new FormData();
    Array.from(input.files).forEach(file => formData.append("files", file));
    formData.append("subject", subject);
    if (classroomId) {
        formData.append("classroom_id", classroomId);
    }

    message.innerText = "Uploading assignments and checking for duplicates...";

    try {
        const uploadResponse = await fetch(`${API_BASE}/assignments/upload`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`
            },
            body: formData
        });

        const uploadData = await uploadResponse.json();

        if (!uploadResponse.ok) {
            throw new Error(uploadData.detail || "Upload failed.");
        }

        const uploadedIds = (uploadData.results || [])
            .filter(item => item.status === "success" && item.assignment_id)
            .map(item => item.assignment_id);

        if (uploadedIds.length < 2) {
            message.innerText = "At least 2 valid assignment files are required to compare.";
            return;
        }

        await compareAssignments(uploadedIds);
        showSection("results");
        message.innerText = "Similarity check completed.";

    } catch (error) {
        console.error(error);
        message.innerText = error.message || "Similarity check failed.";
    }
}

async function loadDashboardData() {
    const totalAssignmentsEl = document.getElementById("totalAssignments");
    const duplicateAssignmentsEl = document.getElementById("duplicateAssignments");
    const totalTeachersEl = document.getElementById("totalTeachers");

    try {
        const assignments =
            role === "teacher" || role === "super_admin"
                ? await loadAllAssignments()
                : await loadMyAssignments();

        totalAssignmentsEl.innerText = String(assignments.length || 0);

        const duplicates = assignments.filter(item => item.is_duplicate).length;
        duplicateAssignmentsEl.innerText = String(duplicates);

        if (role === "teacher" || role === "super_admin") {
            totalTeachersEl.innerText = "1";
        } else {
            totalTeachersEl.innerText = "0";
        }

    } catch (error) {
        console.error(error);
        totalAssignmentsEl.innerText = "0";
        duplicateAssignmentsEl.innerText = "0";
        totalTeachersEl.innerText = "0";
    }
}

function logout() {

    localStorage.removeItem("access_token");
    localStorage.removeItem("user");

    window.location.href = "index.html";
}

renderRoleLayout();
loadDashboardData();
loadClassrooms();
if (role === "teacher" || role === "super_admin") {
    loadTeacherReviewList();
}
showSection("home");