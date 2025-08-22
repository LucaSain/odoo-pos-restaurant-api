from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo import api, models





class PosOrder(models.Model):
    _inherit = "pos.order"


    @api.model
    def broadcast_order_update(self, channel, payload):
        """RPC called from the client to broadcast a payload on a bus channel.

        channel: string (e.g. "pos_order_created_1")
        payload: serializable dict (no recordsets)
        """
        try:
            # Use sudo if you want to avoid ACL issues for POS clients.
            self.env['bus.bus'].sudo()._sendone(channel,"notification", payload)
            return {'success': True}
        except Exception as e:

            return {'success': False, 'error': str(e)}


    order_status = fields.Selection(
        selection=[
            ('draft', 'Cooking'),
            ('waiting', 'Ready'),
            ('cancel', 'Cancel'),
        ],
        string="Order Status",
        default='draft',
        index=True,
        tracking=True,
    )

    @api.model
    def get_details(self, shop_id):
        """Return orders and their lines for the kitchen screen.
        Each order dict will include a `lines` key (list), so the frontend
        can safely iterate `order.lines`.
        """
        shop_id = int(shop_id or 0)
        domain = [('config_id', '=', shop_id), ('state', '!=', 'cancel')]
        orders = self.search(domain, order='date_order desc', limit=500)

        orders_data = []
        lines_data = []

        for order in orders:
            # Find line records (POS uses either 'lines' or 'order_line' historically)
            order_lines = order.lines or getattr(order, 'order_line', self.env['pos.order.line'].browse())

            # Build per-order lines list and also append to a flat list
            order_lines_list = []
            for line in order_lines:
                prod = getattr(line, 'product_id', None)
                prod_pair = [prod.id, prod.display_name] if prod else False

                qty = (
                    getattr(line, 'qty', None)
                    or getattr(line, 'quantity', None)
                    or getattr(line, 'product_uom_qty', None)
                    or 0
                )
                note = (getattr(line, 'note', None) or getattr(line, 'description', '') or '')

                line_item = {
                    'id': line.id,
                    'order_id': order.id,
                    'product_id': prod_pair,
                    'qty': qty,
                    'price_unit': getattr(line, 'price_unit', 0),
                    'note': note,
                }

                order_lines_list.append(line_item)
                lines_data.append(line_item)

            orders_data.append({
                'id': order.id,
                'name': order.name,
                'date_order': order.date_order,
                'order_status': getattr(order, 'order_status', False),
                'state': order.state,
                'table_id': [order.table_id.id, getattr(order.table_id, 'name', False)] if order.table_id else False,
                'config_id': [order.config_id.id, getattr(order.config_id, 'name', False)] if order.config_id else False,
                # Crucial: include lines inside the order
                'lines': order_lines_list,
            })

        # Ensure we always return lists (never None)
        return {'orders': orders_data or [], 'order_lines': lines_data or []}


    @api.model
    def update_order_status(self, order_id, new_status):
        """Update order status from JS via /web/dataset/call_kw."""
        # use sudo() only if your ACLs require it
        self = self.sudo()

        # validate status
        allowed = dict(self._fields['order_status'].selection)
        if new_status not in allowed:
            raise UserError(_("Invalid status: %s") % new_status)

        order = self.browse(order_id)
        if not order.exists():
            raise UserError(_("Order not found: %s") % order_id)

        order.write({'order_status': new_status})
        return {
            'success': True,
            'order_id': order.id,
            'new_status': order.order_status,
        }
