# Copyright 2026 Ocean Technoforge
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpWorkorderProductionEntry(models.TransientModel):
    _name = "mrp.workorder.production.entry"
    _description = "Production Entry Wizard"

    wizard_mode = fields.Selection(
        selection=[
            ("start", "Start Production"),
            ("save_progress", "Save Progress"),
            ("finish", "Finish Production"),
        ],
        string="Wizard Mode",
        default="start",
        required=True,
    )
    workorder_id = fields.Many2one(
        comodel_name="mrp.workorder",
        string="Work Order",
        required=True,
    )
    session_id = fields.Many2one(
        comodel_name="mrp.workorder.session",
        string="Production Session",
    )
    production_id = fields.Many2one(
        related="workorder_id.production_id",
        readonly=True,
        string="Manufacturing Order",
    )
    operation_type = fields.Selection(
        related="workorder_id.operation_type",
        readonly=True,
        string="Operation Type",
    )
    product_id = fields.Many2one(
        related="workorder_id.product_id",
        readonly=True,
        string="Product",
    )
    workcenter_id = fields.Many2one(
        related="workorder_id.workcenter_id",
        readonly=True,
        string="Work Center",
    )
    planned_qty = fields.Float(
        related="workorder_id.qty_production",
        readonly=True,
        string="Target Quantity",
    )
    input_qty = fields.Float(
        string="Input Quantity",
        compute="_compute_input_qty",
        store=True,
        readonly=False,
    )
    required_material_qty = fields.Float(
        compute="_compute_required_material_qty",
        readonly=True,
        string="Input Quantity (Required Material)",
    )
    produced_qty = fields.Float(
        string="Output Quantity",
        compute="_compute_produced_qty",
        store=True,
        readonly=False,
    )
    scrap_qty = fields.Float(
        string="Reject Quantity",
        compute="_compute_scrap_qty",
        store=True,
        readonly=False,
    )
    remarks = fields.Text(
        string="Remarks",
        compute="_compute_remarks",
        store=True,
        readonly=False,
    )
    previous_remarks = fields.Text(
        string="Previous Operations Remarks",
        compute="_compute_previous_remarks",
        readonly=True,
    )

    @api.depends("production_id", "workorder_id")
    def _compute_required_material_qty(self):
        for wizard in self:
            qty = 0.0
            if wizard.production_id:
                qty = sum(wizard.production_id.move_raw_ids.mapped("product_uom_qty"))
            wizard.required_material_qty = qty

    @api.depends("production_id", "workorder_id")
    def _compute_previous_remarks(self):
        for wizard in self:
            remarks_list = []
            if wizard.production_id and wizard.workorder_id:
                prior_wos = wizard.production_id.workorder_ids.filtered(
                    lambda w: w.sequence < wizard.workorder_id.sequence or (w.sequence == wizard.workorder_id.sequence and w.id < wizard.workorder_id.id)
                )
                for pwo in prior_wos.sorted(key=lambda w: (w.sequence, w.id)):
                    notes = []
                    if pwo.remarks:
                        notes.append(pwo.remarks)
                    sessions = pwo.session_ids.filtered(lambda s: s.remarks)
                    for sess in sessions:
                        if sess.remarks not in notes:
                            notes.append(sess.remarks)
                    if notes:
                        op_name = pwo.name or (pwo.operation_id and pwo.operation_id.name) or "Operation"
                        remarks_list.append(f"[{op_name}]: " + " | ".join(notes))
            wizard.previous_remarks = "\n".join(remarks_list) if remarks_list else False
    good_qty = fields.Float(
        string="Good Quantity",
        compute="_compute_good_qty",
        store=True,
        readonly=True,
    )

    @api.depends("produced_qty", "scrap_qty")
    def _compute_good_qty(self):
        for wizard in self:
            wizard.good_qty = max(0.0, wizard.produced_qty - wizard.scrap_qty)

    @api.depends("session_id", "session_id.current_output_qty", "session_id.final_output_qty")
    def _compute_produced_qty(self):
        for wizard in self:
            if wizard.session_id:
                wizard.produced_qty = wizard.session_id.final_output_qty or wizard.session_id.current_output_qty or 0.0
            else:
                wizard.produced_qty = wizard.produced_qty or 0.0

    @api.depends("session_id", "session_id.current_reject_qty", "session_id.final_reject_qty")
    def _compute_scrap_qty(self):
        for wizard in self:
            if wizard.session_id:
                wizard.scrap_qty = wizard.session_id.final_reject_qty or wizard.session_id.current_reject_qty or 0.0
            else:
                wizard.scrap_qty = wizard.scrap_qty or 0.0

    @api.depends("session_id", "session_id.remarks")
    def _compute_remarks(self):
        for wizard in self:
            if wizard.session_id and wizard.session_id.remarks:
                wizard.remarks = wizard.session_id.remarks
            else:
                wizard.remarks = wizard.remarks or ""

    @api.depends("workorder_id", "session_id", "session_id.input_qty", "workorder_id.input_qty")
    def _compute_input_qty(self):
        for wizard in self:
            if wizard.workorder_id and wizard.workorder_id.input_qty:
                wizard.input_qty = wizard.workorder_id.input_qty
            elif wizard.session_id and wizard.session_id.input_qty:
                wizard.input_qty = wizard.session_id.input_qty
            elif wizard.operation_type == "cutting":
                qty = 0.0
                if wizard.production_id:
                    qty = sum(wizard.production_id.move_raw_ids.mapped("product_uom_qty"))
                wizard.input_qty = qty or wizard.planned_qty
            elif wizard.planned_qty:
                wizard.input_qty = wizard.planned_qty
            else:
                wizard.input_qty = 0.0

    def action_confirm_start(self):
        """Confirm starting production and update single session."""
        self.ensure_one()
        wo = self.workorder_id
        session = self.session_id or self.env["mrp.workorder.session"]._get_or_create_session(wo)
        
        session.write({
            "input_qty": self.input_qty or wo.input_qty,
            "state": "in_progress",
            "start_time": session.start_time or fields.Datetime.now(),
        })
        if self.input_qty:
            wo.input_qty = self.input_qty
            raw_moves = wo.move_raw_ids or wo.production_id.move_raw_ids.filtered(lambda m: m.state not in ("done", "cancel"))
            if raw_moves:
                for move in raw_moves:
                    move._set_quantity_done(self.input_qty)
                    move.write({
                        "manual_consumption": True,
                        "picked": True,
                    })
            
        return {"type": "ir.actions.act_window_close"}

    def action_save_progress(self):
        """Save progress (pause) and update single session without completing work order."""
        self.ensure_one()
        wo = self.workorder_id
        session = self.session_id or self.env["mrp.workorder.session"]._get_or_create_session(wo)

        if self.produced_qty < 0:
            raise UserError(_("Output Quantity cannot be negative."))
        if self.scrap_qty < 0:
            raise UserError(_("Reject Quantity cannot be negative."))

        session.write({
            "current_output_qty": self.produced_qty,
            "current_reject_qty": self.scrap_qty,
            "remarks": self.remarks,
            "state": "paused",
            "pause_time": fields.Datetime.now(),
        })
        return {"type": "ir.actions.act_window_close"}

    def action_finish_operation(self):
        """Validate inputs, create scrap if needed, update session & WO, pass input_qty to next WO, and complete operation."""
        self.ensure_one()
        wo = self.workorder_id
        if not wo:
            raise UserError(_("No work order associated with this entry."))

        if self.produced_qty < 0:
            raise UserError(_("Output Quantity cannot be negative."))
        if self.scrap_qty < 0:
            raise UserError(_("Reject Quantity cannot be negative."))

        session = self.session_id or self.env["mrp.workorder.session"]._get_or_create_session(wo)

        # 1. Calculate good_qty internally
        good_qty = max(0.0, self.produced_qty - self.scrap_qty)

        # 2. Update single session record with final output & reject data
        session.write({
            "final_output_qty": self.produced_qty,
            "final_reject_qty": self.scrap_qty,
            "remarks": self.remarks,
            "state": "completed",
            "finish_time": fields.Datetime.now(),
        })

        # 3. Create scrap record if scrap_qty > 0
        if self.scrap_qty > 0:
            scrap = self.env["stock.scrap"].create({
                "product_id": wo.product_id.id,
                "scrap_qty": self.scrap_qty,
                "product_uom_id": wo.product_uom_id.id or wo.product_id.uom_id.id,
                "workorder_id": wo.id,
                "production_id": wo.production_id.id,
                "origin": f"Production Entry for {wo.name}",
            })
            scrap.action_validate()

        # 4. Mark work order as production completed and update producing qty & raw material consumption
        wo.is_production_completed = True
        wo.qty_producing = self.produced_qty if wo.operation_type == "packing" else good_qty

        raw_moves = wo.move_raw_ids or wo.production_id.move_raw_ids.filtered(lambda m: m.state not in ("done", "cancel"))
        if raw_moves and self.input_qty > 0:
            for move in raw_moves:
                move._set_quantity_done(self.input_qty)
                move.write({
                    "manual_consumption": True,
                    "picked": True,
                })

        # 5. Pass output/good quantity to next work order as input_qty and update its session
        next_wo = self._get_next_workorder(wo)
        if next_wo:
            passed_qty = good_qty if wo.operation_type not in ("packing", "inspection") else self.produced_qty
            next_wo.input_qty = passed_qty
            next_session = self.env["mrp.workorder.session"]._get_or_create_session(next_wo)
            next_session.write({"input_qty": passed_qty})

        # 6. Complete current work order
        if wo.state not in ("done", "cancel"):
            wo.with_context(skip_finish_wizard=True).button_finish()

        return {"type": "ir.actions.act_window_close"}

    def _get_next_workorder(self, wo):
        """Find the next work order in sequence for the same MO."""
        workorders = wo.production_id.workorder_ids.sorted(key=lambda w: (w.sequence, w.id))
        found = False
        for w in workorders:
            if found:
                return w
            if w.id == wo.id:
                found = True
        return False
