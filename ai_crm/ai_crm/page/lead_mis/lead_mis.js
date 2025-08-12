frappe.pages['lead_mis'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Lead MIS Dashboard',
        single_column: true
    });

    // Inject your HTML template into the page
    $(frappe.render_template("lead_mis", {})).appendTo(page.body);

    // --- SCRIPT SECTION ---
    let allLeads = [];
    let filteredLeads = [];
    let globallySearchedLeads = [];
    let sourceChart = null;
    const allFetchedFields = [
        "name", "status", "lead_owner", "company_name", "source",
        "industry", "creation", "email_id", "mobile_no",
        "territory", "first_name", "last_name"
    ];
    let currentSort = { field: null, direction: "asc" };

    function showToast(msg, duration = 2200) {
        frappe.show_alert({message: msg, indicator: 'blue'}, duration / 1000);
    }

    document.getElementById("theme-toggle")?.addEventListener("change", function () {
        document.body.classList.toggle("dark-mode", this.checked);
        frappe.boot.dashboardTheme = this.checked ? "dark" : "light";
    });

    function getMultiSelectValues(selectId) {
        return Array.from(document.getElementById(selectId).selectedOptions).map(opt => opt.value);
    }

    frappe.after_ajax(async () => {
        await loadFilterOptions();
        loadLeadData();
    });

    async function loadFilterOptions() {
        const leadsForStatus = await fetchLeads([], ["status"]);
        const statuses = ["All Statuses", ...new Set(leadsForStatus.map(l => l.status).filter(Boolean))].sort();
        populateDropdown("status-filter", statuses.map(s => ({ name: s })), null, true);

        const sources = await fetchDoctypeOptions("Lead Source");
        populateDropdown("source-filter", [{ name: "All Sources" }, ...sources], null, true);

        const owners = await fetchDoctypeOptions("User", ["name", "full_name"], [["enabled", "=", 1]]);
        populateDropdown("owner-filter", [{ name: "All Owners" }, ...owners], "full_name");

        const industries = await fetchDoctypeOptions("Industry Type");
        populateDropdown("industry-filter", [{ name: "All Industries" }, ...industries]);
    }

    function populateDropdown(elementId, options, textField = "name", isMulti = false) {
        const select = document.getElementById(elementId);
        if (!select) return;
        select.innerHTML = "";
        options.forEach(opt => {
            const option = document.createElement("option");
            option.value = opt.name;
            option.textContent = textField ? opt[textField] || opt.name : opt.name;
            select.appendChild(option);
        });
        if (isMulti) {
            Array.from(select.options).forEach(opt => {
                if (opt.value && /^All/.test(opt.value)) opt.selected = true;
            });
        } else {
            select.selectedIndex = 0;
        }
    }

    async function fetchDoctypeOptions(doctype, fields = ["name"], filters = []) {
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

    async function loadLeadData() {
        $("#loading-container").show();
        $("#dashboard-content").hide();

        try {
            const fromDate = $("#from-date").val();
            const toDate = $("#to-date").val();
            if (!makeDateValid(fromDate, toDate)) return;

            const statusFilter = getMultiSelectValues("status-filter");
            const sourceFilter = getMultiSelectValues("source-filter");
            const ownerFilter = $("#owner-filter").val();
            const industryFilter = $("#industry-filter").val();

            let filters = [];
            if (fromDate && toDate) filters.push(["creation", "between", [fromDate, toDate]]);

            allLeads = await fetchLeads(filters);

            filteredLeads = allLeads.filter(lead =>
                (statusFilter.includes("All Statuses") || statusFilter.length === 0 || statusFilter.includes(lead.status)) &&
                (sourceFilter.includes("All Sources") || sourceFilter.length === 0 || sourceFilter.includes(lead.source)) &&
                (ownerFilter === "All Owners" || !ownerFilter || lead.lead_owner === ownerFilter) &&
                (industryFilter === "All Industries" || !industryFilter || lead.industry === industryFilter)
            );

            applyGlobalSearch();
            renderSummaries();
            renderStatusTable();
            renderOwnerTable();
            renderSourceChart();

            $("#dashboard-content").show();
            showToast("Filters applied!");
        } catch (error) {
            showToast("Error loading data. Check console.", 3200);
            console.error("Error loading lead data:", error);
        } finally {
            $("#loading-container").hide();
        }
    }

    $("#global-search").on("input", function () {
        applyGlobalSearch();
        renderSummaries();
        renderStatusTable();
        renderOwnerTable();
        renderSourceChart();
    });

    function applyGlobalSearch() {
        const searchTerm = $("#global-search").val().trim().toLowerCase();
        if (!searchTerm) {
            globallySearchedLeads = [...filteredLeads];
            return;
        }
        globallySearchedLeads = filteredLeads.filter(lead =>
            allFetchedFields.some(f =>
                String(lead[f] || "").toLowerCase().includes(searchTerm)
            )
        );
    }

    // NOTE: Keep all render functions and modal functions from your HTML JS here exactly as in your original script
    // (renderSummaries, renderStatusTable, renderOwnerTable, renderSourceChart, createClickableNumber, showDetails, etc.)

};
