# Copyright 2026 Ocean Technoforge
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

from odoo import fields, models


class OceanMaterialGrade(models.Model):
    _name = "ocean.material.grade"
    _description = "Material Grade"
    _order = "name"

    name = fields.Char(string="Grade", required=True, translate=True)
    active = fields.Boolean(default=True)
