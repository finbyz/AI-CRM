frappe.pages['lead-page'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Lead MIS Dashboard',
        single_column: true
    });

    $(frappe.render_template("lead_page", {})).appendTo(page.body);

    let allLeads = [];
    let filteredLeads = [];
    let globallySearchedLeads = [];
    let sourceChart = null;
    const allFetchedFields = [
        "name", "status", "lead_owner", "company_name", "source", "industry",
        "creation", "email_id", "mobile_no", "territory", "first_name", "last_name"
    ];
    let currentSort = { field: null, direction: "asc" };

    function showToast(msg, duration = 2200) {
        let toast = document.getElementById("custom-toast");
        toast.textContent = msg;
        toast.classList.add("show");
        setTimeout(() => toast.classList.remove("show"), duration);
    }

    document.getElementById("theme-toggle").addEventListener("change", function () {
        document.body.classList.toggle("dark-mode", this.checked);
        localStorage.setItem("dashboardTheme", this.checked ? "dark" : "light");
    });
    (function themeInit() {
        let saved = localStorage.getItem("dashboardTheme");
        if (saved === "dark") {
            document.body.classList.add("dark-mode");
            document.getElementById("theme-toggle").checked = true;
        }
    })();

    function getMultiSelectValues(selectId) {
        return Array.from(document.getElementById(selectId).selectedOptions).map(
            (opt) => opt.value
        );
    }

    // This function is defined locally but needs to be accessible by showDetails
    function createClickableNumber(count, filter) {
      if (count === 0) return "0";
      return `<span class="clickable-number" tabindex="0" onclick='showDetails(${JSON.stringify(
        filter
      )})'>${count}</span>`;
    }
    
    // This function is defined locally but needs to be accessible by showDetails
    function renderModalTable(records) {
      const searchTerm = document.getElementById("modal-search").value.toLowerCase();

      let shownRecords = records.filter((record) =>
        Object.values(record).some((val) =>
          String(val).toLowerCase().includes(searchTerm)
        )
      );

      let headers = allFetchedFields.map((field) => ({
        name: field,
        label: field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      }));

      // Sorting
      if (currentSort.field) {
        shownRecords.sort((a, b) => {
          let valA = a[currentSort.field] || "";
          let valB = b[currentSort.field] || "";
          if (!isNaN(Date.parse(valA)) && !isNaN(Date.parse(valB))) {
            valA = new Date(valA);
            valB = new Date(valB);
          }
          if (valA < valB) return currentSort.direction === "asc" ? -1 : 1;
          if (valA > valB) return currentSort.direction === "asc" ? 1 : -1;
          return 0;
        });
      }

      let tableHTML = `<table class="table table-bordered table-striped table-sm details-table"><thead><tr>`;
      headers.forEach((h) => {
        let sortClass =
          h.name === currentSort.field
            ? "sortable sorted-" + currentSort.direction
            : "sortable";
        tableHTML += `<th class="${sortClass}" tabindex="0" onclick="sortModalTable('${h.name}')">${h.label}</th>`;
      });
      tableHTML += `</tr></thead><tbody>`;
      if (shownRecords.length === 0) {
        tableHTML += `<tr><td colspan="${headers.length}" class="empty-state">No records match your search/filter.</td></tr>`;
      } else {
        shownRecords.forEach((rec) => {
          tableHTML += "<tr>";
          allFetchedFields.forEach((field) => {
            let value = rec[field] || "N/A";
            if (field === "name") {
              const fullName = `${rec.first_name || ""} ${
                rec.last_name || ""
              }`.trim() || rec.name;
              value = `<span class="lead-link" tabindex="0" onclick="navigateToLead('${rec.name}')">${fullName}</span>`;
            } else if (field === "creation") {
              value = new Date(value).toLocaleDateString();
            }
            tableHTML += `<td>${value}</td>`;
          });
          tableHTML += "</tr>";
        });
      }
      tableHTML += "</tbody></table>";

      document.getElementById("modal-table-container").innerHTML = tableHTML;
    }
    
    // This function is defined locally but needs to be accessible by showDetails
    function displayActiveFilters() {
      const filters = [
        { label: "From", value: document.getElementById("from-date").value },
        { label: "To", value: document.getElementById("to-date").value },
      ];
      const statusOpt = getMultiSelectValues("status-filter").filter(
        (v) => v !== "All Statuses"
      );
      if (statusOpt.length) filters.push({ label: "Status", value: statusOpt.join(", ") });
      const sourceOpt = getMultiSelectValues("source-filter").filter(
        (v) => v !== "All Sources"
      );
      if (sourceOpt.length) filters.push({ label: "Source", value: sourceOpt.join(", ") });
      let owner = document.getElementById("owner-filter").value;
      if (owner && owner !== "All Owners") filters.push({ label: "Owner", value: owner });
      let ind = document.getElementById("industry-filter").value;
      if (ind && ind !== "All Industries") filters.push({ label: "Industry", value: ind });
      let filterHTML = "<strong>Active Filters:</strong> ";
      filters.forEach((f) => {
        if (f.value) filterHTML += `<span class="badge badge-secondary">${f.label}: ${f.value}</span>`;
      });
      document.getElementById("modal-filters-display").innerHTML = filterHTML;
    }

    (async () => {
    await loadFilterOptions();

    // --- NEW: Add event listeners for the time period filter ---
    // 1. When the new 'Time Period' dropdown changes, update the dates.
    document.getElementById('time-period-filter').addEventListener('change', handleTimePeriodChange);

    // 2. (Good UX) If the user manually changes a date, reset the period dropdown to "Custom".
    const resetPeriodFilter = () => {
        document.getElementById('time-period-filter').value = 'custom';
    };
    document.getElementById('from-date').addEventListener('change', resetPeriodFilter);
    document.getElementById('to-date').addEventListener('change', resetPeriodFilter);
    
    // Finally, load the initial dashboard data.
    window.loadLeadData();
})();

    // Replace your existing loadFilterOptions function
    async function loadFilterOptions() {
     console.log("--- Starting to load filter options ---");
  try {
    // Status options
    console.log("Fetching statuses...");
    const leadsForStatus = await fetchLeads([], ["status"]);
    const statuses = ["All Statuses", ...new Set(leadsForStatus.map((l) => l.status).filter(Boolean))].sort();
    console.log(`Found ${statuses.length} statuses. Populating dropdown.`);
    populateDropdown("status-filter", statuses.map((s) => ({ name: s })), null, true);

    // Source options
    console.log("Fetching sources...");
    const sources = await fetchDoctypeOptions("Lead Source");
    console.log(`Found ${sources.length} sources. Populating dropdown.`);
    populateDropdown( "source-filter", [{ name: "All Sources" }, ...sources], null, true );

    // Owners/users
    console.log("Fetching owners...");
    const owners = await fetchDoctypeOptions( "User", ["name", "full_name"], [["enabled", "=", 1]] );
    console.log(`Found ${owners.length} owners. Populating dropdown.`);
    populateDropdown("owner-filter", [{ name: "All Owners" }, ...owners], "full_name");

    // Industry
    console.log("Fetching industries...");
    const industries = await fetchDoctypeOptions("Industry Type");
    console.log(`Found ${industries.length} industries. Populating dropdown.`);
    populateDropdown( "industry-filter", [{ name: "All Industries" }, ...industries] );
    
    console.log("--- Finished loading all filter options ---");
  } catch (e) {
    console.error("CRITICAL ERROR in loadFilterOptions:", e);
  }
}

