import json
from odoo import http
from odoo.http import request


class PosMenuAPI(http.Controller):

    def _get_product_data(self, product, pricelist):
        """Helper to format product data and get the correct price."""
        return {
            'id': product.id,
            'name': product.display_name,  # This will be translated
            'description': product.description_sale,  # This will be translated
            'price': pricelist._get_product_price(product, 1.0, False),
            'image_url': f'/web/image/product.template/{product.id}/image_1920',
        }

    def _build_category_tree(self, category, pricelist):
        """Recursively builds the category tree with products."""
        # Find active products available in POS for this category
        products = request.env['product.template'].search([
            ('active', '=', True),
            ('available_in_pos', '=', True),
            ('pos_categ_id', '=', category.id)
        ])

        product_list = [self._get_product_data(p, pricelist) for p in products]

        # Find child categories
        child_categories = request.env['pos.category'].search([
            ('parent_id', '=', category.id)
        ])

        # Recursively build the tree for children
        child_list = [self._build_category_tree(child, pricelist) for child in child_categories]

        return {
            'id': category.id,
            'name': category.name,  # This will be translated
            'products': product_list,
            'children': child_list,
        }

    # -*- coding: utf-8 -*-
    from odoo import http
    from odoo.http import request

    class MenuTreeController(http.Controller):

        @http.route('/api/v1/pos-menu', type='json', auth='public', cors='*')
        def get_pos_menu(self, pos_config_id=None, lang='en_US', category_id=None):
            """
            Returns *only* the immediate children categories and products
            under `category_id`. If category_id is None, returns only root
            categories (parent_id = False) and no products.
            """
            if not pos_config_id:
                return {'error': 'pos_config_id is required.'}

            try:
                # Prepare translation context
                env = request.env(context=dict(request.env.context, lang=lang))
                pos_config = env['pos.config'].sudo().browse(int(pos_config_id))
                if not pos_config.exists():
                    return {'error': 'POS configuration not found.'}

                # Fetch flat data
                raw = pos_config.load_self_data()
                cats = raw['pos.category']['data']
                prods = raw['product.product']['data']

                # Determine which level to return
                parent_key = None if category_id is None else int(category_id)

                # 1) Filter subcategories at this level
                level_cats = [c for c in cats if (c.get('parent_id') or None) == parent_key]

                # 2) Serialize categories
                level_cats = [c for c in cats if (c.get('parent_id') or None) == parent_key]
                categories = []
                for c in level_cats:
                    # build the image URL only if has_image is True
                    img_url = None
                    if c.get('has_image'):
                        img_url = f"/web/image/pos.category/{c['id']}/image_128"

                    categories.append({
                        'id': c['id'],
                        'name': c['name'],
                        'has_more': any(ch['parent_id'] == c['id'] for ch in cats),
                        'image_url': img_url,
                        'parent_id': c['parent_id']
                    })


                # 3) If drilling into a real category, also fetch its products
                products = []
                if parent_key:
                    for p in prods:
                        if p.get('available_in_pos') and parent_key in (p.get('pos_categ_ids') or []):
                            products.append({
                                'id': p['id'],
                                'name': p['display_name'],
                                'price': p['lst_price'],
                                'price_incl': p['list_price'],
                                'description': p['public_description'],
                                'image_url': f"/web/image/product.product/{p['id']}/image_1024",
                            })
                category_name = None
                if parent_key is not None:
                    category_name = next((c['name'] for c in cats if c['id'] == parent_key), None)

                return {
                    'language': lang,
                    'category_id': parent_key,
                    'category_name':category_name,
                    'categories': categories,
                    'products': products,
                }

            except Exception as e:
                return {'error': str(e)}

        @http.route('/api/v1/pos-menu-languages', type='json', auth='public', cors='*')
        def get_pos_languages(self):
            """
            Returns all available languages with their codes, display names, and flag icons.
            """
            try:
                # Fetch all languages and include their flag icons
                langs = request.env['res.lang'].sudo().search([])
                data = []
                for lang in langs:
                    data.append({
                        'code':         lang.code,
                        'name':         lang.display_name,
                        'flag_icon':    lang.flag_image_url,
                    })
                return {'languages': data}
            except Exception as e:
                return {'error': str(e)}