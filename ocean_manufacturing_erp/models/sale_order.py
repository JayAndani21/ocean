# Copyright 2026 Ocean Technoforge
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    po_attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        relation="sale_order_po_attachment_rel",
        column1="order_id",
        column2="attachment_id",
        string="Customer PO Documents",
        help="Upload Customer Purchase Order attachments.",
    )

    po_number = fields.Char(
        string="Customer PO Number",
        help="Enter the Customer Purchase Order number.",
    )
