frappe.pages["quick-sale"].on_page_load = function (wrapper) {
  var page = frappe.ui.make_app_page({
    parent: wrapper,
    title: "Quick Sale",
    single_column: true,
  });

  // Inline HTML — avoids dependency on compiled template bundle
  page.body.html(`
<div class="qs-root">

  <header class="qs-header">
    <div class="qs-header-brand">
      <span class="qs-wordmark">254 SPORTS</span>
      <span class="qs-tagline">Born Kenyan, Born to Run</span>
    </div>
    <div class="qs-warehouse-toggle" id="qs-warehouse-toggle"></div>
  </header>

  <div class="qs-layout">

    <section class="qs-form-panel">
      <div class="qs-card">
        <div class="qs-card-header qs-diagonal-band"><span>New Sale</span></div>
        <div class="qs-card-body">

          <div class="qs-field-group">
            <label class="qs-label" for="qs-customer">Customer Name</label>
            <input type="text" id="qs-customer" class="qs-input"
              placeholder="Leave blank for Walk-in Customer" autocomplete="off" />
          </div>

          <div class="qs-field-group">
            <label class="qs-label">Items</label>
            <div id="qs-items-table"></div>
            <button class="qs-btn-add-item" id="qs-add-item">+ Add Item</button>
          </div>

          <div class="qs-field-group">
            <label class="qs-label">Payment Mode</label>
            <div class="qs-payment-grid" id="qs-payment-grid">
              <button class="qs-pay-tile active" data-mode="Cash">
                <span class="qs-pay-icon">💵</span>
                <span class="qs-pay-label">Cash</span>
              </button>
              <button class="qs-pay-tile" data-mode="M-Pesa">
                <span class="qs-pay-icon">📱</span>
                <span class="qs-pay-label">M-Pesa</span>
              </button>
              <button class="qs-pay-tile" data-mode="Bank Transfer">
                <span class="qs-pay-icon">🏦</span>
                <span class="qs-pay-label">Bank</span>
              </button>
              <button class="qs-pay-tile qs-pay-credit" data-mode="Credit">
                <span class="qs-pay-icon">📋</span>
                <span class="qs-pay-label">Credit</span>
              </button>
            </div>
            <p class="qs-credit-note" id="qs-credit-note" style="display:none;">
              Invoice will remain outstanding in Accounts Receivable.
            </p>
          </div>

          <div class="qs-total-bar">
            <span class="qs-total-label">TOTAL</span>
            <span class="qs-total-amount" id="qs-total">KES 0.00</span>
          </div>

          <button class="qs-submit-btn" id="qs-submit">Record &amp; Mark Paid</button>

        </div>
      </div>
    </section>

    <section class="qs-feed-panel">
      <div class="qs-feed-header">
        <div class="qs-feed-header-top">
          <div class="qs-feed-title" id="qs-feed-title">Today's Sales</div>
          <div class="qs-feed-daily-total" id="qs-daily-total">KES 0.00</div>
        </div>
        <div class="qs-feed-period-tabs" id="qs-feed-period-tabs">
          <button class="qs-period-tab active" data-period="today">Today</button>
          <button class="qs-period-tab" data-period="week">This Week</button>
          <button class="qs-period-tab" data-period="month">This Month</button>
        </div>
      </div>
      <div class="qs-feed-list" id="qs-feed-list">
        <div class="qs-feed-empty">No sales recorded today.</div>
      </div>
    </section>

  </div>
</div>
  `);

  new QuickSalePage(page, wrapper);
};

// ─────────────────────────────────────────────────────────────────────────────
class QuickSalePage {
  constructor(page, wrapper) {
    this.page = page;
    this.wrapper = wrapper;
    this.warehouses = [];
    this.selectedWarehouse = null;
    this.paymentMode = "Cash";
    this.feedPeriod = "today";
    this.items = [];
    this._init();
  }

  async _init() {
    await this._loadWarehouses();
    this._bindPaymentTiles();
    this._bindAddItem();
    this._bindSubmit();
    this._bindFeedPeriodTabs();
    this._addItemRow();
    this._refreshFeed();
  }

  // ── Warehouses ─────────────────────────────────────────────────────────────
  async _loadWarehouses() {
    const data = await frappe.call({ method: "sports_254.api.get_warehouses" });
    this.warehouses = (data && data.message) || [];
    // Only restore a warehouse the user explicitly chose before — never auto-select.
    const saved = localStorage.getItem("qs_warehouse");
    this.selectedWarehouse =
      (saved && this.warehouses.find((w) => w.name === saved)) ? saved : null;
    this._renderWarehouseToggle();
  }

