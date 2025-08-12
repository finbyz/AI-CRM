// Refactored Lead Dashboard JavaScript

class LeadDashboard {
  constructor() {
    this.allLeads = [];
    this.displayLeads = []; // For global search filtering
    this.analytics = {};
    this.sourceChart = null;
    this.currentSort = { field: 'creation', direction: 'desc' };
    
    // The name of your custom Frappe app
    this.appName = 'ai_crm'; // <-- IMPORTANT: Change this to your app's name

    // The fields to display in the details modal
    this.modalFields = [
      "name", "full_name", "status", "lead_owner", "company_name", 
      "source", "industry", "creation", "email_id", "mobile_no", "territory"
    ];

    this.init();
  }

  // Initialize dashboard
  async init() {
    this.bindEvents();
    this.initTheme();
    await this.loadFilterOptions();
    this.loadDashboardData();
  }

  // Bind all event listeners
  bindEvents() {
    document.getElementById("theme-toggle").addEventListener("change", (e) => {
      document.body.classList.toggle("dark-mode", e.target.checked);
      localStorage.setItem("dashboardTheme", e.target.checked ? "dark" : "light");
    });
    
    document.getElementById("global-search").addEventListener('input', () => {
        this.applyGlobalSearch();
        this.renderAllComponents();
    });

    document.getElementById("modal-search").addEventListener('input', (e) => this.renderModalTable());
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") this.closeModal() });
    document.getElementById("filter-form").addEventListener('submit', (e) => e.preventDefault());
  }

  // Initialize theme from localStorage
  initTheme() {
    if (localStorage.getItem("dashboardTheme") === "dark") {
      document.body.classList.add("dark-mode");
      document.getElementById("theme-toggle").checked = true;
    }
  }

  // API call wrapper using frappe.call for simplicity and auth handling
  async apiCall(method, args = {}) {
    try {
      const response = await frappe.call({
        method: `ai_crm.api.lead_dashboard.${method}`, // <-- IMPORTANT: Verify this path
        args: args
      });
      if (response && response.message) {
        return response.message;
      }
      throw new Error("Invalid API response from server.");
    } catch (error) {
      console.error(`API call to ${method} failed:`, error);
      this.showError(error.message || "An unknown server error occurred.");
      throw error;
    }
  }
  
