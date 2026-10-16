function formatTime(seconds) {
    return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
}

function formatRunning(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor(seconds / 60) % 60;
    return (hours ? hours + "h " : "") + minutes + "m " + (seconds % 60) + "s";
}

function parseTime(text) {
    return new Date(text.replace(" ", "T")).getTime();
}

function fillTable(id, rows, columns) {
    document.getElementById(id).innerHTML = rows.length
        ? rows.map(cells => "<tr>" + cells.map(cell => `<td>${cell}</td>`).join("") + "</tr>").join("")
        : `<tr><td class="muted empty" colspan="${columns}">Nothing saved yet</td></tr>`;
}

const pages = ["live", "analytics", "history", "settings"];

function currentPage() {
    const page = location.hash.slice(1);
    return pages.includes(page) ? page : "live";
}

function showPage() {
    const page = currentPage();
    for (const name of pages) {
        document.getElementById("page-" + name).hidden = name !== page;
    }
    document.querySelectorAll("nav a").forEach(a => a.classList.toggle("active", a.hash === "#" + page));
    if (page === "settings") {
        loadSettings();
    }
    refresh();
}

window.addEventListener("hashchange", showPage);

const WIDTH = 500, HEIGHT = 170, LEFT = 30, RIGHT = 30, TOP = 10, BOTTOM = 25;
const tooltip = document.getElementById("tooltip");

function drawChart(svg, points, key, maxValue, serverNow, seconds, unit) {
    const plotW = WIDTH - LEFT - RIGHT, plotH = HEIGHT - TOP - BOTTOM;
    const end = parseTime(serverNow);
    const start = seconds ? end - seconds * 1000 : (points.length ? parseTime(points[0].time) : end - 1000);
    const xOf = time => LEFT + (time - start) / Math.max(end - start, 1) * plotW;
    const yOf = value => TOP + plotH - value / maxValue * plotH;

    let html = "";
    for (const value of [0, maxValue / 2, maxValue]) {
        html += `<line class="gridline" x1="${LEFT}" x2="${WIDTH - RIGHT}" y1="${yOf(value)}" y2="${yOf(value)}"/>
            <text class="axis" x="${LEFT - 8}" y="${yOf(value) + 4}" text-anchor="end">${Math.round(value)}</text>`;
    }

    let last = 0;
    if (points.length) {
        const xy = points.map(p => [xOf(parseTime(p.time)), yOf(p[key])]);
        let path = `M${xy[0][0]},${xy[0][1]}`;
        for (let i = 1; i < xy.length; i++) {
            path += ` H${xy[i][0]} V${xy[i][1]}`;
        }
        path += ` H${xOf(end)}`;
        html += `<path class="area" d="${path} V${yOf(0)} H${xy[0][0]} Z"/><path class="line" d="${path}"/>`;
        last = points[points.length - 1][key];
    }

    const startLabel = seconds ? formatRunning(seconds).replace(/^0m /, "").replace(/ 0s$/, "") + " ago" : "first";
    html += `<circle class="end" cx="${xOf(end)}" cy="${yOf(last)}" r="3"/>
        <text class="axis" x="${xOf(end) + 8}" y="${yOf(last) + 4}">${last}</text>
        <text class="axis" x="${LEFT}" y="${HEIGHT - 5}">${startLabel}</text>
        <text class="axis" x="${WIDTH - RIGHT}" y="${HEIGHT - 5}" text-anchor="end">now</text>
        <line class="cursor" id="${svg.id}-cursor" y1="${TOP}" y2="${TOP + plotH}" visibility="hidden"/>`;
    svg.innerHTML = html;

    svg.chart = {points, key, end, start, plotW, unit};
}

function showTooltip(event) {
    const svg = event.currentTarget;
    const chart = svg.chart;
    if (!chart || !chart.points.length) {
        return;
    }
    const box = svg.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width * WIDTH;
    const time = chart.start + (x - LEFT) / chart.plotW * (chart.end - chart.start);

    let point = null;
    for (const p of chart.points) {
        if (parseTime(p.time) <= time) {
            point = p;
        }
    }
    if (!point || x < LEFT || x > WIDTH - RIGHT) {
        hideTooltip(event);
        return;
    }

    const cursor = document.getElementById(svg.id + "-cursor");
    cursor.setAttribute("x1", x);
    cursor.setAttribute("x2", x);
    cursor.setAttribute("visibility", "visible");

    const ago = Math.max(0, Math.round((chart.end - time) / 1000));
    tooltip.textContent = `${point[chart.key]} ${chart.unit} • ${ago < 60 ? ago + "s" : formatTime(ago)} ago`;
    tooltip.style.left = event.clientX + "px";
    tooltip.style.top = (box.top + window.scrollY + 4) + "px";
    tooltip.style.display = "block";
}

