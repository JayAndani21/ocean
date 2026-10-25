# Copyright 2026 Ocean Technoforge
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

from odoo import fields, models


class OceanProcessTemplate(models.Model):
    _name = "ocean.process.template"
    _description = "Process Template"
    _order = "name"

    name = fields.Char(string="Template Name", required=True, translate=True)
    code = fields.Char(string="Code")
    active = fields.Boolean(default=True)
    note = fields.Text(string="Notes")
    line_ids = fields.One2many(
        comodel_name="ocean.process.template.line",
        inverse_name="template_id",
        string="Operations",
        copy=True,
    )


class OceanProcessTemplateLine(models.Model):
    _name = "ocean.process.template.line"
    _description = "Process Template Operation Line"
    _order = "sequence, id"

    template_id = fields.Many2one(
        comodel_name="ocean.process.template",
        string="Process Template",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="Sequence", default=10)
    name = fields.Char(string="Operation Name", required=True)
    workcenter_id = fields.Many2one(
        comodel_name="mrp.workcenter",
        string="Work Center",
        required=True,
    )
    operation_type = fields.Selection(
        selection=[
            ("cutting", "Cutting"),
            ("forging", "Forging"),
            ("cnc", "CNC"),
            ("vmc", "VMC"),
            ("inspection", "Inspection"),
            ("packing", "Packing"),
        ],
        string="Operation Type",
        default="cutting",
        required=True,
    )