  // Show toast notification
  showToast(message, duration = 2200) {
    const toast = document.getElementById("custom-toast");
    toast.textContent = message;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), duration);
  }

  // UI state management
  showLoading() {
    document.getElementById("loading-container").style.display = "block";
    document.getElementById("dashboard-content").style.display = "none";
    document.getElementById("error-container").style.display = "none";
  }

  showError(message) {
    document.getElementById("error-container").style.display = "block";
    document.getElementById("error-message").textContent = message;
    document.getElementById("loading-container").style.display = "none";
    document.getElementById("dashboard-content").style.display = "none";
  }

  showContent() {
    document.getElementById("dashboard-content").style.display = "block";
    document.getElementById("loading-container").style.display = "none";
    document.getElementById("error-container").style.display = "none";
  }

  // Populate dropdowns with data
  populateDropdown(elementId, options, config = {}) {
    const select = document.getElementById(elementId);
    select.innerHTML = ""; // Clear existing

    if (config.hasAllOption) {
      const allOption = document.createElement("option");
      allOption.value = config.allValue || `All ${elementId.split('-')[0]}s`;
      allOption.textContent = allOption.value;
      select.appendChild(allOption);
    }
    
    options.forEach(opt => {
        const option = document.createElement("option");
        option.value = typeof opt === 'object' ? opt.value : opt;
        option.textContent = typeof opt === 'object' ? opt.label : opt;
        select.appendChild(option);
    });
  }

  // Load options for all filter dropdowns from the backend
  async loadFilterOptions() {
    try {
        const options = await this.apiCall('get_filter_options');
        this.populateDropdown("status-filter", ["All Statuses", ...options.status]);
        this.populateDropdown("source-filter", ["All Sources", ...options.source]);
        this.populateDropdown("industry-filter", options.industry, { hasAllOption: true, allValue: "All Industries" });
        this.populateDropdown("owner-filter", options.owner, { hasAllOption: true, allValue: "All Owners" });
    } catch (error) {
        this.showToast("Could not load filter options. Using defaults.", 3000);
    }
  }

  // Get current filter values from the form
  getFilterValues() {
    const getMulti = (id) => Array.from(document.getElementById(id).selectedOptions).map(o => o.value);
    
    return {
      fromDate: document.getElementById("from-date").value,
      toDate: document.getElementById("to-date").value,
      statusFilter: getMulti("status-filter"),
      sourceFilter: getMulti("source-filter"),
      ownerFilter: document.getElementById("owner-filter").value,
      industryFilter: document.getElementById("industry-filter").value
    };
  }

  // Load main dashboard data from the backend
  async loadDashboardData() {
    this.showLoading();
    try {
      const filters = this.getFilterValues();
      if (filters.fromDate && filters.toDate && filters.toDate < filters.fromDate) {
        this.showToast("End date cannot be before start date.", 3000);
        this.showContent(); // Show previous content
        return;
      }
      
      const data = await this.apiCall('get_dashboard_data', { filters: JSON.stringify(filters) });
      
      this.allLeads = data.leads;
      this.analytics = data.analytics;
      
      this.applyGlobalSearch();
      this.renderAllComponents();

      this.showContent();
      this.showToast("Dashboard updated successfully!");

    } catch (error) {
      // The error is already shown by apiCall, just need to hide loading
      document.getElementById("loading-container").style.display = "none";
    }
  }

  // Apply the global search input to filter the displayed leads
  applyGlobalSearch() {
    const searchTerm = document.getElementById("global-search").value.trim().toLowerCase();
    
    if (!searchTerm) {
        this.displayLeads = [...this.allLeads];
    } else {
        this.displayLeads = this.allLeads.filter(lead => 
            Object.values(lead).some(val => val && String(val).toLowerCase().includes(searchTerm))
        );
    }
  }

  // Render all visual components with the current data
  renderAllComponents() {
    if (this.displayLeads.length === 0 && document.getElementById("global-search").value) {
        // If search returns no results, show a message but keep analytics from before search
    } else {
        // Re-calculate analytics based on the globally searched subset
        const newAnalytics = _calculate_lead_analytics(this.displayLeads);
        this.renderSummaries(newAnalytics.summary);
        this.renderStatusTable(newAnalytics.by_status);
        this.renderOwnerGrid(newAnalytics.by_owner);
        this.renderSourceChart(newAnalytics.by_source);
    }
  }

  // RENDER METHODS
  renderSummaries(summary) {
    const html = `
      <div class="summary-card">
        <div class="icon total"><i class="fa-solid fa-layer-group"></i></div>
        <div><h5>Total Leads</h5><div class="count">${this.createClickableNumber(summary.total, {})}</div></div>
      </div>
      <div class="summary-card">
        <div class="icon open"><i class="fa-solid fa-folder-open"></i></div>
        <div><h5>Open Leads</h5><div class="count">${this.createClickableNumber(summary.open, { status: ["Lead", "Open", "Replied", "Interested"] })}</div></div>
      </div>
      <div class="summary-card">
        <div class="icon converted"><i class="fa-solid fa-circle-check"></i></div>
        <div><h5>Converted</h5><div class="count">${this.createClickableNumber(summary.converted, { status: "Converted" })}</div></div>
      </div>
      <div class="summary-card">
        <div class="icon lost"><i class="fa-solid fa-circle-xmark"></i></div>
        <div><h5>Lost</h5><div class="count">${this.createClickableNumber(summary.lost, { status: ["Do Not Contact", "Lost Quotation"] })}</div></div>
      </div>
    `;
    document.getElementById("overall-summary").innerHTML = html;
  }

  renderStatusTable(statuses) {
    const section = document.getElementById("status-summary-section");
    if (Object.keys(statuses).length === 0) {
      section.innerHTML = `<h4>By Status</h4><div class="empty-state">No data</div>`;
      return;
    }
    let tableHTML = `<h4>By Status</h4><table class="table table-striped"><thead><tr><th>Status</th><th class="text-right">Count</th></tr></thead><tbody>`;
    for (const [status, count] of Object.entries(statuses)) {
        tableHTML += `<tr><td>${status}</td><td class="text-right">${this.createClickableNumber(count, { status })}</td></tr>`;
    }
    section.innerHTML = tableHTML + "</tbody></table>";
  }

  renderOwnerGrid(owners) {
    const section = document.getElementById("owner-summary-section");
    if (owners.length === 0) {
      section.innerHTML = `<h4>By Lead Owner</h4><div class="empty-state">No data</div>`;
      return;
    }
    let html = `<h4>By Lead Owner</h4><div class="lead-owner-grid">`;
    owners.forEach(({ owner, total, converted, lost }) => {
      const initials = owner === "Unassigned" ? "?" : owner.split('@')[0].split(/[.\s_]/).map(w => w[0]?.toUpperCase()).join("").slice(0, 2) || "U";
      html += `
        <div class="owner-card">
          <div class="owner-avatar">${initials}</div>
          <div class="owner-name" title="${owner}">${owner}</div>
          <div class="owner-metrics">
            <span class="metric total">${this.createClickableNumber(total, { lead_owner: owner })} <small>Total</small></span>
            <span class="metric converted">${this.createClickableNumber(converted, { lead_owner: owner, status: "Converted" })} <small>Converted</small></span>
            <span class="metric lost">${this.createClickableNumber(lost, { lead_owner: owner, status: ["Do Not Contact", "Lost Quotation"] })} <small>Lost</small></span>
          </div>
        </div>`;
    });
    section.innerHTML = html + "</div>";
  }

  renderSourceChart(sources) {
    if (this.sourceChart) this.sourceChart.destroy();
    const ctx = document.getElementById("sourceChart").getContext("2d");
    this.sourceChart = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: Object.keys(sources),
        datasets: [{
          data: Object.values(sources),
          backgroundColor: ["#007bff", "#28a745", "#ffc107", "#dc3545", "#17a2b8", "#6610f2", "#fd7e14", "#6c757d"],
          borderWidth: 2,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: true, position: 'bottom', labels: { padding: 15, usePointStyle: true } } }
      }
    });
  }

  // MODAL LOGIC
  createClickableNumber(count, filter) {
    if (count === 0) return "0";
    return `<span class="clickable-number" tabindex="0" onclick='window.dashboard.showDetails(${JSON.stringify(filter)})'>${count}</span>`;
  }
  
  showDetails(filter) {
    this.modalFilter = filter; // Store the filter for the modal
    this.renderModalTable(); // Initial render
    document.getElementById("modal-title").textContent = `Lead Details`;
    this.displayActiveFiltersInModal();
    document.getElementById("records-modal").style.display = "flex";
    document.body.classList.add("modal-open");
    document.getElementById("modal-search").value = "";
  }

  displayActiveFiltersInModal() {
    const filters = this.getFilterValues();
    let filterHTML = "<strong>Dashboard Filters:</strong> ";
    if (filters.fromDate) filterHTML += `<span class="badge badge-secondary">From: ${filters.fromDate}</span>`;
    if (filters.toDate) filterHTML += `<span class="badge badge-secondary">To: ${filters.toDate}</span>`;
    document.getElementById("modal-filters-display").innerHTML = filterHTML;
  }

  renderModalTable() {
    // Filter records for the modal based on the drill-down filter and modal search
    let records = this.displayLeads.filter(lead => {
        let match = true;
        for (const [key, value] of Object.entries(this.modalFilter)) {
            if (Array.isArray(value)) match = match && value.includes(lead[key]);
            else match = match && lead[key] === value;
        }
        return match;
    });

    const searchTerm = document.getElementById("modal-search").value.toLowerCase();
    if (searchTerm) {
        records = records.filter(rec => Object.values(rec).some(val => String(val || "").toLowerCase().includes(searchTerm)));
    }
    document.getElementById("modal-title").textContent = `Lead Details (${records.length} Records)`;

    // Apply sorting
    if (this.currentSort.field) {
      records.sort((a, b) => {
        let valA = a[this.currentSort.field] || "";
        let valB = b[this.currentSort.field] || "";
        if (valA < valB) return this.currentSort.direction === "asc" ? -1 : 1;
        if (valA > valB) return this.currentSort.direction === "asc" ? 1 : -1;
        return 0;
      });
    }

    const headers = this.modalFields.map(f => ({ key: f, label: f.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) }));
    let tableHTML = `<table class="table table-bordered table-striped table-sm details-table"><thead><tr>`;
    headers.forEach(h => {
        const sortClass = h.key === this.currentSort.field ? `sortable sorted-${this.currentSort.direction}` : "sortable";
        tableHTML += `<th class="${sortClass}" onclick="window.dashboard.sortModalTable('${h.key}')">${h.label}</th>`;
    });
    tableHTML += `</tr></thead><tbody>`;

    if (records.length === 0) {
      tableHTML += `<tr><td colspan="${headers.length}" class="empty-state">No records found.</td></tr>`;
    } else {
      records.forEach(rec => {
        tableHTML += "<tr>";
        headers.forEach(h => {
          let value = rec[h.key] || "N/A";
          if (h.key === "name") {
            value = `<span class="lead-link" onclick="window.dashboard.navigateToLead('${rec.name}')">${rec.full_name || rec.name}</span>`;
          } else if (h.key === "creation" && value !== "N/A") {
            value = frappe.datetime.str_to_user(value);
          }
          tableHTML += `<td>${value}</td>`;
        });
        tableHTML += "</tr>";
      });
    }
    document.getElementById("modal-table-container").innerHTML = tableHTML + "</tbody></table>";
  }

  sortModalTable(field) {
    if (this.currentSort.field === field) {
      this.currentSort.direction = this.currentSort.direction === "asc" ? "desc" : "asc";
    } else {
      this.currentSort = { field, direction: "asc" };
    }
    this.renderModalTable();
  }

  navigateToLead(leadName) {
    frappe.set_route("Form", "Lead", leadName);
  }

  closeModal() {
    document.getElementById("records-modal").style.display = "none";
    document.body.classList.remove("modal-open");
  }
}