  _renderWarehouseToggle() {
    const $toggle = $("#qs-warehouse-toggle").empty();
    this.warehouses.forEach((w) => {
      const active = w.name === this.selectedWarehouse ? "active" : "";
      $(`<button class="qs-wh-pill ${active}" data-wh="${w.name}">${frappe.utils.escape_html(w.warehouse_name)}</button>`)
        .on("click", (e) => {
          this.selectedWarehouse = $(e.currentTarget).data("wh");
          localStorage.setItem("qs_warehouse", this.selectedWarehouse);
          this._renderWarehouseToggle();
          this._refreshFeed();
          this._refreshAllItemStock();
        })
        .appendTo($toggle);
    });
    this._updateFormState();
  }

  // ── Feed period tabs ───────────────────────────────────────────────────────
  _bindFeedPeriodTabs() {
    const self = this;
    const titles = {
      today: "Today's Sales",
      week: "This Week's Sales",
      month: "This Month's Sales",
    };
    $("#qs-feed-period-tabs").on("click", ".qs-period-tab", function () {
      $(".qs-period-tab").removeClass("active");
      $(this).addClass("active");
      self.feedPeriod = $(this).data("period");
      $("#qs-feed-title").text(titles[self.feedPeriod]);
      self._refreshFeed();
    });
  }

  _updateFormState() {
    const ready = !!this.selectedWarehouse;
    // Disable submit until a warehouse is intentionally chosen.
    $("#qs-submit").prop("disabled", !ready).toggleClass("qs-submit-disabled", !ready);
    // Show/hide the warehouse prompt banner inside the header.
    if (!ready) {
      if (!$("#qs-wh-required").length) {
        $('<div class="qs-wh-required" id="qs-wh-required">Select a store above before recording a sale.</div>')
          .appendTo(".qs-header");
      }
      $("#qs-feed-list").html('<div class="qs-feed-empty">Select a store to view today\'s sales.</div>');
      $("#qs-daily-total").text("KES 0.00");
    } else {
      $("#qs-wh-required").remove();
    }
  }

  // ── Payment tiles ──────────────────────────────────────────────────────────
  _bindPaymentTiles() {
    const self = this;
    $("#qs-payment-grid").on("click", ".qs-pay-tile", function () {
      $(".qs-pay-tile").removeClass("active");
      $(this).addClass("active");
      self.paymentMode = $(this).data("mode");
      self._updateSubmitLabel();
      $("#qs-credit-note").toggle(self.paymentMode === "Credit");
    });
  }

  _updateSubmitLabel() {
    $("#qs-submit").text(
      this.paymentMode === "Credit" ? "Record Credit Sale" : "Record & Mark Paid"
    );
  }

  // ── Item rows ──────────────────────────────────────────────────────────────
  _bindAddItem() {
    $("#qs-add-item").on("click", () => this._addItemRow());
  }

  _addItemRow() {
    const idx = this.items.length;
    this.items.push({ item_code: null, item_name: "", qty: 1, rate: 0, actual_qty: 0 });

    const $row = $(`
      <div class="qs-item-row" data-idx="${idx}">
        <div class="qs-item-search-col">
          <input type="text" class="qs-input qs-item-search" placeholder="Search item…" autocomplete="off" />
          <div class="qs-item-stock-badge" style="display:none;"></div>
          <div class="qs-item-dropdown" style="display:none;"></div>
        </div>
        <div class="qs-item-controls-row">
          <div class="qs-item-qty-col">
            <span class="qs-sublabel">Qty</span>
            <input type="number" class="qs-input qs-item-qty" value="1" min="1" step="1" />
          </div>
          <div class="qs-item-rate-col">
            <span class="qs-sublabel">Rate (KES)</span>
            <input type="number" class="qs-input qs-item-rate" value="0" min="0" step="0.01" />
          </div>
          <div class="qs-item-del-col">
            <button class="qs-btn-del-item" title="Remove">✕</button>
          </div>
        </div>
      </div>
    `);

    this._bindItemRowEvents($row, idx);
    $("#qs-items-table").append($row);
    this._updateTotal();
  }

