document.addEventListener("DOMContentLoaded", () => {
    const transportSelect = document.getElementById("transport_type");
    const vehicleNumberLabel = document.getElementById("vehicleNumberLabel");
    const vehicleNumberHint = document.getElementById("vehicleNumberHint");
    const descriptionLabel = document.getElementById("descriptionLabel");
    const descriptionHint = document.getElementById("descriptionHint");
    const vehicleNumberInput = document.getElementById("vehicle_number");
    const vehicleNumberGroup = document.getElementById("vehicleNumberGroup");

    const transportLabels = {
        Bus: "Enter Bus Number",
        Train: "Enter Train Number",
        Auto: "Enter Auto Number",
        Metro: "Enter Metro Number",
        Taxi: "Enter Taxi Number",
    };

    const transportPrompts = {
        Bus: "Please describe the complaint on your Bus.",
        Train: "Please describe the complaint on your Train.",
        Auto: "Please describe the complaint on your Auto.",
        Metro: "Please describe the complaint on your Metro.",
        Taxi: "Please describe the complaint on your Taxi.",
    };

    const refreshComplaintFields = () => {
        if (!transportSelect) {
            return;
        }

        const selectedVehicle = transportSelect.value;
        const fieldLabel = transportLabels[selectedVehicle] || "Vehicle Number";
        const promptText = transportPrompts[selectedVehicle] || "Please describe the complaint clearly.";

        if (vehicleNumberGroup) {
            vehicleNumberGroup.style.display = selectedVehicle ? "block" : "none";
        }

        if (vehicleNumberLabel) {
            vehicleNumberLabel.textContent = fieldLabel;
        }

        if (vehicleNumberHint) {
            vehicleNumberHint.textContent = `Enter the ${selectedVehicle ? selectedVehicle.toLowerCase() : "selected transport"} number here.`;
        }

        if (descriptionLabel) {
            descriptionLabel.textContent = "Complaint Description";
        }

        if (descriptionHint) {
            descriptionHint.textContent = promptText;
        }

        if (vehicleNumberInput && selectedVehicle) {
            vehicleNumberInput.placeholder = `Enter ${selectedVehicle} number`;
        }

        if (vehicleNumberInput && !selectedVehicle) {
            vehicleNumberInput.placeholder = "Enter vehicle number";
        }
    };

    if (transportSelect) {
        transportSelect.addEventListener("change", refreshComplaintFields);
        refreshComplaintFields();
    }

    const profileStats = document.querySelector("[data-stat='complaint_count']");
    if (profileStats) {
        const refreshProfileStats = async () => {
            try {
                const response = await fetch("/api/profile_stats", {
                    cache: "no-store",
                    headers: { Accept: "application/json" },
                });
                if (!response.ok) {
                    return;
                }

                const stats = await response.json();
                Object.entries(stats).forEach(([key, value]) => {
                    const element = document.querySelector(`[data-stat='${key}']`);
                    if (element) {
                        element.textContent = value;
                    }
                });
            } catch (error) {
                // Keep the page usable even if the live refresh fails.
            }
        };

        const refreshComplaintStatus = async () => {
            try {
                const response = await fetch("/api/profile_complaints", {
                    cache: "no-store",
                    headers: { Accept: "application/json" },
                });
                if (!response.ok) {
                    return;
                }

                const data = await response.json();
                if (!data.complaints) {
                    return;
                }

                data.complaints.forEach((complaint) => {
                    const statusElement = document.querySelector(`[data-complaint-status='${complaint.id}']`);
                    if (statusElement) {
                        statusElement.textContent = complaint.status;
                        statusElement.className = `status-pill status-${complaint.status.toLowerCase().replace(/\s+/g, "-")}`;
                    }

                    const updatedElement = document.querySelector(`[data-complaint-updated='${complaint.id}']`);
                    if (updatedElement) {
                        updatedElement.textContent = `Updated: ${complaint.updated_at}`;
                    }
                });
            } catch (error) {
                // Keep the page usable even if the live refresh fails.
            }
        };

        refreshProfileStats();
        refreshComplaintStatus();
        window.setInterval(() => {
            refreshProfileStats();
            refreshComplaintStatus();
        }, 5000);
    }

    const flashMessages = document.querySelectorAll(".flash-message");
    if (flashMessages.length) {
        window.setTimeout(() => {
            flashMessages.forEach((message) => {
                message.style.transition = "opacity 0.25s ease, transform 0.25s ease";
                message.style.opacity = "0";
                message.style.transform = "translateY(8px)";
            });

            window.setTimeout(() => {
                const flashWrapper = document.querySelector(".flash-wrapper");
                if (flashWrapper) {
                    flashWrapper.remove();
                }
            }, 250);
        }, 2000);
    }

    const authTabs = document.querySelector("[data-auth-tabs]");
    if (authTabs) {
        const tabButtons = authTabs.querySelectorAll(".auth-tab");
        const panels = document.querySelectorAll(".auth-panel");

        tabButtons.forEach((button) => {
            button.addEventListener("click", () => {
                tabButtons.forEach((item) => item.classList.remove("active"));
                panels.forEach((panel) => panel.classList.remove("active"));

                button.classList.add("active");
                const targetPanel = document.getElementById(button.dataset.target);
                if (targetPanel) {
                    targetPanel.classList.add("active");
                }
            });
        });
    }

    const complaintForm = document.getElementById("complaintForm");

    if (complaintForm) {
        complaintForm.addEventListener("submit", (event) => {
            const description = document.getElementById("description").value.trim();
            const contact = document.getElementById("contact").value.trim();
            const image = document.getElementById("image").files[0];

            if (description.length < 10) {
                event.preventDefault();
                alert("Please provide a complaint description with at least 10 characters.");
                return;
            }

            if (contact.length < 5) {
                event.preventDefault();
                alert("Please enter a valid contact detail.");
                return;
            }

            if (!image) {
                event.preventDefault();
                alert("Please upload an image before submitting the complaint.");
            }
        });
    }
});
