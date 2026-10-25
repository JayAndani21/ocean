# Copyright 2026 Ocean Technoforge
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

from odoo import fields, models


class OceanSectionType(models.Model):
    _name = "ocean.section.type"
    _description = "Section Type"
    _order = "name"

    name = fields.Char(string="Section Type", required=True, translate=True)
    active = fields.Boolean(default=True)