// Re-calculation function to be used for client-side global search
function _calculate_lead_analytics(leads) {
    const summary = { total: leads.length, open: 0, converted: 0, lost: 0 };
    const by_status = {};
    const by_source = {};
    const owner_stats = {};
    const open_statuses = {"Lead", "Open", "Replied", "Interested"};
    const lost_statuses = {"Do Not Contact", "Lost Quotation"};

    for (const lead of leads) {
        const status = lead.status || "Uncategorized";
        const source = lead.source || "Unknown";
        const owner = lead.lead_owner || "Unassigned";

        if (status === "Converted") summary.converted++;
        else if (open_statuses.has(status)) summary.open++;
        else if (lost_statuses.has(status)) summary.lost++;

        by_status[status] = (by_status[status] || 0) + 1;
        by_source[source] = (by_source[source] || 0) + 1;

        if (!owner_stats[owner]) owner_stats[owner] = { total: 0, converted: 0, lost: 0 };
        owner_stats[owner].total++;
        if (status === "Converted") owner_stats[owner].converted++;
        else if (lost_statuses.has(status)) owner_stats[owner].lost++;
    }

    const by_owner = Object.entries(owner_stats).map(([owner, stats]) => ({ owner, ...stats }))
                           .sort((a, b) => b.total - a.total);

    return { summary, by_status, by_source, by_owner };
}


// Initialize dashboard when Frappe page script is loaded
frappe.pages['lead-dashboard'].on_page_load = function(wrapper) {
	window.dashboard = new LeadDashboard();
};