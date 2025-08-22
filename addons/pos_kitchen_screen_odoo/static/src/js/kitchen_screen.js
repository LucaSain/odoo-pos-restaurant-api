/** @odoo-module */
import { registry } from "@web/core/registry";
const { Component, onMounted, onWillUnmount, useState } = owl;
import { useService } from "@web/core/utils/hooks";

class KitchenScreenDashboard extends Component {
  setup() {
    super.setup();

    // Services
    this.orm = useService("orm");
    this.busService = useService("bus_service"); // your environment's bus wrapper
    // For RPC fallback (if needed)
    this.rpcService = this.env.services.rpc;

    // Derived values
    this.currentShopId = this.getCurrentShopId();
    this.channel = `waiter-${this.currentShopId}`;

    // component state (kept minimal)
    this.state = useState({
      orders: [],
      lines: [],
      stage: "draft",
      draft_count: 0,
      waiting_count: 0,
      ready_count: 0,
      isLoading: false,
      shop_id: this.currentShopId,
    });

    console.log(this.currentShopId, this.state);

    this._onNotification = this._onNotification.bind(this);

    onMounted(() => {
      // subscribe to bus
      try {
        if (this.busService) {
          this.busService.addChannel(this.channel);
          this.busService.subscribe(`notification`, this._onNotification);
          console.log("subscribed", this.state.shop_id);
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn("Failed to subscribe to bus", err);
      }
    });

    onWillUnmount(() => {
      // cleanup
      try {
        if (this.busService) {
          this.busService.unsubscribe("notification", this._onNotification);
          this.busService.deleteChannel(this.channel);
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn("Failed to cleanup bus subscription", err);
      }
    });
  }

  draft_stage(ev) {
    this.state.stage = "draft";
  }

  ready_stage(ev) {
    this.state.stage = "completed";
  }
  getCurrentShopId() {
    // same logic you used earlier
    let session_shop_id;
    if (this.props.action?.context?.default_shop_id) {
      sessionStorage.setItem(
        "shop_id",
        this.props.action.context.default_shop_id
      );
      session_shop_id = this.props.action.context.default_shop_id;
    } else {
      session_shop_id = sessionStorage.getItem("shop_id");
    }
    return parseInt(session_shop_id, 10) || 0;
  }

  async completeOrder(kitchen_order_id) {
    // Find index of the order
    const idx = this.state.orders.findIndex(
      (order) => order.kitchen_order_id === kitchen_order_id
    );

    if (idx !== -1) {
      const order = this.state.orders.find(
        (order) => order.kitchen_order_id === kitchen_order_id
      );

      // // Option 1: remove the order from the list
      // this.state.orders.splice(idx, 1);

      // Option 2 (instead of removing): mark it as completed
      this.state.orders[idx].state = "completed";
      this.state.ready_count = this.state.ready_count + 1;
      this.state.draft_count = this.state.draft_count - 1;
      const status = await this.orm.call(
        "pos.order",
        "broadcast_order_update",
        [
          `kitchen-${this.currentShopId}`,
          {
            from: "kitchen",
            message: `Order Completed\nTable: ${
              order.table
            }\n Products:${order.lines
              .map((line) => line.product_name)
              .join(",")}`,
          },
        ]
      );
    }
  }

  _onNotification(message) {
    try {
      if (!message || message.config_id !== this.currentShopId) {
        return;
      }

      this.add_order(message);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("Error handling bus notification:", err);
    }
  }

  _onNotification(message) {
    console.log(message);
    try {
      if (!message || message.config_id !== this.currentShopId) {
        return;
      }
      this.add_order(message);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("Error handling bus notification:", err);
    }
  }

  /**
   * Processes an incoming order message, calculates the difference (diff) from the
   * most recent version of the same order, and appends a new order containing
   * only the diff lines to the state.
   * @param {IncomingMessage} message - The incoming order data from the notification.
   */
  add_order(message) {
    function _normalizePosRef(ref) {
      if (ref === null || ref === undefined) return "";
      const s = String(ref).trim();
      // Remove a single leading "Order" (any case), with optional whitespace following it.
      return s.replace(/^\s*Order\s*/i, "").trim();
    }

    try {
      if (!message || typeof message !== "object") {
        console.warn("add_order: invalid message", message);
        return;
      }
      const { config_id, pos_reference } = message;
      if (
        config_id === undefined ||
        pos_reference === undefined ||
        pos_reference === null
      ) {
        console.warn(
          "add_order: message missing config_id or pos_reference",
          message
        );
        return;
      }

      const normalizedIncomingRef = _normalizePosRef(pos_reference);

      // Helper: sanitize product name by removing any leading CANCELLED: prefixes (case-insensitive)
      const stripCancelledPrefixes = (name = "") => {
        if (name === null || name === undefined) return "";
        return String(name)
          .replace(/^(?:\s*CANCELLED:\s*)+/i, "")
          .trim();
      };

      const orders = Array.isArray(this.state.orders) ? this.state.orders : [];

      // Aggregate previous quantities across all stored orders whose pos_reference matches normalizedIncomingRef
      const prevMap = new Map(); // product_id -> { qty: number, lastSanitizedName: string, lastRawName: string }

      for (const existingOrder of orders) {
        if (!existingOrder) continue;
        const existingRefNorm = _normalizePosRef(existingOrder.pos_reference);
        if (existingRefNorm !== normalizedIncomingRef) continue;
        const lines = Array.isArray(existingOrder.lines)
          ? existingOrder.lines
          : [];
        for (const line of lines) {
          const pid = line && (line.product_id ?? line.productId);
          if (pid === undefined || pid === null) continue;
          const rawName = (line.product_name ?? "") + "";
          const sanitized = stripCancelledPrefixes(rawName);
          const isCancelled = /^\s*CANCELLED:\s*/i.test(rawName);
          const qty = Number(line.qty);
          const numericQty = Number.isFinite(qty) ? qty : 0;

          const prevEntry = prevMap.get(pid) || {
            qty: 0,
            lastSanitizedName: "",
            lastRawName: "",
          };
          prevEntry.qty += isCancelled ? -numericQty : numericQty;
          prevEntry.lastSanitizedName =
            sanitized || prevEntry.lastSanitizedName;
          prevEntry.lastRawName = rawName || prevEntry.lastRawName;
          prevMap.set(pid, prevEntry);
        }
      }

      // Aggregate incoming message lines by product_id (new quantities)
      const newMap = new Map(); // product_id -> { qty: number, lastRawName: string }
      const incomingLines = Array.isArray(message.lines) ? message.lines : [];
      for (const line of incomingLines) {
        const pid = line && (line.product_id ?? line.productId);
        if (pid === undefined || pid === null) continue;
        const rawName = (line.product_name ?? "") + "";
        const qty = Number(line.qty);
        const numericQty = Number.isFinite(qty) ? qty : 0;

        const entry = newMap.get(pid) || { qty: 0, lastRawName: "" };
        entry.qty += numericQty;
        entry.lastRawName = rawName || entry.lastRawName;
        newMap.set(pid, entry);
      }

      // Union of product ids
      const allProductIds = new Set([...prevMap.keys(), ...newMap.keys()]);
      const diffLines = [];

      for (const pid of allProductIds) {
        const prevEntry = prevMap.get(pid) || {
          qty: 0,
          lastSanitizedName: "",
          lastRawName: "",
        };
        const newEntry = newMap.get(pid) || { qty: 0, lastRawName: "" };

        const prevQty = Number.isFinite(Number(prevEntry.qty))
          ? Number(prevEntry.qty)
          : 0;
        const newQty = Number.isFinite(Number(newEntry.qty))
          ? Number(newEntry.qty)
          : 0;

        if (newQty === prevQty) continue;

        if (newQty > prevQty) {
          const addedQty = newQty - prevQty;
          const name =
            (newEntry.lastRawName && String(newEntry.lastRawName).trim()) ||
            prevEntry.lastSanitizedName ||
            "";
          diffLines.push({
            product_id: pid,
            product_name: name,
            qty: addedQty,
          });
        } else {
          const cancelQty = prevQty - newQty;
          const baseNameRaw =
            (newEntry.lastRawName && String(newEntry.lastRawName).trim()) ||
            prevEntry.lastRawName ||
            prevEntry.lastSanitizedName ||
            "";
          const sanitizedBase = stripCancelledPrefixes(baseNameRaw);
          const cancelledName = sanitizedBase
            ? `CANCELLED: ${sanitizedBase}`
            : "CANCELLED:";
          diffLines.push({
            product_id: pid,
            product_name: cancelledName,
            qty: cancelQty,
          });
        }
      }

      if (diffLines.length === 0) return;

      // Merge to ensure single line per product_id
      const merged = new Map();
      for (const l of diffLines) {
        const pid = l.product_id;
        const qty = Number(l.qty);
        const numericQty = Number.isFinite(qty) ? qty : 0;
        const name = l.product_name ?? "";
        const existing = merged.get(pid);
        if (!existing)
          merged.set(pid, {
            product_id: pid,
            product_name: name,
            qty: numericQty,
          });
        else existing.qty += numericQty;
      }

      const finalLines = Array.from(merged.values());

      const newOrder = {
        config_id: message.config_id,
        pos_reference: message.pos_reference, // keep original form as provided
        date_order: message.date_order,
        from: message.from,
        state: message.state,
        floor: message.floor,
        table: message.table,
        lines: finalLines,
        kitchen_order_id:
          (Array.isArray(this.state.orders) ? this.state.orders.length : 0) + 1,
      };

      this.state.orders = [...orders, newOrder];
      this.state.draft_count =
        (Number.isFinite(Number(this.state.draft_count))
          ? Number(this.state.draft_count)
          : 0) + 1;
    } catch (err) {
      console.error("add_order: unexpected error", err);
    }
  }
}

KitchenScreenDashboard.template = "KitchenCustomDashBoard";
registry
  .category("actions")
  .add("kitchen_custom_dashboard_tags", KitchenScreenDashboard);