function hideTooltip(event) {
    tooltip.style.display = "none";
    const cursor = document.getElementById(event.currentTarget.id + "-cursor");
    if (cursor) {
        cursor.setAttribute("visibility", "hidden");
    }
}

document.querySelectorAll(".chart").forEach(svg => {
    svg.addEventListener("mousemove", showTooltip);
    svg.addEventListener("mouseleave", hideTooltip);
});

let stats = {ready: false};
const video = document.getElementById("video");

function drawSummary() {
    const freeTables = stats.total_tables - stats.occupied_tables;
    document.getElementById("occupied").textContent = stats.occupied_tables;
    document.getElementById("occupied-of").textContent = "of " + stats.total_tables + " tables";
    document.getElementById("walk-ins").textContent = freeTables + " available for walk-ins";

    const capacity = stats.guests / stats.seats * 100;
    document.getElementById("guests").textContent = stats.guests;
    document.getElementById("guests-of").textContent = "/ " + stats.seats + " covers";
    document.getElementById("capacity").textContent = capacity.toFixed(1) + "% dining capacity";

    document.getElementById("utilization").textContent = Math.round(capacity) + "%";
    document.getElementById("free").textContent = (stats.seats - stats.guests) + " seats free";

    const busy = Object.entries(stats.tables).filter(([name, table]) => table.occupied);
    if (busy.length === 0) {
        document.getElementById("avg-time").textContent = "-";
        document.getElementById("longest").textContent = "No guests seated";
        return;
    }
    const average = busy.reduce((sum, [name, table]) => sum + table.seconds, 0) / busy.length;
    const [longestName, longest] = busy.reduce((a, b) => (b[1].seconds > a[1].seconds ? b : a));
    document.getElementById("avg-time").textContent = formatTime(Math.round(average));
    document.getElementById("longest").textContent = "Longest: " + longestName + " \u2022 " + formatTime(longest.seconds);
}

function seatAngle(seat, count, shape) {
    const start = shape === "square" ? 0 : 45;
    return (start + seat * 360 / count) % 360;
}

function drawFloorPlan() {
    const tables = Object.entries(stats.tables);
    document.getElementById("table-count").textContent = "(" + tables.length + " tables)";

    document.getElementById("tables").innerHTML = tables.map(([name, table]) => {
        let seats = "";
        for (let seat = 0; seat < stats.seats_per_table; seat++) {
            const angle = seatAngle(seat, stats.seats_per_table, table.shape);
            const radians = angle * Math.PI / 180;
            const x = 50 + Math.cos(radians) * 46;
            const y = 50 + Math.sin(radians) * 46;
            const taken = table.seats_taken.includes(seat) ? " taken" : "";
            seats += `<i class="chair${taken}" style="left:${x}%;top:${y}%;transform:translate(-50%,-50%) rotate(${angle + 90}deg)"></i>`;
        }
        const number = name.split(" ").pop().padStart(2, "0");
        const state = table.occupied
            ? `${table.guests}/${stats.seats_per_table}<br>${formatTime(table.seconds)}`
            : "Free";
        return `<div class="spot">${seats}
            <div class="top ${table.shape}${table.occupied ? " busy" : ""}"><b>${number}</b><span>${state}</span></div>
        </div>`;
    }).join("");
}

video.addEventListener("error", () => {
    setTimeout(() => {
        video.src = "/video?" + Date.now();
    }, 2000);
});

document.getElementById("restart").addEventListener("click", () => {
    fetch("/restart", {method: "POST"});
});

document.getElementById("fullscreen").addEventListener("click", () => {
    if (document.fullscreenElement) {
        document.exitFullscreen();
    } else {
        video.requestFullscreen();
    }
});

