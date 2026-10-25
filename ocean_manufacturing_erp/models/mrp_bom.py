# Copyright 2026 Ocean Technoforge
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

from odoo import api, fields, models


class MrpRoutingWorkcenter(models.Model):
    _inherit = "mrp.routing.workcenter"

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


class MrpBom(models.Model):
    _inherit = "mrp.bom"

    consumption = fields.Selection(
        default="flexible",
    )
    process_template_id = fields.Many2one(
        comodel_name="ocean.process.template",
        string="Process Template",
        help="Select a reusable process template to automatically populate BoM operations.",
    )

    @api.onchange("process_template_id")
    def _onchange_process_template_id(self):
        """Automatically copy template operations into BoM operations when template is selected."""
        if self.process_template_id:
            self._apply_process_template()

    def action_reload_process_template(self):
        """Button action to reload BoM operations from the selected Process Template."""
        for bom in self:
            if bom.process_template_id:
                bom._apply_process_template()
        return True

    def _apply_process_template(self):
        """Helper method to copy template operations to BoM operations."""
        self.ensure_one()
        if not self.process_template_id:
            return

        new_operations = []
        for line in self.process_template_id.line_ids:
            new_operations.append((0, 0, {
                "sequence": line.sequence,
                "name": line.name,
                "workcenter_id": line.workcenter_id.id,
                "operation_type": line.operation_type,
                "time_mode": "manual",
            }))

        self.operation_ids = [(5, 0, 0)] + new_operations