// Replace your existing populateDropdown function
function populateDropdown(elementId, options, textField = "name", isMulti = false) {
  console.log(`  -> Populating #${elementId} with ${options.length} options.`);
  const select = document.getElementById(elementId);
  if (!select) {
    console.error(`  -> FATAL: Element with ID #${elementId} NOT FOUND.`);
    return;
  }
  select.innerHTML = "";
  options.forEach((opt) => {
    const option = document.createElement("option");
    option.value = opt.name;
    option.textContent = textField ? opt[textField] || opt.name : opt.name;
    select.appendChild(option);
  });
  if (isMulti) {
    Array.from(select.options).forEach((opt) => {
      if (opt.value && /^All/.test(opt.value)) opt.selected = true;
    });
  } else {
    select.selectedIndex = 0;
  }
}

    async function fetchDoctypeOptions(doctype, fields = ["name"], filters = []) {
        if (typeof frappe === "undefined") return [];
        try {
            const response = await frappe.call({
                method: "frappe.client.get_list",
                args: { doctype, fields, filters, limit_page_length: 1000 },
            });
            return response.message || [];
        } catch (e) {
            console.error(`Failed to fetch ${doctype}`, e);
            return [];
        }
    }

    async function fetchLeads(filters = [], fields = allFetchedFields) {
        if (typeof frappe === "undefined") return generateMockLeads();
        const response = await frappe.call({
            method: "frappe.client.get_list",
            args: { doctype: "Lead", fields, filters, limit_page_length: 0 },
        });
        return response.message || [];
    }

    function makeDateValid(from, to) {
        if (from && to && to < from) {
            showToast("End date cannot be before start date", 2000);
            return false;
        }
        return true;
    }

     function handleTimePeriodChange() {
        const period = document.getElementById('time-period-filter').value;
        if (period === 'custom') {
            return; // If user selects "Custom", do nothing and let them pick dates manually.
        }

        const toDateEl = document.getElementById('to-date');
        const fromDateEl = document.getElementById('from-date');

        const toDate = new Date();
        let fromDate = new Date();

        // Calculate the 'from' date based on the selected period
        switch (period) {
            case 'last_week':
                fromDate.setDate(toDate.getDate() - 7);
                break;
            case 'last_month':
                fromDate.setMonth(toDate.getMonth() - 1);
                break;
            case 'last_3_months':
                fromDate.setMonth(toDate.getMonth() - 3);
                break;
            case 'last_6_months':
                fromDate.setMonth(toDate.getMonth() - 6);
                break;
            case 'last_year':
                fromDate.setFullYear(toDate.getFullYear() - 1);
                break;
        }

        // Helper to format date to YYYY-MM-DD for input fields
        const formatDate = (date) => {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
        };

        // Set the values of the date input fields
        toDateEl.value = formatDate(toDate);
        fromDateEl.value = formatDate(fromDate);

        // Automatically refresh the dashboard with the new dates
        window.loadLeadData();
    }
    // 🔹 Global function so HTML and other functions can call it
  window.loadLeadData = async function () {
    console.log("--- Starting Filter Debug ---");
    document.getElementById("loading-container").style.display = "block";
    document.getElementById("dashboard-content").style.display = "none";

    try {
        // --- Let's debug the filter values one by one ---

        // Debugging Lead Owner
        const ownerElement = document.getElementById("owner-filter");
        console.log("1. Lead Owner HTML Element:", ownerElement);
        const ownerFilterValue = ownerElement ? ownerElement.value : "ELEMENT NOT FOUND";
        console.log("2. Value read from Lead Owner dropdown:", `"${ownerFilterValue}"`); // Quotes help see spaces
        const isOwnerFilterValid = ownerFilterValue && ownerFilterValue !== "All Owners";
        console.log("3. Is the Lead Owner filter condition met?", isOwnerFilterValid);

        // Debugging Industry
        const industryElement = document.getElementById("industry-filter");
        console.log("4. Industry HTML Element:", industryElement);
        const industryFilterValue = industryElement ? industryElement.value : "ELEMENT NOT FOUND";
        console.log("5. Value read from Industry dropdown:", `"${industryFilterValue}"`);
        const isIndustryFilterValid = industryFilterValue && industryFilterValue !== "All Industries";
        console.log("6. Is the Industry filter condition met?", isIndustryFilterValid);

        // Debugging Status (Multi-select)
        const statusFilterValues = getMultiSelectValues("status-filter").filter(v => v !== "All Statuses");
        console.log("7. Values read from Status multi-select:", statusFilterValues);
        const isStatusFilterValid = statusFilterValues.length > 0;
        console.log("8. Is the Status filter condition met?", isStatusFilterValid);

        // --- Now, let's build the filters like before ---
        let filters = [];
        const fromDate = document.getElementById("from-date").value;
        const toDate = document.getElementById("to-date").value;
        if (fromDate && toDate) {
            filters.push(["creation", "between", [fromDate, toDate]]);
        }
        if (isStatusFilterValid) {
            filters.push(["status", "in", statusFilterValues]);
        }
        if (isOwnerFilterValid) {
            filters.push(["lead_owner", "=", ownerFilterValue]);
        }
        if (isIndustryFilterValid) {
            filters.push(["industry", "=", industryFilterValue]);
        }
        // (You can add the same logic for the 'source' filter)

        console.log("FINAL FILTERS to be sent:", JSON.stringify(filters));
        
        // Fetch leads and render the rest of the dashboard...
        allLeads = await fetchLeads(filters);
        filteredLeads = [...allLeads];
        applyGlobalSearch();
        window.renderSummaries();
        window.renderStatusTable();
        window.renderOwnerTable();
        window.renderSourceChart();
        document.getElementById("dashboard-content").style.display = "block";
        showToast("Filters applied!");

    } catch (error) {
        showToast("Error loading data. Check console.", 3200);
        console.error("Error loading lead data:", error);
    } finally {
        document.getElementById("loading-container").style.display = "none";
    }
}

    document.getElementById("global-search").oninput = function () {
        applyGlobalSearch();
        window.renderSummaries();
        window.renderStatusTable();
        window.renderOwnerTable();
        window.renderSourceChart();
    };

    function applyGlobalSearch() {
        const searchTerm = document.getElementById("global-search").value.trim().toLowerCase();
        if (!searchTerm) {
            globallySearchedLeads = [...filteredLeads];
            return;
        }
        globallySearchedLeads = filteredLeads.filter(lead => {
            return allFetchedFields.some(f =>
                String(lead[f] || "").toLowerCase().includes(searchTerm)
            );
        });
    }

    // 🔹 Now global so HTML inline calls work
    window.renderSummaries = function () { 
        const leads = globallySearchedLeads;
        const totalLeads = leads.length;
        const openLeads = leads.filter((l) =>
            ["Open", "Replied"].includes(l.status)
        ).length;
        const convertedLeads = leads.filter((l) => l.status === "Converted").length;
        const lostLeads = leads.filter((l) =>
            ["Do Not Contact", "Unqualified"].includes(l.status)
        ).length;

        const summaryHTML = `
            <div class="summary-card">
              <div class="icon total">
                <i class="fa-solid fa-layer-group"></i>
              </div>
              <div>
                <h5>Total Leads</h5>
                <div class="count">${createClickableNumber(totalLeads, {})}</div>
              </div>
            </div>
            <div class="summary-card">
              <div class="icon open">
                <i class="fa-solid fa-folder-open"></i>
              </div>
              <div>
                <h5>Open Leads</h5>
                <div class="count">${createClickableNumber(openLeads, {
                  status: ["Open", "Replied"],
                })}</div>
              </div>
            </div>
            <div class="summary-card">
              <div class="icon converted">
                <i class="fa-solid fa-circle-check"></i>
              </div>
              <div>
                <h5>Converted</h5>
                <div class="count">${createClickableNumber(convertedLeads, {
                  status: "Converted",
                })}</div>
              </div>
            </div>
            <div class="summary-card">
              <div class="icon lost">
                <i class="fa-solid fa-circle-xmark"></i>
              </div>
              <div>
                <h5>Lost</h5>
                <div class="count">${createClickableNumber(lostLeads, {
                  status: ["Do Not Contact", "Unqualified"],
                })}</div>
              </div>
            </div>
        `;
        document.getElementById("overall-summary").innerHTML = summaryHTML;
     }
    window.renderStatusTable = function () { 
        const leads = globallySearchedLeads;
        if (leads.length === 0) {
            document.getElementById(
              "status-summary-section"
            ).innerHTML = `<div class="empty-state">No lead data found for selected filters and search.</div>`;
            return;
        }
        const statusCounts = leads.reduce((acc, lead) => {
            const status = lead.status || "Uncategorized";
            acc[status] = (acc[status] || 0) + 1;
            return acc;
        }, {});
        let tableHTML = `<h5>By Status</h5><table class="table table-striped"><thead><tr><th>Status</th><th class="text-right">Leads</th></tr></thead><tbody>`;
        Object.entries(statusCounts)
            .sort((a, b) => b[1] - a[1])
            .forEach(([status, count]) => {
              tableHTML += `<tr><td>${status}</td><td class="text-right">${createClickableNumber(
                count,
                { status }
              )}</td></tr>`;
            });
        document.getElementById("status-summary-section").innerHTML =
            tableHTML + "</tbody></table>";
     }
    window.renderOwnerTable = function () { 
        const leads = globallySearchedLeads;
        const section = document.getElementById("owner-summary-section");
        if (leads.length === 0) {
            section.innerHTML = `<div class="empty-state">No lead data found for selected filters and search.</div>`;
            return;
        }
        const ownerCounts = leads.reduce((acc, lead) => {
            const owner = lead.lead_owner || "Unassigned";
            if (!acc[owner]) acc[owner] = { total: 0, converted: 0, lost: 0, owner };
            acc[owner].total++;
            if (lead.status === "Converted") acc[owner].converted++;
            else if (["Do Not Contact", "Unqualified"].includes(lead.status)) acc[owner].lost++;
            return acc;
        }, {});

        const sorted = Object.values(ownerCounts).sort((a, b) => b.total - a.total);

        let html = `<h5 class="mb-3">By Lead Owner</h5>
            <div class="lead-owner-grid">`;
        sorted.forEach(({ owner, total, converted, lost }) => {
            let initials =
              owner === "Unassigned"
                ? "?"
                : owner
                    .split("@")[0]
                    .split(/[.\s_]/)
                    .map((w) => w[0]?.toUpperCase())
                    .join("")
                    .slice(0, 2) || "U";
            html += `
              <div class="owner-card">
                <div class="owner-avatar">${initials}</div>
                <div class="owner-name" title="${owner}">${owner}</div>
                <div class="owner-metrics">
                  <span class="metric total">${createClickableNumber(
                    total,
                    { lead_owner: owner }
                  )} <small>Total</small></span>
                  <span class="metric converted">${createClickableNumber(
                    converted,
                    { lead_owner: owner, status: "Converted" }
                  )} <small>Converted</small></span>
                  <span class="metric lost">${createClickableNumber(
                    lost,
                    { lead_owner: owner, status: ["Do Not Contact", "Unqualified"] }
                  )} <small>Lost</small></span>
                </div>
              </div>`;
        });
        html += "</div>";
        section.innerHTML = html;
     }
    window.renderSourceChart = function () { 
        const leads = globallySearchedLeads;
        const sourceCounts = leads.reduce((acc, { source }) => {
            acc[source || "Unknown"] = (acc[source || "Unknown"] || 0) + 1;
            return acc;
        }, {});
        const sorted = Object.entries(sourceCounts).sort((a, b) => b[1] - a[1]);
        if (sourceChart) sourceChart.destroy();
        sourceChart = new Chart(
            document.getElementById("sourceChart").getContext("2d"),
            {
              type: "doughnut",
              data: {
                labels: sorted.map((s) => s[0]),
                datasets: [
                  {
                    data: sorted.map((s) => s[1]),
                    backgroundColor: [
                      "#007bff", "#28a745", "#ffc107", "#dc3545",
                      "#17a2b8", "#6610f2", "#fd7e14", "#6c757d",
                    ],
                    borderWidth: 1,
                  },
                ],
              },
              options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
              },
            }
        );
     }
    window.showDetails = function (filter) { 
        let leads = globallySearchedLeads;
        const records = leads.filter((lead) => {
            let match = true;
            if (filter.status) {
              if (Array.isArray(filter.status))
                match = match && filter.status.includes(lead.status);
              else match = match && lead.status === filter.status;
            }
            if (filter.lead_owner) match = match && lead.lead_owner === filter.lead_owner;
            return match;
        });

        document.getElementById("modal-title").textContent = `Lead Details (${
            records.length
        } Records)`;
        displayActiveFilters();
        renderModalTable(records);
        document.getElementById("records-modal").style.display = "flex";
        document.body.classList.add("modal-open");
        document.getElementById("modal-search").value = "";
        document.getElementById("modal-search").onkeyup = () => renderModalTable(records);
        showToast(
            records.length ? "Loaded lead details." : "No lead records found for your selection.",
            1200
        );
     }
    window.sortModalTable = function (field) { 
        if (currentSort.field === field)
            currentSort.direction = currentSort.direction === "asc" ? "desc" : "asc";
        else currentSort = { field, direction: "asc" };
        
        // Re-render modal table with current lead records by finding the currently shown leads
        const modalTitle = document.getElementById("modal-title").textContent;
        const currentFilter = JSON.parse(
          document
            .querySelector(".clickable-number")
            ?.getAttribute("onclick")
            .match(/\((.*)\)/)[1] || "{}"
        );
        let leadsToDisplay = globallySearchedLeads.filter((lead) => {
          let match = true;
          if (currentFilter.status) {
            if (Array.isArray(currentFilter.status))
              match = match && currentFilter.status.includes(lead.status);
            else match = match && lead.status === currentFilter.status;
          }
          if (currentFilter.lead_owner)
            match = match && lead.lead_owner === currentFilter.lead_owner;
          return match;
        });
        renderModalTable(leadsToDisplay);
     }
    window.navigateToLead = function (leadName) { 
        if (typeof frappe !== "undefined") {
            frappe.set_route("Form", "Lead", leadName);
        } else {
            showToast("Navigation simulated: " + leadName, 1200);
        }
     }
    window.closeModal = function () { 
        document.getElementById("records-modal").style.display = "none";
        document.body.classList.remove("modal-open");
     }
    
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeModal();
    });

    function generateMockLeads() { 
        const statuses = ["Open", "Replied", "Converted", "Do Not Contact", "Unqualified"];
        const sources = ["Web Form", "Advertisement", "Cold Calling", "Trade Show"];
        const owners = ["john@example.com", "jane@example.com", "peter@example.com"];
        const industries = ["IT", "Healthcare", "Finance", "Manufacturing"];
        const leads = [];
        for (let i = 0; i < 200; i++) {
            leads.push({
              name: `LEAD-00${100 + i}`,
              first_name: `User${i}`,
              last_name: `Test`,
              status: statuses[Math.floor(Math.random() * statuses.length)],
              lead_owner: owners[Math.floor(Math.random() * owners.length)],
              company_name: `Company ${i}`,
              source: sources[Math.floor(Math.random() * sources.length)],
              industry: industries[Math.floor(Math.random() * industries.length)],
              creation: new Date(
                new Date() - Math.random() * 60 * 24 * 60 * 60 * 1000
              ).toISOString(),
              email_id: `user${i}@example.com`,
              mobile_no: `987654321${i}`,
              territory: "Global",
            });
        }
        return leads;
     }
}