/** @odoo-module */
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

patch(PosStore.prototype, {
  async sendOrderInPreparation(order, cancelled = false) {
    // 1) Run the original logic (printing, state updates, etc.)
    await super.sendOrderInPreparation(order, cancelled);

    // 2) If the POS‐config toggle is on, serialize & POST to external API
    const cfg = this.config;
    if (!cfg.api_enabled) {
      return;
    }

    // Build your payload
    const payload = {
      pos_reference: order.pos_reference,
      date_order: order.date_order,
      state: order.state,
      lines: order.lines.map((line) => ({
        product_id: line.product_id.id,
        product_name: line.product_id.name,
        qty: line.qty,
        price_unit: line.price_unit,
        price_subtotal: line.price_subtotal,
        price_subtotal_incl: line.price_subtotal_incl,
        discount: line.discount,
        note: line.note || '',
      })),
    };

    // Send it off
    try {
      const response = await fetch(cfg.api_endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Status ${response.status}: ${text}`);
      }

      this.env.services.notification.add(
        _t("Order sent to external API: %s", order.pos_reference),
        { type: "success" }
      );
    } catch (e) {
      console.error("Error sending POS order to external API:", e);
      this.env.services.notification.add(
        _t("Error sending order to external API: %s", e.message),
        { type: "danger" }
      );
    }
  },
});