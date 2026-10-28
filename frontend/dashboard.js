let user = null;
let token = localStorage.getItem("access_token");
const API_BASE = window.ASSIGNMENT_CHECKER_API_URL;
let onlineClassSocket = null;
let onlineClassStream = null;
let onlineClassHost = false;
const onlinePeerConnections = new Map();
const onlineParticipants = new Map();
const pendingIceCandidates = new Map();
let teacherAssignments = [];
let notificationsInitialized = false;
let knownNotificationIds = new Set();
let notificationToastTimer = null;

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
        adminRoleEl.innerText =
            role === "super_admin" ? "Super Admin" :
            role === "authority" ? "Authority" :
            role === "teacher" ? "Teacher" :
            "Student";
    }
}

function renderRoleLayout() {
    const teacherButton = document.querySelector('[data-section="teachers"]');
    const similarityButton = document.querySelector('[data-section="results"]');
    const submissionsButton = document.querySelector('[data-section="my-submissions"]');
    const isTeacherAccess = ["teacher", "authority", "super_admin"].includes(role);

    if (teacherButton && !isTeacherAccess) {
        teacherButton.style.display = "none";
    }
    if (teacherButton && isTeacherAccess) {
        teacherButton.textContent = "📚 Class Assignments";
    }
    if (similarityButton && role === "student") {
        similarityButton.style.display = "none";
    }
    if (submissionsButton && role !== "student") {
        submissionsButton.style.display = "none";
    }

    const submissionsSection = document.getElementById("my-submissions");
    const submissionsPreview = document.getElementById("studentSubmissionsPreview");
    if (submissionsSection && role !== "student") {
        submissionsSection.style.display = "none";
    }
    if (submissionsPreview && role !== "student") {
        submissionsPreview.style.display = "none";
    }

    const welcomeHeader = document.querySelector("#home h2");
    const sectionText = document.querySelector(".welcome-box p");
    const duplicateLabel = document.getElementById("assignmentStatusLabel");
    const totalTeachersCard = document.getElementById("totalTeachers")?.closest(".card");
    const similarityCard = document.querySelector(".card.danger");
    const notificationArea = document.getElementById("studentNotificationArea");
    if (notificationArea) {
        notificationArea.hidden = role !== "student";
    }

    if (welcomeHeader) {
        welcomeHeader.innerText =
            role === "teacher" || role === "authority" || role === "super_admin"
                ? "Welcome, Teacher/Admin 👋"
                : "Welcome, Student 👋";
    }

    if (sectionText) {
        sectionText.innerText =
            role === "student"
                ? "Upload your assignments and track whether your teacher has approved or rejected them."
                : role === "teacher" || role === "authority" || role === "super_admin"
                ? "Review uploaded assignments and check duplication across the class."
                : "Manage assignment reviews and check duplication across submissions.";
    }

    if (role === "student") {
        if (duplicateLabel) duplicateLabel.innerText = "Rejected Assignments";
        if (totalTeachersCard) totalTeachersCard.style.display = "none";
        if (similarityCard) similarityCard.style.display = "none";
        document.getElementById("uploadInstructions").innerText =
            "Upload 1 to 100 assignment files. You can check the teacher's review status after submission.";
        document.getElementById("uploadActionButton").innerText = "📤 Submit Assignment";
    }
}

function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    window.location.href = "index.html";
}

