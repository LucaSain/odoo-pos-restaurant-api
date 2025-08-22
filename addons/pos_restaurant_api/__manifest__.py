{
    'name': 'Restaurant POS API Integration',
    'version': '18.0',
    'category': 'Point of Sale',
    'summary': 'Send POS orders to external API',
    'description': """
        This module extends the restaurant POS functionality to automatically
        send order information to an external API when orders are registered.
    """,
    'depends': ['pos_restaurant', 'point_of_sale'],
    'data': [
  
        'views/pos_category_form.xml',
      
        'security/ir.model.access.csv'
    ],
   
    'installable': True,
    'auto_install': False,
    'application': False,
}
