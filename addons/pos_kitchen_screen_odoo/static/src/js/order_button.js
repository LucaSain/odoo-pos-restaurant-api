/** @odoo-module */
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
  async setup(env, options) {
    await super.setup(env, options);
    this.orm = this.env.services.orm;
    // Keep a reference to bus_service (if available)
    try {
      this.bus = this.env.services.bus_service;
      const posId = this.config && this.config.id;
      if (this.bus && posId) {
        this._kitchenChannel = `kitchen-${posId}`;
        this.bus.addChannel(this._kitchenChannel);

        // handler receives notification messages forwarded by the server
        this._busHandler = (message) => {
          try {
            const data = message.data || message;
            const notification_sender = data.from;
            if (data.from == "waiter") return;
            // show notifications received via bus
            this._showNotification(data, { type: "info", sticky: true });
          } catch (err) {
            // swallow errors to avoid breaking POS
            // eslint-disable-next-line no-console
            console.warn("bus handler error", err);
          }
        };

        // subscribe for bus notifications (notification channel)
        this.bus.subscribe(`notification`, this._busHandler);
        console.log("subscribed test");
      }
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn("Failed to initialize bus subscription", e);
    }
  },

  async sendOrderInPreparation(order) {
    await super.sendOrderInPreparation(...arguments);
    console.log(order);
    const orderData = {
      from: "waiter",
      config_id: this.config.id,
      pos_reference: order.pos_reference,
      date_order: order.date_order,
      table: order.table_id.table_number || "",
      floor: order.table_id.floor_id.name || "",
      state: order.state,
      lines: order.lines.map((line) => ({
        product_id: line.product_id.id,
        product_name: line.product_id.name,
        qty: line.qty,
        price_unit: line.price_unit,
        price_subtotal: line.price_subtotal,
        price_subtotal_incl: line.price_subtotal_incl,
        discount: line.discount,
        note: line.note || "",
      })),
    };
    console.log(this.config.id);
    const status = await this.orm.call("pos.order", "broadcast_order_update", [
      `waiter-${this.config.id}`,
      orderData,
    ]);
    console.log(status);
    return;
    // Try to persist a status update (safe non-blocking)
    try {
      const rpc = this.rpc || this.env.services.rpc;
      if (rpc && order && order.id) {
        // set to 'draft' (Cooking) when sending to kitchen — change as desired
        await rpc({
          model: "pos.order",
          method: "update_order_status",
          args: [order.id, "draft"],
        });
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("Failed to update order status via RPC", err);
    }
  },

  _showNotification(message, options = {}) {
    // Safe, minimal notification helper
    try {
      const finalMessage =
        typeof message === "object"
          ? message.message || message.text || JSON.stringify(message)
          : message;

      if (this.env && this.env.services && this.env.services.notification) {
        this.env.services.notification.add(finalMessage, options);
      } else {
        // fallback
        // eslint-disable-next-line no-console
        console.log("Kitchen Notification:", finalMessage);
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("Failed to show notification:", err);
    }
  },

  async _onWillUnload() {
    // cleanup bus subscription and channel
    try {
      if (this.bus && this._busHandler) {
        this.bus.unsubscribe("notification", this._busHandler);
      }
      if (this.bus && this._kitchenChannel) {
        this.bus.deleteChannel(this._kitchenChannel);
      }
    } catch (e) {
      // ignore cleanup errors
    }
    await super._onWillUnload?.();
  },
});