function showSection(sectionName) {
    if (role === "student" && sectionName === "results") {
        return;
    }

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
        "my-submissions": "My Assignments",
        classrooms: "Classrooms",
        teachers: "Class Assignments"
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

    const minimumFileCount = role === "student" ? 1 : 2;
    if (files.length < minimumFileCount) {

        fileList.innerHTML =
            `<p>Please select at least ${minimumFileCount} assignment${minimumFileCount === 1 ? "" : "s"}.</p>`;

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

function getSubmissionStatus(assignment) {
    if (assignment.teacher_decision === "reject") {
        return { label: "Rejected", className: "status-rejected" };
    }
    if (assignment.teacher_decision === "pass") {
        return { label: "Approved", className: "status-approved" };
    }
    return { label: "Pending review", className: "status-pending" };
}

function renderSubmissionList(containerId, assignments) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.replaceChildren();
    if (!assignments.length) {
        const emptyMessage = document.createElement("p");
        emptyMessage.textContent = "You have not uploaded any assignments yet.";
        container.appendChild(emptyMessage);
        return;
    }

    assignments.forEach(assignment => {
        const item = document.createElement("article");
        item.className = "submission-item";

        const details = document.createElement("div");
        const filename = document.createElement("h3");
        filename.textContent = assignment.filename || "Assignment";
        const subject = document.createElement("p");
        subject.textContent = `Subject: ${assignment.subject || "General"}`;
        details.append(filename, subject);

        const status = getSubmissionStatus(assignment);
        const statusLabel = document.createElement("span");
        statusLabel.className = `submission-status ${status.className}`;
        statusLabel.textContent = status.label;

        item.append(details, statusLabel);
        container.appendChild(item);
    });
}

async function loadMySubmissions() {
    const containers = ["mySubmissionList", "homeSubmissionList"]
        .map(id => document.getElementById(id))
        .filter(Boolean);

    containers.forEach(container => {
        container.textContent = "Loading your assignments...";
    });

    try {
        const data = await requestApi("/assignments/my-uploads");
        const assignments = data.assignments || [];
        renderSubmissionList("mySubmissionList", assignments);
        renderSubmissionList("homeSubmissionList", assignments);

        const rejectedCount = assignments.filter(item =>
            item.teacher_decision === "reject"
        ).length;
        const rejectedCountEl = document.getElementById("duplicateAssignments");
        if (rejectedCountEl) rejectedCountEl.textContent = String(rejectedCount);
    } catch (error) {
        containers.forEach(container => {
            container.textContent = `Unable to load assignment statuses: ${error.message}`;
        });
    }
}

function toggleNotificationPanel() {
    const panel = document.getElementById("notificationPanel");
    const toggle = document.getElementById("notificationToggle");
    panel.hidden = !panel.hidden;
    toggle.setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden) {
        void loadNotifications();
    }
}

function showNotificationToast(message) {
    const toast = document.getElementById("notificationToast");
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(notificationToastTimer);
    notificationToastTimer = window.setTimeout(() => {
        toast.hidden = true;
    }, 7000);
}

function renderNotifications(notifications) {
    const list = document.getElementById("notificationList");
    const badge = document.getElementById("notificationBadge");
    if (!list || !badge) return;

    list.replaceChildren();
    if (!notifications.length) {
        const empty = document.createElement("p");
        empty.className = "notification-empty";
        empty.textContent = "No assignment review notifications yet.";
        list.appendChild(empty);
        return;
    }

    notifications.forEach(notification => {
        const item = document.createElement("article");
        item.className = `notification-item${notification.is_read ? "" : " is-unread"}`;

        const message = document.createElement("p");
        message.textContent = notification.message;
        const actions = document.createElement("div");
        actions.className = "notification-item-actions";

        const date = document.createElement("time");
        const timestamp = new Date(notification.created_at);
        date.textContent = Number.isNaN(timestamp.getTime())
            ? ""
            : timestamp.toLocaleString();
        actions.appendChild(date);

        if (!notification.is_read) {
            const readButton = document.createElement("button");
            readButton.type = "button";
            readButton.textContent = "Mark as read";
            readButton.addEventListener("click", () => {
                void markNotificationRead(notification.id);
            });
            actions.appendChild(readButton);
        }

        item.append(message, actions);
        list.appendChild(item);
    });
}

async function loadNotifications() {
    if (role !== "student") return;
    try {
        const data = await requestApi("/notifications");
        const notifications = data.notifications || [];
        const badge = document.getElementById("notificationBadge");
        badge.textContent = String(data.unread_count || 0);
        badge.hidden = !data.unread_count;
        renderNotifications(notifications);

        const newNotifications = notifications.filter(notification =>
            !knownNotificationIds.has(notification.id)
        );
        if (notificationsInitialized && newNotifications.length) {
            const newest = newNotifications[0];
            showNotificationToast(newest.message);
            if ("Notification" in window && Notification.permission === "granted") {
                new Notification("Assignment review update", {
                    body: newest.message,
                });
            }
        }
        notifications.forEach(notification => {
            knownNotificationIds.add(notification.id);
        });
        notificationsInitialized = true;
    } catch (error) {
        const list = document.getElementById("notificationList");
        if (list) {
            list.textContent = `Unable to load notifications: ${error.message}`;
        }
    }
}

