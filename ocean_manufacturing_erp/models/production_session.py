# Copyright 2026 Ocean Technoforge
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

from odoo import api, fields, models


class MrpWorkorderSession(models.Model):
    _name = "mrp.workorder.session"
    _description = "Work Order Production Session"
    _order = "id desc"

    workorder_id = fields.Many2one(
        comodel_name="mrp.workorder",
        string="Work Order",
        required=True,
        index=True,
        ondelete="cascade",
    )
    production_id = fields.Many2one(
        related="workorder_id.production_id",
        store=True,
        readonly=True,
        string="Manufacturing Order",
    )
    product_id = fields.Many2one(
        related="workorder_id.product_id",
        store=True,
        readonly=True,
        string="Product",
    )
    workcenter_id = fields.Many2one(
        related="workorder_id.workcenter_id",
        store=True,
        readonly=True,
        string="Work Center",
    )
    operation_type = fields.Selection(
        related="workorder_id.operation_type",
        store=True,
        readonly=True,
        string="Operation Type",
    )
    input_qty = fields.Float(
        string="Input Quantity",
        default=0.0,
    )
    required_material_qty = fields.Float(
        string="Input Quantity (Required Material)",
        default=0.0,
    )
    current_output_qty = fields.Float(
        string="Current Output Quantity",
        default=0.0,
    )
    current_reject_qty = fields.Float(
        string="Current Reject Quantity",
        default=0.0,
    )
    final_output_qty = fields.Float(
        string="Final Output Quantity",
        default=0.0,
    )
    final_reject_qty = fields.Float(
        string="Final Reject Quantity",
        default=0.0,
    )
    remarks = fields.Text(
        string="Remarks",
    )
    operator_id = fields.Many2one(
        comodel_name="res.users",
        string="Operator",
        default=lambda self: self.env.user,
    )
    start_time = fields.Datetime(
        string="Start Time",
    )
    pause_time = fields.Datetime(
        string="Pause Time",
    )
    resume_time = fields.Datetime(
        string="Resume Time",
    )
    finish_time = fields.Datetime(
        string="Finish Time",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("in_progress", "In Progress"),
            ("paused", "Paused"),
            ("completed", "Completed"),
        ],
        string="Status",
        default="draft",
        required=True,
    )

    @api.model
    def _get_or_create_session(self, workorder):
        """Find the single existing session for the given workorder or create a new one."""
        session = self.search([("workorder_id", "=", workorder.id)], limit=1)
        if not session:
            req_mat_qty = 0.0
            if workorder.production_id:
                req_mat_qty = sum(workorder.production_id.move_raw_ids.mapped("product_uom_qty"))

            session = self.create({
                "workorder_id": workorder.id,
                "input_qty": workorder.input_qty,
                "required_material_qty": req_mat_qty,
                "state": "draft",
            })
        return session