async function refreshAnalytics() {
    const data = await (await fetch("/analytics/data")).json();
    const mostGuests = Math.max(4, ...data.points.map(p => p.guests));
    drawChart(document.getElementById("live-guests"), data.points, "guests", mostGuests, data.now, 300, "guests");
    drawChart(document.getElementById("live-tables"), data.points, "occupied_tables",
        stats.total_tables || 6, data.now, 300, "tables");

    fillTable("activity-body", data.activity.map(a => [
        `<span class="mono">${a.time.split(" ")[1]}</span>`, a.table, a.event, a.guests,
    ]), 4);
}

let rangeSeconds = 300;

async function refreshHistory() {
    const history = await (await fetch("/history/data?seconds=" + rangeSeconds)).json();
    document.getElementById("saved").textContent = `Saved in the database: ${history.counts.visits} visits `
        + `and ${history.counts.snapshots} snapshots`;

    const mostGuests = Math.max(4, ...history.snapshots.map(s => s.guests));
    drawChart(document.getElementById("history-guests"), history.snapshots, "guests", mostGuests,
        history.now, rangeSeconds, "guests");
    drawChart(document.getElementById("history-tables"), history.snapshots, "occupied_tables",
        stats.total_tables || 6, history.now, rangeSeconds, "tables");

    fillTable("tables-body", history.tables.map(t => [
        t.table_name, t.visits, formatTime(t.average_seconds), formatTime(t.longest_seconds), t.average_guests,
    ]), 5);
    fillTable("recent-body", history.recent.map(v => [
        `<span class="mono">${v.ended}</span>`, v.table_name, v.guests, formatTime(v.seconds),
    ]), 4);
}

document.getElementById("ranges").addEventListener("click", event => {
    const button = event.target.closest("button");
    if (!button) {
        return;
    }
    document.querySelectorAll("#ranges button").forEach(b => b.classList.remove("active"));
    button.classList.add("active");
    rangeSeconds = Number(button.dataset.seconds);
    document.getElementById("range-label").textContent = rangeSeconds ? "Last " + button.textContent : "All time";
    refreshHistory();
});

const form = document.getElementById("settings-form");

async function loadSettings() {
    const data = await (await fetch("/settings")).json();
    document.getElementById("video-select").innerHTML = data.videos
        .map(v => `<option value="${v}">${v.split("/").pop()}</option>`).join("");
    for (const [key, value] of Object.entries(data.settings)) {
        if (form.elements[key]) {
            form.elements[key].value = value;
        }
    }
    document.getElementById("saved-note").textContent = "";
}

form.addEventListener("submit", event => {
    event.preventDefault();
    document.getElementById("save").click();
});

document.getElementById("save").addEventListener("click", async () => {
    const values = {};
    for (const element of form.elements) {
        if (element.name) {
            values[element.name] = element.type === "number" ? Number(element.value) : element.value;
        }
    }
    const note = document.getElementById("saved-note");
    note.textContent = "Saving...";
    try {
        await fetch("/settings", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(values),
        });
        await loadSettings();
        note.textContent = "Saved. The video restarts with the new settings.";
    } catch (error) {
        note.textContent = "Could not save, is the server running?";
    }
});

document.getElementById("reset").addEventListener("click", async () => {
    if (!confirm("Put every setting back to its default value?")) {
        return;
    }
    await fetch("/settings/reset", {method: "POST"});
    await loadSettings();
    document.getElementById("saved-note").textContent = "Back to defaults. The video restarts.";
});

async function refresh() {
    try {
        stats = await (await fetch("/stats")).json();
    } catch (error) {
        document.getElementById("status").classList.add("offline");
        document.getElementById("status-text").textContent = "Offline";
        return;
    }

    document.getElementById("status").classList.remove("offline");
    document.getElementById("status-text").textContent = stats.ready ? "Live " + Math.round(stats.processing_fps) + "fps" : "Starting";
    document.querySelectorAll(".video-name").forEach(el => (el.textContent = stats.video));
    if (!stats.ready) {
        return;
    }
    document.getElementById("running").textContent = "Running: " + formatRunning(stats.running_seconds);

    const page = currentPage();
    if (page === "live") {
        drawSummary();
        drawFloorPlan();
    } else if (page === "analytics") {
        await refreshAnalytics();
    } else if (page === "history") {
        await refreshHistory();
    }
}

showPage();
setInterval(refresh, 1000);
