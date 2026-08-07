const API_URL = "https://automatic-adventure-5g9gqvxwgpw6c7x4r-8000.app.github.dev";


async function loadAthletes() {
    try {
        const response = await fetch(`${API_URL}/api/athletes`);

        if (!response.ok) {
            throw new Error("Failed to load athletes");
        }

        const athletes = await response.json();

        displayAthletes(athletes);

    } catch (error) {
        console.error("Error loading athletes:", error);

        document.getElementById("athletes-list").innerHTML = `
            <p class="text-red-600">
                Unable to load athletes.
            </p>
        `;
    }
}


function displayAthletes(athletes) {

    const athletesList = document.getElementById("athletes-list");

    athletesList.innerHTML = "";

    athletes.forEach(athlete => {

        const card = document.createElement("div");

        card.className =
            "bg-white rounded-xl shadow-md p-6 hover:shadow-xl transition";


        card.innerHTML = `
            <h2 class="text-2xl font-bold mb-2">
                ${athlete.name}
            </h2>

            <p class="text-gray-600 mb-6">
                ${athlete.sport}
            </p>

            <button
                class="w-full bg-blue-600 text-white
                       py-3 px-4 rounded-lg
                       hover:bg-blue-700 transition"
                onclick="startTest('${athlete.id}')"
            >
                Start Test
            </button>
        `;


        athletesList.appendChild(card);

    });

}


function startTest(athleteId) {

    window.location.href = `test.html?athlete=${athleteId}`;

}


loadAthletes();