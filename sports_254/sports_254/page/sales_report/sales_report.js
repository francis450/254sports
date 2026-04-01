frappe.pages["sales-report"].on_page_load = function (wrapper) {
  var page = frappe.ui.make_app_page({
    parent: wrapper,
    title: "Sales Report",
    single_column: true,
  });

  page.body.html(`
<div class="sr-root">

  <header class="sr-header">
    <div class="sr-header-brand">
      <span class="sr-wordmark">254 SPORTS</span>
      <span class="sr-tagline">Sales Report</span>
    </div>
  </header>

  <div class="sr-filters-bar">

    <div class="sr-filter-group">
      <label class="sr-label">From</label>
      <input type="date" id="sr-from-date" class="sr-input" />
    </div>

    <div class="sr-filter-group">
      <label class="sr-label">To</label>
      <input type="date" id="sr-to-date" class="sr-input" />
    </div>

    <div class="sr-filter-group">
      <label class="sr-label">Status</label>
      <div class="sr-status-tabs" id="sr-status-tabs">
        <button class="sr-tab active" data-status="All">All</button>
        <button class="sr-tab" data-status="Paid">Paid</button>
        <button class="sr-tab" data-status="Credit">Credit</button>
      </div>
    </div>

    <div class="sr-filter-group">
      <label class="sr-label">Customer</label>
      <input type="text" id="sr-customer" class="sr-input" placeholder="Any customer…" autocomplete="off" />
    </div>

    <div class="sr-filter-group">
      <label class="sr-label">Item</label>
      <input type="text" id="sr-item" class="sr-input" placeholder="Any item…" autocomplete="off" />
    </div>

    <div class="sr-filter-group">
      <label class="sr-label">Category</label>
      <select id="sr-item-group" class="sr-input sr-select">
        <option value="">All Categories</option>
      </select>
    </div>

    <div class="sr-filter-group">
      <label class="sr-label">Warehouse</label>
      <select id="sr-warehouse" class="sr-input sr-select">
        <option value="">All Warehouses</option>
      </select>
    </div>

    <div class="sr-filter-group sr-filter-run">
      <button class="sr-run-btn" id="sr-run">Run Report</button>
    </div>

  </div>

  <div class="sr-body" id="sr-body">
    <div class="sr-empty-state">Set filters above and click <strong>Run Report</strong>.</div>
  </div>

</div>
  `);

  new SalesReportPage(page, wrapper);
};

// ─────────────────────────────────────────────────────────────────────────────
class SalesReportPage {
  constructor(page, wrapper) {
    this.page = page;
    this.wrapper = wrapper;
    this.paymentStatus = "All";
    this._init();
  }

  async _init() {
    this._setDefaultDates();
    this._bindStatusTabs();
    this._bindRun();
    await Promise.all([this._loadWarehouses(), this._loadItemGroups()]);
    this._run();
  }

  // ── Defaults ───────────────────────────────────────────────────────────────
  _setDefaultDates() {
    const today = frappe.datetime.get_today();
    const firstOfMonth = today.substring(0, 7) + "-01";
    $("#sr-from-date").val(firstOfMonth);
    $("#sr-to-date").val(today);
  }

  // ── Dropdowns ──────────────────────────────────────────────────────────────
  async _loadWarehouses() {
    const data = await frappe.call({ method: "sports_254.api.get_warehouses" });
    const warehouses = (data && data.message) || [];
    const $sel = $("#sr-warehouse");
    warehouses.forEach((w) => {
      $sel.append(`<option value="${frappe.utils.escape_html(w.name)}">${frappe.utils.escape_html(w.warehouse_name)}</option>`);
    });
  }

  async _loadItemGroups() {
    const data = await frappe.call({ method: "sports_254.api.get_item_groups" });
    const groups = (data && data.message) || [];
    const $sel = $("#sr-item-group");
    groups.forEach((g) => {
      $sel.append(`<option value="${frappe.utils.escape_html(g.name)}">${frappe.utils.escape_html(g.name)}</option>`);
    });
  }

  // ── Status tabs ────────────────────────────────────────────────────────────
  _bindStatusTabs() {
    const self = this;
    $("#sr-status-tabs").on("click", ".sr-tab", function () {
      $(".sr-tab").removeClass("active");
      $(this).addClass("active");
      self.paymentStatus = $(this).data("status");
    });
  }

  // ── Run ────────────────────────────────────────────────────────────────────
  _bindRun() {
    $("#sr-run").on("click", () => this._run());
  }