async function markNotificationRead(notificationId) {
    try {
        await requestApi(`/notifications/${notificationId}/read`, {
            method: "POST",
        });
        await loadNotifications();
    } catch (error) {
        showNotificationToast(`Unable to update notification: ${error.message}`);
    }
}

async function enableBrowserNotifications() {
    if (!("Notification" in window)) {
        showNotificationToast("Browser notifications are not supported here. In-app notifications will still work.");
        return;
    }
    const permission = await Notification.requestPermission();
    showNotificationToast(permission === "granted"
        ? "Browser alerts enabled."
        : "Browser alerts were not enabled. In-app notifications will still work.");
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

        teacherAssignments = data.assignments || [];
        populateTeacherClassFilter(teacherAssignments);
        renderTeacherAssignments();

    } catch (error) {
        reviewList.textContent = error.message;
    }
}

function populateTeacherClassFilter(assignments) {
    const filter = document.getElementById("assignmentClassFilter");
    if (!filter) return;

    const selected = filter.value || "all";
    const classrooms = new Map();
    assignments.forEach(assignment => {
        const key = assignment.classroom_id == null
            ? "unassigned"
            : String(assignment.classroom_id);
        classrooms.set(key, assignment.class_section || assignment.classroom_name || "No classroom assigned");
    });

    filter.replaceChildren(new Option("All classrooms", "all"));
    [...classrooms.entries()]
        .sort((left, right) => left[1].localeCompare(right[1]))
        .forEach(([id, name]) => filter.add(new Option(name, id)));

    if ([...filter.options].some(option => option.value === selected)) {
        filter.value = selected;
    }
}

function filterTeacherAssignments() {
    renderTeacherAssignments();
}

function renderTeacherAssignments() {
    const reviewList = document.getElementById("teacherReviewList");
    if (!reviewList) return;

    const selectedClassroom = document.getElementById("assignmentClassFilter")?.value || "all";
    const assignments = teacherAssignments.filter(assignment => {
        if (selectedClassroom === "all") return true;
        const classroomId = assignment.classroom_id == null
            ? "unassigned"
            : String(assignment.classroom_id);
        return classroomId === selectedClassroom;
    });

    reviewList.replaceChildren();
    if (!assignments.length) {
        const message = document.createElement("p");
        message.textContent = teacherAssignments.length
            ? "No assignments are stored for this classroom yet."
            : "No assignments have been submitted to your classrooms yet.";
        reviewList.appendChild(message);
        return;
    }

    const groups = new Map();
    assignments.forEach(assignment => {
        const classroomId = assignment.classroom_id == null
            ? "unassigned"
            : String(assignment.classroom_id);
        const classSection = assignment.class_section ||
            assignment.classroom_name ||
            "No classroom assigned";
        if (!groups.has(classroomId)) {
            groups.set(classroomId, { name: classSection, assignments: [] });
        }
        groups.get(classroomId).assignments.push(assignment);
    });

    groups.forEach(group => {
        const section = document.createElement("section");
        section.className = "assignment-class-group";

        const heading = document.createElement("h3");
        heading.textContent = `${group.name} (${group.assignments.length})`;
        section.appendChild(heading);

        group.assignments.forEach(assignment => {
            const card = document.createElement("article");
            card.className = "result-card";

            const details = [
                ["Student", assignment.uploader_name || "Unknown"],
                ["Subject", assignment.subject || "General"],
                ["File", assignment.filename || "Assignment"],
                ["Review status", assignment.teacher_decision === "pass"
                    ? "Approved"
                    : assignment.teacher_decision === "reject"
                        ? "Rejected"
                        : "Pending review"],
            ];
            details.forEach(([label, value]) => {
                const paragraph = document.createElement("p");
                const strong = document.createElement("strong");
                strong.textContent = `${label}: `;
                paragraph.append(strong, value);
                card.appendChild(paragraph);
            });

            const actions = document.createElement("div");
            actions.className = "assignment-review-actions";
            [["pass", "Approve"], ["reject", "Reject"]].forEach(([decision, label]) => {
                const button = document.createElement("button");
                button.type = "button";
                button.textContent = label;
                button.addEventListener("click", async () => {
                    try {
                        await reviewAssignment(assignment.id, decision);
                        await loadTeacherReviewList();
                    } catch (error) {
                        alert(error.message);
                    }
                });
                actions.appendChild(button);
            });
            card.appendChild(actions);
            section.appendChild(card);
        });

        reviewList.appendChild(section);
    });
}

