async function refreshDashboard() {

    const response = await fetch("/api/dashboard");

    const data = await response.json();

    document.getElementById("party-size").textContent =
        data.party_size;

    document.getElementById("queue-status").textContent =
        data.status ? "🟢 OPEN" : "🔴 CLOSED";
}


async function increaseParty() {

    await fetch("/party/increase", {
        method: "POST"
    });

    refreshDashboard();

}


async function decreaseParty() {

    await fetch("/party/decrease", {
        method: "POST"
    });

    refreshDashboard();

}


window.onload = () => {

    refreshDashboard();

};