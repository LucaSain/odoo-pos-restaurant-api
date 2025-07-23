from odoo import models, fields, api

class PosCategory(models.Model):
    _inherit = 'pos.category'

    image_1920 = fields.Image(
        "Image (1920px)",
        max_width=1920, max_height=1920,
        help="Master high‑resolution image"
    )
    image_1024 = fields.Image(
        compute='_compute_images',
        inverse='_inverse_image',
        max_width=1024, max_height=1024,
        store=True
    )
    image_512  = fields.Image(compute='_compute_images', inverse='_inverse_image', max_width=512,  max_height=512,  store=True)
    image_256  = fields.Image(compute='_compute_images', inverse='_inverse_image', max_width=256,  max_height=256,  store=True)
    image_128  = fields.Image(compute='_compute_images', inverse='_inverse_image', max_width=128,  max_height=128,  store=True)

    @api.depends('image_1920')
    def _compute_images(self):
        for rec in self:
            rec.image_1024 = rec.image_1920
            rec.image_512  = rec.image_1920
            rec.image_256  = rec.image_1920
            rec.image_128  = rec.image_1920

    def _inverse_image(self):
        for rec in self:
            # whichever size was written, use it to overwrite the master
            rec.image_1920 = rec.image_128 or rec.image_256 or rec.image_512 or rec.image_1024
