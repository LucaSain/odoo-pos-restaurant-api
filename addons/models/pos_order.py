import logging
import json
import requests
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    _inherit = 'pos.config'

    api_endpoint = fields.Char(
        string='API Endpoint',
        help='External API endpoint to send order data',
        default='https://a.com/api'
    )
    api_enabled = fields.Boolean(
        string='Enable API Integration',
        default=True
    )
    api_timeout = fields.Integer(
        string='API Timeout (seconds)',
        default=30
    )


class PosOrder(models.Model):
    _inherit = 'pos.order'

    api_sent = fields.Boolean(
        string='Sent to API',
        default=False,
        help='Indicates if order was successfully sent to external API'
    )
    api_response = fields.Text(
        string='API Response',
        help='Response from external API'
    )

    def _prepare_order_data_for_api(self):
        """Prepare order data in format suitable for external API"""
        _logger.info('Preparing order data for API: %s', self.pos_reference)

        order_data = {
            'order_id': self.id,
            'pos_reference': self.pos_reference,
            'session_id': self.session_id.id,
            'partner_id': self.partner_id.id if self.partner_id else None,
            'partner_name': self.partner_id.name if self.partner_id else None,
            'date_order': self.date_order.isoformat() if self.date_order else None,
            'amount_total': float(self.amount_total),
            'amount_tax': float(self.amount_tax),
            'amount_paid': float(self.amount_paid),
            'amount_return': float(self.amount_return),
            'state': self.state,
            'table_id': self.table_id.id if self.table_id else None,
            'lines': []
        }

        # Add order lines
        for line in self.lines:

            line_data = {
                'product_id': line.product_id.id,
                'product_name': line.product_id.name,
                'qty': float(line.qty),
                'price_unit': float(line.price_unit),
                'price_subtotal': float(line.price_subtotal),
                'price_subtotal_incl': float(line.price_subtotal_incl),
                'discount': float(line.discount),
                'note': line.note or '',
            }
            order_data['lines'].append(line_data)

        _logger.info('Order data prepared: %s', json.dumps(order_data, indent=2))
        return order_data

    @api.model
    def send_to_api(self, order_id):
        """RPC entrypoint: browse the single order and delegate."""
        order = self.browse(order_id)
        if not order:
            _logger.error("send_to_api: no order found with ID %r", order_id)
            return False
        return order._send_to_api()

    @api.model
    def send_to_api_by_reference(self, pos_reference):
        _logger.info("Sending POS order by reference: %s", pos_reference)
        order = None;
        #order = self.env['pos.order'].search([('pos_reference', '=', pos_reference)], limit=1)
        if not order:
            _logger.warning("No POS order found with reference: %s", pos_reference)
            return {"success": False, "error": "Order not found"}

        return order._send_to_api()

    def _send_to_api(self):
        """Send order data to external API"""
        _logger.info('send_to_api called for order: %s', self.pos_reference)

        if not self.session_id or not self.session_id.config_id:
            _logger.warning('No session or config found for order %s', self.pos_reference)
            return False

        if not self.session_id.config_id.api_enabled:
            _logger.info('API integration disabled for POS config %s', self.session_id.config_id.name)
            return True

        api_endpoint = self.session_id.config_id.api_endpoint
        if not api_endpoint:
            _logger.warning('No API endpoint configured for POS config %s', self.session_id.config_id.name)
            return False

        try:
            order_data = self._prepare_order_data_for_api()

            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }

            timeout = self.session_id.config_id.api_timeout or 30

            _logger.info('Sending POST request to: %s', api_endpoint)
            _logger.info('Request headers: %s', headers)
            _logger.info('Request data: %s', json.dumps(order_data, indent=2))

            response = requests.post(
                api_endpoint,
                json=order_data,
                headers=headers,
                timeout=timeout
            )

            _logger.info('API Response Status: %s', response.status_code)
            _logger.info('API Response Text: %s', response.text)

            response.raise_for_status()

            self.write({
                'api_sent': True,
                'api_response': response.text
            })

            _logger.info('Order %s successfully sent to API', self.pos_reference)
            return True

        except requests.exceptions.RequestException as e:
            error_msg = f'Failed to send order {self.pos_reference} to API: {str(e)}'
            _logger.error(error_msg)

            self.write({
                'api_sent': False,
                'api_response': error_msg
            })

            return False
        except Exception as e:
            error_msg = f'Unexpected error sending order {self.pos_reference} to API: {str(e)}'
            _logger.error(error_msg)

            self.write({
                'api_sent': False,
                'api_response': error_msg
            })

            return False

    @api.model
    def create_from_ui(self, orders, draft=False):
        """Override to send orders to API after creation"""
        _logger.info('create_from_ui called with %d orders, draft=%s', len(orders), draft)

        # Call the original method first
        order_ids = super().create_from_ui(orders, draft)

        _logger.info('Orders created: %s', order_ids)

        # Send each order to API
        for order_id in order_ids:
            try:
                order = self.browse(order_id['id'])
                _logger.info('Processing order %s (state: %s, draft: %s)', order.pos_reference, order.state, draft)

                if order and not draft:
                    _logger.info('Attempting to send order %s to API', order.pos_reference)
                    order._send_to_api()
                else:
                    _logger.info('Skipping API send for order %s (draft=%s)',
                                 order.pos_reference if order else 'Unknown', draft)

            except Exception as e:
                _logger.error('Failed to send order to API: %s', str(e))

        return order_ids

    @api.model
    def create(self, vals):
        """Override create to also handle direct order creation"""
        _logger.info('POS Order create called with vals: %s', vals)
        order = super().create(vals)

        # Try to send to API if this is a finalized order
        if order.state not in ['draft', 'cancel']:
            _logger.info('Order created with state %s, sending to API', order.state)
            order._send_to_api()

        return order

    # def write(self, vals):
    #     """Override write to catch state changes"""
    #     _logger.info('POS Order write called for %s with vals: %s', self.pos_reference, vals)
    #     result = super().write(vals)
    #
    #     # If state changed to paid/done and not sent to API yet, send it
    #     if 'state' in vals and vals['state'] in ['paid', 'done'] and not self.api_sent:
    #         _logger.info('Order %s state changed to %s, sending to API', self.pos_reference, vals['state'])
    #         self._send_to_api()
    #
    #     return result