  _bindItemRowEvents($row, idx) {
    const self = this;
    let searchTimer = null;

    $row.find(".qs-item-search").on("input", function () {
      const q = $(this).val().trim();
      clearTimeout(searchTimer);
      const $dd = $row.find(".qs-item-dropdown");
      if (q.length < 2) { $dd.hide().empty(); return; }
      searchTimer = setTimeout(() => self._doItemSearch(q, $row, idx), 300);
    });

    $row.find(".qs-item-qty").on("input", () => {
      self.items[idx].qty = parseFloat($row.find(".qs-item-qty").val()) || 0;
      self._updateTotal();
    });

    $row.find(".qs-item-rate").on("input", () => {
      self.items[idx].rate = parseFloat($row.find(".qs-item-rate").val()) || 0;
      self._updateTotal();
    });

    $row.find(".qs-btn-del-item").on("click", () => {
      if (self.items.length === 1) {
        self.items[0] = { item_code: null, item_name: "", qty: 1, rate: 0, actual_qty: 0 };
        $row.find(".qs-item-search").val("");
        $row.find(".qs-item-qty").val(1);
        $row.find(".qs-item-rate").val(0);
        $row.find(".qs-item-stock-badge").hide();
      } else {
        $row.remove();
        self.items.splice(idx, 1);
        $("#qs-items-table .qs-item-row").each(function (i) { $(this).attr("data-idx", i); });
      }
      self._updateTotal();
    });

    // Close dropdown on outside click
    $(document).off("click.qs-dropdown-" + idx).on("click.qs-dropdown-" + idx, function (e) {
      if (!$(e.target).closest(".qs-item-search-col").length) {
        $row.find(".qs-item-dropdown").hide().empty();
      }
    });
  }

  async _doItemSearch(q, $row, idx) {
    if (!this.selectedWarehouse) return;
    const data = await frappe.call({
      method: "sports_254.api.search_items",
      args: { query: q, warehouse: this.selectedWarehouse },
    });
    const results = (data && data.message) || [];
    const $dd = $row.find(".qs-item-dropdown").empty().show();

    if (!results.length) {
      $dd.html('<div class="qs-dd-empty">No items found</div>');
      return;
    }

    results.forEach((item) => {
      const stockCls = item.actual_qty > 0 ? "qs-stock-ok" : "qs-stock-none";
      $(`<div class="qs-dd-item">
          <span class="qs-dd-name">${frappe.utils.escape_html(item.item_name)}</span>
          <span class="qs-dd-stock ${stockCls}">${item.actual_qty} ${item.stock_uom || ""}</span>
         </div>`)
        .on("click", () => {
          this.items[idx] = {
            item_code: item.item_code,
            item_name: item.item_name,
            qty: parseFloat($row.find(".qs-item-qty").val()) || 1,
            rate: item.standard_rate || 0,
            actual_qty: item.actual_qty,
            stock_uom: item.stock_uom,
          };
          $row.find(".qs-item-search").val(item.item_name);
          $row.find(".qs-item-rate").val(item.standard_rate || 0);
          $row.find(".qs-item-stock-badge")
            .text(`Stock: ${item.actual_qty} ${item.stock_uom || ""}`)
            .removeClass("qs-stock-ok qs-stock-none").addClass(stockCls).show();
          $dd.hide().empty();
          this._updateTotal();
        })
        .appendTo($dd);
    });
  }

  async _refreshAllItemStock() {
    for (let idx = 0; idx < this.items.length; idx++) {
      const item = this.items[idx];
      if (!item.item_code) continue;
      const data = await frappe.call({
        method: "sports_254.api.search_items",
        args: { query: item.item_code, warehouse: this.selectedWarehouse },
      });
      const match = ((data && data.message) || []).find((r) => r.item_code === item.item_code);
      if (match) {
        item.actual_qty = match.actual_qty;
        const stockCls = match.actual_qty > 0 ? "qs-stock-ok" : "qs-stock-none";
        $(`#qs-items-table .qs-item-row[data-idx="${idx}"] .qs-item-stock-badge`)
          .text(`Stock: ${match.actual_qty} ${match.stock_uom || ""}`)
          .removeClass("qs-stock-ok qs-stock-none").addClass(stockCls).show();
      }
    }
  }

  // ── Total ──────────────────────────────────────────────────────────────────
  _updateTotal() {
    const total = this.items.reduce((s, r) => s + (r.qty || 0) * (r.rate || 0), 0);
    $("#qs-total").text("KES " + format_number(total, null, 2));
  }

  // ── Submit ─────────────────────────────────────────────────────────────────
  _bindSubmit() {
    $("#qs-submit").on("click", () => this._doSubmit());
  }

  async _doSubmit() {
    const validItems = this.items.filter((r) => r.item_code && r.qty > 0);
    if (!validItems.length) {
      frappe.msgprint({ title: "Incomplete", message: "Add at least one item.", indicator: "red" });
      return;
    }
    if (!this.selectedWarehouse) {
      frappe.msgprint({ title: "No Warehouse", message: "Select a warehouse first.", indicator: "red" });
      return;
    }

    const $btn = $("#qs-submit").prop("disabled", true).text("Processing…");
    try {
      const result = await frappe.call({
        method: "sports_254.api.submit_quick_sale",
        args: {
          customer_name: $("#qs-customer").val().trim(),
          warehouse: this.selectedWarehouse,
          items: JSON.stringify(validItems.map((r) => ({
            item_code: r.item_code, qty: r.qty, rate: r.rate,
          }))),
          payment_mode: this.paymentMode,
        },
      });
      if (result && result.message) {
        const { invoice, total, status } = result.message;
        frappe.show_alert({
          message: `✓ ${invoice} — KES ${format_number(total, null, 2)} (${status})`,
          indicator: "green",
        }, 6);
        this._resetForm();
        this._refreshFeed();
      }
    } finally {
      $btn.prop("disabled", false);
      this._updateSubmitLabel();
    }
  }

