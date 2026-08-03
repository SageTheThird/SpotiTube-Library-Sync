document.getElementById("syncButton").addEventListener("click", function () {
  const spinner = document.getElementById("spinner");
  spinner.classList.add("visible"); // Show spinner
  fetch("http://localhost:5000/run-script", { method: "POST" })
    .then((response) => response.json())
    .then((data) => {
      const logDiv = document.getElementById("log");
      logDiv.innerHTML = ""; // Clear previous log
      logDiv.appendChild(createLogParagraph(data.status));
      if (data.output) {
        logDiv.appendChild(createLogParagraph(data.output));
      }
    })
    .catch((error) => {
      document
        .getElementById("log")
        .appendChild(createLogParagraph("Error: " + error));
    })
    .finally(() => {
      spinner.classList.remove("visible"); // Hide spinner after operation
    });
});

function createLogParagraph(text) {
  const para = document.createElement("p");
  para.textContent = text;
  return para;
}