function renderClassroomActions() {
    const actions = document.getElementById("classroomActions");
    const intro = document.getElementById("classroomIntro");
    const subjects = Array.from(document.getElementById("subjectSelect").options)
        .filter(option => option.value)
        .map(option => `<option value="${option.value}">${option.textContent}</option>`)
        .join("");

    if (role === "student") {
        intro.textContent = "Join your teacher's classroom and attend their live online classes.";
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

    intro.textContent = "Create a classroom, share its join code, and start live online classes.";
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
    subjectSelect.disabled = false;
    renderClassroomActions();

    try {
        const data = await requestApi("/classrooms");
        const classrooms = data.classrooms || [];
        classroomSelect.required = role === "student" && classrooms.length > 0;
        subjectSelect.disabled = role === "student" && classrooms.length > 0;
        if (role === "student" && classrooms.length === 0) {
            subjectSelect.value = user.subject || "";
        }

        classroomSelect.replaceChildren(new Option("Select a classroom", ""));
        classroomList.replaceChildren();

        if (!classrooms.length) {
            classroomList.innerHTML = "<p>No classrooms yet.</p>";
        } else {
            classrooms.forEach(classroom => {
                const item = document.createElement("div");
                item.className = "classroom-item";

                const row = document.createElement("div");
                row.className = "classroom-item-row";
                const details = document.createElement("p");
                details.textContent = `${classroom.name} — ${classroom.subject}`;
                row.appendChild(details);

                const onlineStatus = document.createElement("span");
                onlineStatus.className = `classroom-online-status ${classroom.is_online ? "is-live" : "is-offline"}`;
                onlineStatus.textContent = classroom.is_online ? "Online class live" : "Offline";
                row.appendChild(onlineStatus);
                item.appendChild(row);

                if (classroom.join_code && role !== "student") {
                    const code = document.createElement("p");
                    code.textContent = `Join code: ${classroom.join_code}`;
                    item.appendChild(code);
                }

                const isClassTeacher =
                    role === "teacher" && classroom.teacher_id === user.id;
                if (isClassTeacher || role === "student") {
                    const classButton = document.createElement("button");
                    classButton.type = "button";
                    if (isClassTeacher) {
                        classButton.textContent = classroom.is_online
                            ? "Class is live"
                            : "Start online class";
                        classButton.disabled = classroom.is_online;
                        classButton.addEventListener("click", () =>
                            startOnlineClass(classroom.id, classroom.name)
                        );
                    } else {
                        classButton.textContent = classroom.is_online
                            ? "Join online class"
                            : "Class is offline";
                        classButton.disabled = !classroom.is_online;
                        classButton.addEventListener("click", () =>
                            joinOnlineClass(classroom.id, classroom.name)
                        );
                    }
                    item.appendChild(classButton);
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
                : "No classroom is available. Submit to your assigned subject without a classroom.";
        document.getElementById("classroomLiveHint").textContent =
            role === "student"
                ? "Live classes appear here when your teacher starts one. The list refreshes automatically."
                : "Start an online class from one of your classrooms.";
    } catch (error) {
        classroomList.textContent = error.message;
        document.getElementById("classroomUploadHint").textContent =
            "Unable to load classrooms. Please try again.";
    }
}

async function startOnlineClass(classroomId, classroomName) {
    await connectToOnlineClass(classroomId, classroomName, true);
}

async function joinOnlineClass(classroomId, classroomName) {
    await connectToOnlineClass(classroomId, classroomName, false);
}

async function connectToOnlineClass(classroomId, classroomName, isHost) {
    if (onlineClassSocket) {
        return;
    }

    const status = document.getElementById("onlineClassStatus");
    try {
        if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {
            throw new Error("This browser does not support live video classes.");
        }

        const config = await requestApi(`/classrooms/${classroomId}/online-config`);
        onlineClassStream = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: true,
        });
        onlineClassHost = isHost;

        const panel = document.getElementById("onlineClassPanel");
        panel.hidden = false;
        document.getElementById("onlineClassTitle").textContent =
            `${classroomName} — Live online class`;
        document.getElementById("leaveOnlineClassButton").textContent =
            isHost ? "End class" : "Leave class";
        const localVideo = document.getElementById("localClassVideo");
        localVideo.srcObject = onlineClassStream;
        document.getElementById("onlineVideoGrid").replaceChildren(
            localVideo.closest(".online-video-tile"),
        );
        status.textContent = "Connecting to online class...";

        const apiUrl = new URL(API_BASE, window.location.href);
        const wsProtocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
        const wsBase = `${wsProtocol}//${apiUrl.host}${apiUrl.pathname.replace(/\/+$/, "")}`;
        const socket = new WebSocket(
            `${wsBase}/classrooms/${classroomId}/online`,
            ["assignment-checker", `bearer.${token}`],
        );
        onlineClassSocket = socket;

        socket.addEventListener("message", event => {
            let message;
            try {
                message = JSON.parse(event.data);
            } catch (error) {
                console.error("Invalid online class signaling message", error);
                return;
            }
            void handleOnlineClassMessage(message, config.ice_servers || []);
        });
        socket.addEventListener("close", event => {
            const closeMessage = event.code === 4404
                ? "The teacher has not started this online class yet."
                : event.code === 4409
                    ? "This online class is already open in another teacher session."
                    : event.code === 4429
                        ? "This online class has reached its participant limit."
                        : event.code === 1000
                            ? ""
                            : "The online class connection was closed. Check that the backend is running and try again.";
            finishOnlineClass(closeMessage, false);
        });
        socket.addEventListener("error", () => {
            status.textContent = "Unable to connect. Check the backend connection and try again.";
        });
    } catch (error) {
        finishOnlineClass(error.message || "Unable to start the online class.", true);
    }
}

async function handleOnlineClassMessage(message, iceServers) {
    const status = document.getElementById("onlineClassStatus");
    if (message.type === "error") {
        status.textContent = message.message;
        return;
    }
    if (message.type === "room_state") {
        status.textContent = "Online class connected. Allow camera and microphone access to participate.";
        const participants = message.participants || [];
        participants.forEach(participant => {
            onlineParticipants.set(participant.id, participant);
            if (onlineClassHost) {
                void createOnlinePeer(participant.id, participant.name, iceServers);
            }
        });
        return;
    }
    if (message.type === "class_started") {
        status.textContent = "Your teacher has started the online class.";
        return;
    }
    if (message.type === "participant_joined") {
        const participant = message.participant;
        onlineParticipants.set(participant.id, participant);
        status.textContent = `${participant.name} joined the online class.`;
        if (onlineClassHost) {
            void createOnlinePeer(participant.id, participant.name, iceServers);
        }
        return;
    }
    if (message.type === "participant_left") {
        removeOnlinePeer(message.participant_id);
        status.textContent = "A participant left the online class.";
        return;
    }
    if (message.type === "class_ended") {
        finishOnlineClass("The teacher ended the online class.", true);
        return;
    }

    const participant = onlineParticipants.get(message.from);
    const connection = onlinePeerConnections.get(message.from) ||
        (participant && await createOnlinePeer(message.from, participant.name, iceServers));
    if (!connection) {
        return;
    }

    try {
        if (message.type === "offer") {
            await connection.setRemoteDescription(message.data);
            const candidates = pendingIceCandidates.get(message.from) || [];
            pendingIceCandidates.delete(message.from);
            for (const candidate of candidates) {
                await connection.addIceCandidate(candidate);
            }
            const answer = await connection.createAnswer();
            await connection.setLocalDescription(answer);
            sendOnlineSignal("answer", message.from, connection.localDescription);
        } else if (message.type === "answer") {
            await connection.setRemoteDescription(message.data);
            const candidates = pendingIceCandidates.get(message.from) || [];
            pendingIceCandidates.delete(message.from);
            for (const candidate of candidates) {
                await connection.addIceCandidate(candidate);
            }
        } else if (message.type === "ice_candidate" && message.data) {
            const candidate = new RTCIceCandidate(message.data);
            if (connection.remoteDescription) {
                await connection.addIceCandidate(candidate);
            } else {
                const candidates = pendingIceCandidates.get(message.from) || [];
                candidates.push(candidate);
                pendingIceCandidates.set(message.from, candidates);
            }
        }
    } catch (error) {
        console.error("Online class connection failed", error);
        status.textContent = `Could not connect to ${participant?.name || "a participant"}.`;
    }
}

async function createOnlinePeer(participantId, participantName, iceServers) {
    if (onlinePeerConnections.has(participantId)) {
        return onlinePeerConnections.get(participantId);
    }

    const connection = new RTCPeerConnection({ iceServers });
    onlinePeerConnections.set(participantId, connection);
    onlineParticipants.set(participantId, {
        id: participantId,
        name: participantName,
    });

    onlineClassStream?.getTracks().forEach(track => {
        connection.addTrack(track, onlineClassStream);
    });
    connection.addEventListener("icecandidate", event => {
        if (event.candidate) {
            sendOnlineSignal("ice_candidate", participantId, event.candidate.toJSON());
        }
    });
    connection.addEventListener("track", event => {
        renderRemoteClassVideo(participantId, participantName, event.streams[0]);
    });
    connection.addEventListener("connectionstatechange", () => {
        if (connection.connectionState === "failed") {
            document.getElementById("onlineClassStatus").textContent =
                `Connection to ${participantName} failed. Check your network or TURN configuration.`;
        }
    });

    if (onlineClassHost) {
        try {
            const offer = await connection.createOffer();
            await connection.setLocalDescription(offer);
            sendOnlineSignal("offer", participantId, connection.localDescription);
        } catch (error) {
            console.error("Unable to create online class offer", error);
            document.getElementById("onlineClassStatus").textContent =
                `Unable to connect to ${participantName}.`;
        }
    }
    return connection;
}

function sendOnlineSignal(type, participantId, data) {
    if (onlineClassSocket?.readyState === WebSocket.OPEN) {
        onlineClassSocket.send(JSON.stringify({
            type,
            to: participantId,
            data,
        }));
    }
}

function renderRemoteClassVideo(participantId, participantName, stream) {
    const grid = document.getElementById("onlineVideoGrid");
    let tile = grid.querySelector(`[data-participant-id="${CSS.escape(participantId)}"]`);
    if (!tile) {
        tile = document.createElement("article");
        tile.className = "online-video-tile";
        tile.dataset.participantId = participantId;

        const video = document.createElement("video");
        video.autoplay = true;
        video.playsInline = true;
        video.srcObject = stream;
        const name = document.createElement("p");
        name.textContent = participantName;
        tile.append(video, name);
        grid.appendChild(tile);
    }
}

function removeOnlinePeer(participantId) {
    onlinePeerConnections.get(participantId)?.close();
    onlinePeerConnections.delete(participantId);
    onlineParticipants.delete(participantId);
    pendingIceCandidates.delete(participantId);
    document.querySelector(`[data-participant-id="${CSS.escape(participantId)}"]`)?.remove();
}

function toggleOnlineMicrophone() {
    if (!onlineClassStream) return;
    const audioTrack = onlineClassStream.getAudioTracks()[0];
    if (!audioTrack) return;
    audioTrack.enabled = !audioTrack.enabled;
    document.getElementById("toggleMicrophone").textContent =
        audioTrack.enabled ? "Mute microphone" : "Unmute microphone";
}

function toggleOnlineCamera() {
    if (!onlineClassStream) return;
    const videoTrack = onlineClassStream.getVideoTracks()[0];
    if (!videoTrack) return;
    videoTrack.enabled = !videoTrack.enabled;
    document.getElementById("toggleCamera").textContent =
        videoTrack.enabled ? "Turn camera off" : "Turn camera on";
}

function leaveOnlineClass() {
    finishOnlineClass(
        onlineClassHost ? "You ended the online class." : "You left the online class.",
        true,
    );
}

function finishOnlineClass(message, closeSocket) {
    const socket = onlineClassSocket;
    onlineClassSocket = null;
    if (closeSocket && socket && socket.readyState < WebSocket.CLOSING) {
        socket.close();
    }
    onlinePeerConnections.forEach(connection => connection.close());
    onlinePeerConnections.clear();
    onlineParticipants.clear();
    pendingIceCandidates.clear();
    onlineClassStream?.getTracks().forEach(track => track.stop());
    onlineClassStream = null;
    onlineClassHost = false;

    const panel = document.getElementById("onlineClassPanel");
    if (panel) panel.hidden = true;
    const localVideo = document.getElementById("localClassVideo");
    if (localVideo) localVideo.srcObject = null;
    const videoGrid = document.getElementById("onlineVideoGrid");
    if (videoGrid && localVideo?.closest(".online-video-tile")) {
        videoGrid.replaceChildren(localVideo.closest(".online-video-tile"));
    }
    if (message) {
        document.getElementById("classroomMessage").textContent = message;
    }
    if (typeof loadClassrooms === "function") {
        void loadClassrooms();
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
    if (role === "student") {
        const input = document.getElementById("assignmentFiles");
        const subjectSelect = document.getElementById("subjectSelect");
        const message = document.getElementById("uploadMessage");

        if (input.files.length < 1) {
            message.innerText = "Please select at least 1 assignment.";
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
        if (document.getElementById("classroomSelect").required && !classroomId) {
            message.innerText = "Join and select a classroom before uploading.";
            return;
        }

        const formData = new FormData();
        Array.from(input.files).forEach(file => formData.append("files", file));
        formData.append("subject", subject);
        if (classroomId) {
            formData.append("classroom_id", classroomId);
        }
        message.innerText = "Uploading your assignment...";

        try {
            const uploadData = await requestApi("/assignments/upload", {
                method: "POST",
                body: formData,
            });
            const successfulUploads = (uploadData.results || []).filter(
                item => item.status === "success"
            ).length;
            const failedUploads = (uploadData.results || []).filter(
                item => item.status !== "success"
            );

            input.value = "";
            document.getElementById("fileList").replaceChildren();
            await Promise.all([loadMySubmissions(), loadDashboardData()]);

            if (successfulUploads) {
                message.innerText = `${successfulUploads} assignment${successfulUploads === 1 ? "" : "s"} submitted. Check My Assignments for the review status.`;
                showSection("my-submissions");
            } else {
                message.innerText = failedUploads
                    .map(item => `${item.filename}: ${item.message}`)
                    .join(" ") || "No assignments were uploaded.";
            }
        } catch (error) {
            console.error(error);
            message.innerText = error.message || "Assignment upload failed.";
        }
        return;
    }

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
            role === "teacher" || role === "authority" || role === "super_admin"
                ? await loadAllAssignments()
                : await loadMyAssignments();

        totalAssignmentsEl.innerText = String(assignments.length || 0);

        const duplicates = role === "student"
            ? assignments.filter(item => item.teacher_decision === "reject").length
            : assignments.filter(item => item.is_duplicate).length;
        duplicateAssignmentsEl.innerText = String(duplicates);

        if (role === "teacher" || role === "authority" || role === "super_admin") {
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
if (role === "student") {
    loadMySubmissions();
    loadNotifications();
}
if (role === "teacher" || role === "authority" || role === "super_admin") {
    loadTeacherReviewList();
}
window.setInterval(() => {
    if (!onlineClassSocket) {
        loadClassrooms();
        if (role === "teacher" || role === "authority" || role === "super_admin") {
            loadTeacherReviewList();
        }
    }
    if (role === "student") {
        loadNotifications();
    }
}, 10000);
showSection("home");