  _resetForm() {
    $("#qs-customer").val("");
    this.items = [];
    $("#qs-items-table").empty();
    this._addItemRow();
    this.paymentMode = "Cash";
    $(".qs-pay-tile").removeClass("active");
    $(".qs-pay-tile[data-mode='Cash']").addClass("active");
    $("#qs-credit-note").hide();
    this._updateSubmitLabel();
    this._updateTotal();
  }

  // ── Feed ───────────────────────────────────────────────────────────────────
  async _refreshFeed() {
    if (!this.selectedWarehouse) return;
    const data = await frappe.call({
      method: "sports_254.api.get_period_sales",
      args: { warehouse: this.selectedWarehouse, period: this.feedPeriod },
    });
    this._renderFeed((data && data.message) || []);
  }

  _renderFeed(invoices) {
    const self = this;
    const $list = $("#qs-feed-list").empty();
    if (!invoices.length) {
      $list.html('<div class="qs-feed-empty">No sales recorded today.</div>');
      $("#qs-daily-total").text("KES 0.00");
      return;
    }
    let dayTotal = 0;
    invoices.forEach((inv) => {
      dayTotal += inv.grand_total || 0;
      const isPaid = (inv.outstanding_amount || 0) === 0;
      const badge = isPaid
        ? '<span class="qs-badge qs-badge-paid">Paid</span>'
        : '<span class="qs-badge qs-badge-credit">Credit</span>';
      const hhmm = (inv.posting_time || "").substring(0, 5);
      // For week/month views show the date so multi-day rows are distinguishable.
      const time = this.feedPeriod === "today"
        ? hhmm
        : `${(inv.posting_date || "").substring(5).replace("-", "/")} ${hhmm}`;
      const markPaidBtn = !isPaid
        ? `<button class="qs-mark-paid-btn" data-invoice="${frappe.utils.escape_html(inv.name)}"
              data-customer="${frappe.utils.escape_html(inv.customer)}"
              data-amount="${inv.outstanding_amount}"
              title="Record payment for this invoice">Mark Paid</button>`
        : "";
      const $row = $(`<div class="qs-feed-row" data-invoice="${frappe.utils.escape_html(inv.name)}">
          <div class="qs-feed-row-left">
            <div class="qs-feed-customer">${frappe.utils.escape_html(inv.customer)}</div>
            <div class="qs-feed-items">${frappe.utils.escape_html(inv.items_summary || "")}</div>
          </div>
          <div class="qs-feed-row-right">
            <div class="qs-feed-amount">KES ${format_number(inv.grand_total, null, 2)}</div>
            <div class="qs-feed-meta">${time} ${badge}</div>
            ${markPaidBtn}
          </div>
         </div>`);

      $row.find(".qs-mark-paid-btn").on("click", function (e) {
        e.stopPropagation();
        self._showMarkPaidDialog(
          $(this).data("invoice"),
          $(this).data("customer"),
          parseFloat($(this).data("amount"))
        );
      });

      $row.on("click", function () {
        frappe.set_route("Form", "Sales Invoice", $(this).data("invoice"));
      });

      $row.appendTo($list);
    });
    $("#qs-daily-total").text("KES " + format_number(dayTotal, null, 2));
  }

  // ── Mark credit invoice as paid ────────────────────────────────────────────
  _showMarkPaidDialog(invoiceName, customer, outstandingAmount) {
    const self = this;
    frappe.prompt(
      [
        {
          fieldtype: "Select",
          fieldname: "payment_mode",
          label: "Payment Mode",
          options: "Cash\nM-Pesa\nBank Transfer",
          default: "Cash",
          reqd: 1,
        },
      ],
      (values) => {
        self._doMarkPaid(invoiceName, values.payment_mode);
      },
      `Mark Paid — ${customer}`,
      `Confirm KES ${format_number(outstandingAmount, null, 2)}`
    );
  }

  async _doMarkPaid(invoiceName, paymentMode) {
    try {
      const result = await frappe.call({
        method: "sports_254.api.mark_invoice_paid",
        args: { invoice_name: invoiceName, payment_mode: paymentMode },
      });
      if (result && result.message) {
        frappe.show_alert(
          { message: `✓ ${invoiceName} marked as paid`, indicator: "green" },
          5
        );
        this._refreshFeed();
      }
    } catch (_) {
      // frappe.call displays the server error automatically
    }
  }
}