  async _run() {
    const fromDate = $("#sr-from-date").val();
    const toDate = $("#sr-to-date").val();
    if (!fromDate || !toDate) {
      frappe.msgprint({ title: "Missing Dates", message: "Please set both From and To dates.", indicator: "red" });
      return;
    }

    const $btn = $("#sr-run").prop("disabled", true).text("Loading…");
    $("#sr-body").html('<div class="sr-loading">Fetching data…</div>');

    try {
      const result = await frappe.call({
        method: "sports_254.api.get_sales_report",
        args: {
          from_date: fromDate,
          to_date: toDate,
          payment_status: this.paymentStatus,
          customer: $("#sr-customer").val().trim(),
          item_code: $("#sr-item").val().trim(),
          item_group: $("#sr-item-group").val(),
          warehouse: $("#sr-warehouse").val(),
        },
      });
      if (result && result.message) {
        this._render(result.message);
      }
    } finally {
      $btn.prop("disabled", false).text("Run Report");
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  _render(data) {
    const { invoices, summary, credit_customers } = data;
    const $body = $("#sr-body").empty();

    // Summary cards
    $body.append(`
      <div class="sr-summary-row">
        <div class="sr-summary-card">
          <div class="sr-summary-label">Total Sales</div>
          <div class="sr-summary-value">${this._fmt(summary.total_sales)}</div>
          <div class="sr-summary-sub">${summary.invoice_count} invoice${summary.invoice_count !== 1 ? "s" : ""}</div>
        </div>
        <div class="sr-summary-card sr-summary-paid">
          <div class="sr-summary-label">Total Paid</div>
          <div class="sr-summary-value">${this._fmt(summary.total_paid)}</div>
          <div class="sr-summary-sub">${summary.invoice_count - summary.credit_count} paid</div>
        </div>
        <div class="sr-summary-card sr-summary-credit">
          <div class="sr-summary-label">Outstanding Credit</div>
          <div class="sr-summary-value">${this._fmt(summary.total_outstanding)}</div>
          <div class="sr-summary-sub">${summary.credit_count} on credit</div>
        </div>
      </div>
    `);

    // Credit customers section
    if (credit_customers && credit_customers.length && this.paymentStatus !== "Paid") {
      const $section = $('<div class="sr-section"></div>');
      $section.append('<div class="sr-section-title">Credit Customers — Who Owes What</div>');
      const $table = $(`
        <table class="sr-table">
          <thead>
            <tr>
              <th>Customer</th>
              <th class="sr-num">Amount Owed</th>
              <th class="sr-num">Invoices</th>
              <th>Oldest Invoice</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      `);
      const $tbody = $table.find("tbody");
      credit_customers.forEach((c) => {
        $(`<tr class="sr-credit-row" title="Click to filter by this customer">
            <td><strong>${frappe.utils.escape_html(c.customer)}</strong></td>
            <td class="sr-num sr-amount-owed">${this._fmt(c.total_outstanding)}</td>
            <td class="sr-num">${c.invoice_count}</td>
            <td>${frappe.utils.escape_html(c.oldest_date || "")}</td>
           </tr>`)
          .on("click", () => {
            $("#sr-customer").val(c.customer);
            $(".sr-tab").removeClass("active");
            $(".sr-tab[data-status='Credit']").addClass("active");
            this.paymentStatus = "Credit";
            this._run();
          })
          .appendTo($tbody);
      });
      $section.append($table);
      $body.append($section);
    }

    // Invoices table
    const $section2 = $('<div class="sr-section"></div>');
    const rangeLabel = `${$("#sr-from-date").val()} → ${$("#sr-to-date").val()}`;
    $section2.append(`<div class="sr-section-title">Invoices &mdash; ${frappe.utils.escape_html(rangeLabel)}</div>`);

    if (!invoices || !invoices.length) {
      $section2.append('<div class="sr-empty-state">No invoices match your filters.</div>');
    } else {
      const $table = $(`
        <table class="sr-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Invoice</th>
              <th>Customer</th>
              <th>Items</th>
              <th class="sr-num">Amount</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      `);
      const $tbody = $table.find("tbody");
      invoices.forEach((inv) => {
        const isPaid = inv.outstanding_amount === 0 || parseFloat(inv.outstanding_amount) === 0;
        const badge = isPaid
          ? '<span class="sr-badge sr-badge-paid">Paid</span>'
          : '<span class="sr-badge sr-badge-credit">Credit</span>';
        const time = (inv.posting_time || "").substring(0, 5);
        $(`<tr class="sr-invoice-row" title="Open invoice">
            <td>${frappe.utils.escape_html(inv.posting_date)}<span class="sr-time"> ${time}</span></td>
            <td class="sr-invoice-name">${frappe.utils.escape_html(inv.name)}</td>
            <td>${frappe.utils.escape_html(inv.customer || "")}</td>
            <td class="sr-items-cell">${frappe.utils.escape_html(inv.items_summary || "")}</td>
            <td class="sr-num">${this._fmt(inv.grand_total)}</td>
            <td>${badge}</td>
           </tr>`)
          .on("click", function () {
            frappe.set_route("Form", "Sales Invoice", inv.name);
          })
          .appendTo($tbody);
      });
      $section2.append($table);
    }
    $body.append($section2);
  }

  _fmt(val) {
    return "KES " + format_number(val || 0, null, 2);
  }
}
